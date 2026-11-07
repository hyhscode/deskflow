import json

from langchain_core.tools import tool
from langchain.agents import create_agent
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import collect_permissions
from app.models import Message, Ticket, User
from app.services.assist import draft_reply
from app.services.callbacks import DbLogHandler
from app.services.kb_search import search_kb_hybrid
from app.services.llm import LLMError, build_chat_model
from app.services.ticket_svc import DATA_SCOPE_ALL, list_tickets

MAX_STEPS = 8        # Agent 最多循环几轮：模型绕不出来时强制停


class AgentStep(BaseModel):
    """一次工具调用。"""
    tool: str
    args: dict


class AgentResult(BaseModel):
    answer: str
    steps: list[AgentStep] = []
    tool_calls: int = 0


SYSTEM_PROMPT = (
    "你是客服工作台的助手。规则：\n"
    "1. 需要数据时必须用工具查，不许凭空回答；\n"
    "2. 能并行调用的工具就一次调完，不要来回多轮；\n"
    "3. 只做查询和起草，不要承诺你做不了的事（比如替客户改状态）；\n"
    "4. 最后用中文简报式回答，先说结论，再列依据。"
)


def _can_access(ticket: Ticket, user: User, perms: list[str]) -> bool:
    """能不能碰这张单（和 desk.py 里的规则保持一致）。"""
    return ticket.assignee_id == user.id or DATA_SCOPE_ALL in perms


def _make_tools(db: Session, user: User) -> list:
    perms = collect_permissions(user)

    @tool
    def my_tickets(status: str = "") -> str:
        """查当前客服的工单列表。status 可选 assigned / processing / resolved / closed，留空表示全部。"""
        rows = list_tickets(db, user, perms, status or None)
        if not rows:
            return "没有符合条件的工单"
        return json.dumps(
            [
                {
                    "id": t.id, "title": t.title, "status": t.status,
                    "priority": t.priority, "category": t.category,
                }
                for t in rows[:20]
            ],
            ensure_ascii=False,
        )

    @tool
    def get_ticket(ticket_id: int) -> str:
        """查一张工单的详情和最近几条对话。用于了解客户到底说了什么。"""
        ticket = db.get(Ticket, ticket_id)
        if ticket is None:
            return f"工单 {ticket_id} 不存在"
        if not _can_access(ticket, user, perms):
            return "这张工单没有派给当前客服，无权查看"

        messages = db.execute(
            select(Message)
            .where(Message.conversation_id == ticket.conversation_id)
            .order_by(Message.id.desc())
            .limit(8)
        ).scalars().all()

        return json.dumps(
            {
                "id": ticket.id,
                "title": ticket.title,
                "status": ticket.status,
                "priority": ticket.priority,
                "summary": ticket.summary,
                "first_response_at": str(ticket.first_response_at) if ticket.first_response_at else None,
                "recent_messages": [
                    {"sender": m.sender, "content": m.content[:200]}
                    for m in reversed(messages)
                ],
            },
            ensure_ascii=False,
        )

    @tool
    def search_knowledge(keyword: str) -> str:
        """在知识库里检索资料。返回最相关的几条标题和正文片段，用来支撑回复。"""
        result = search_kb_hybrid(db, keyword)
        if not result.hits:
            return "知识库里没有找到相关内容"
        return json.dumps(
            [{"title": h.title, "content": h.content[:300]} for h in result.hits],
            ensure_ascii=False,
        )

    @tool
    def make_draft(ticket_id: int, instruction: str = "") -> str:
        """为某张工单生成回复草稿。instruction 是客服的额外要求，例如"语气客气点"。"""
        ticket = db.get(Ticket, ticket_id)
        if ticket is None:
            return f"工单 {ticket_id} 不存在"
        if not _can_access(ticket, user, perms):
            return "这张工单没有派给当前客服，无权起草"

        result = draft_reply(db, ticket, instruction or None)
        return result["draft"]

    return [my_tickets, get_ticket, search_knowledge, make_draft]


def run(db: Session, user: User, message: str, trace_id: str | None = None) -> AgentResult:

    tools = _make_tools(db, user)

    agent = create_agent(
        build_chat_model(temperature=0.0),
        tools=tools,                    # 注意：现在是关键字参数 tools=
        system_prompt=SYSTEM_PROMPT,    # 注意：不是 prompt=
    )

    try:
        out = agent.invoke(
            {"messages": [("user", message)]},
            config={
                "recursion_limit": MAX_STEPS,
                # 每次模型调用都会经过这个 handler，自动写 llm_logs
                "callbacks": [DbLogHandler(db, "agent", trace_id)],
            },
        )
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(f"助手执行失败：{str(exc)[:200]}") from exc

    # 把"调了哪些工具"捞出来 —— 这是可解释性的来源
    steps: list[AgentStep] = []
    for msg in out["messages"]:
        for call in (getattr(msg, "tool_calls", None) or []):
            steps.append(AgentStep(tool=call["name"], args=call.get("args") or {}))

    last = out["messages"][-1]
    answer = last.content if isinstance(last.content, str) else str(last.content)

    return AgentResult(answer=answer, steps=steps, tool_calls=len(steps))
