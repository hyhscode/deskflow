from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Message, QaReport, Ticket
from app.services.kb_search import search_kb
from app.services.llm import LLMError, run_structured, run_text

MAX_HISTORY = 50

class QaScore(BaseModel):
    """质检四维打分。权重合计 100。"""
    understanding: int = Field(description="问题理解，0-25 分")
    solution: int = Field(description="解决方案，0-40 分")
    accuracy: int = Field(description="信息准确，0-20 分")
    attitude: int = Field(description="服务态度，0-15 分")
    comment: str = Field(description="一句话点评，指出最需要改进的一点")

QA_WEIGHTS = {"understanding": 25, "solution": 40, "accuracy": 20, "attitude": 15}

def _load_conversation(db: Session, ticket: Ticket) -> list[Message]:
    """取这张工单对应的完整对话（时间正序）。"""
    return db.execute(
        select(Message)
        .where(Message.conversation_id == ticket.conversation_id)
        .order_by(Message.id)
    ).scalars().all()

def _transcript(messages: list[Message]) -> str:
    role_map = {"visitor": "客户", "ai": "机器人", "agent": "客服"}
    return "\n".join(
        f"{role_map.get(m.sender, m.sender)}：{m.content}"
        for m in messages[-MAX_HISTORY:]
    )

def summarize_ticket(db: Session, ticket: Ticket, trace_id: str | None = None) -> str:
    messages = _load_conversation(db, ticket)
    if not messages:
        return ticket.summary or ""

    system_prompt = (
        "你是客服系统的记录员。把下面的对话压缩成给客服看的摘要。\n"
        "严格按三行输出，每行不超过 40 字，不要序号、不要 markdown：\n"
        "问题：客户想解决什么\n"
        "处理：客服/机器人做了什么\n"
        "结果：当前状态（已解决/待客户确认/已转人工）\n"
        "只依据对话内容，不要推测没提到的事。"
    )
    user_prompt = (
        f"工单标题：{ticket.title}\n"
        f"工单状态：{ticket.status}\n"
        f"对话记录：\n{_transcript(messages)}"
    )

    try:
        summary = run_text(
            system_prompt, user_prompt,
            scene="summary", db=db, trace_id=trace_id, max_tokens=200,
        )
    except LLMError:
        first = next((m.content for m in messages if m.sender == "visitor"), ticket.title)
        summary = f"问题：{first[:60]}\n处理：（模型不可用，未生成）\n结果：{ticket.status}"

    ticket.summary = summary
    return summary

def draft_reply(
    db: Session,
    ticket: Ticket,
    instruction: str | None = None,
    trace_id: str | None = None,
) -> dict:
    messages = _load_conversation(db, ticket)
    last_visitor = next(
        (m.content for m in reversed(messages) if m.sender == "visitor"),
        ticket.title,
    )

    kb = search_kb(db, last_visitor)          # 复用主链路的检索
    citations, context = [], ""
    if kb.hits:
        context = "\n\n".join(
            f"【资料{i}】{h.title}\n{h.content[:400]}"
            for i, h in enumerate(kb.hits[:3], start=1)
        )
        citations = [{"article_id": h.article_id, "title": h.title} for h in kb.hits[:3]]

    system_prompt = (
        "你是 SaaS 公司的客服。根据【资料】和对话记录，写一段给客户的回复草稿。\n"
        "要求：\n"
        "1. 只能依据资料里的事实，资料没写的不要编；\n"
        "2. 100 字以内，口语化，不要 markdown、不要落款；\n"
        "3. 资料不足以回答时，就写需要客户补充什么信息。"
    )
    user_prompt = (
        f"{context}\n\n"
        f"客户最后一句：{last_visitor}\n"
        f"工单分类：{ticket.category}，优先级：{ticket.priority}\n"
        + (f"客服额外要求：{instruction}" if instruction else "")
    )

    try:
        draft = run_text(
            system_prompt, user_prompt,
            scene="draft", db=db, trace_id=trace_id, max_tokens=300,
        )
        return {"draft": draft, "citations": citations, "source": "llm"}
    except LLMError:
        if kb.hits:
            return {"draft": kb.hits[0].content[:200], "citations": citations, "source": "fallback"}
        return {"draft": "您好，这个问题我需要确认一下，稍后回复您。",
                "citations": [], "source": "fallback"}

def score_qa(db: Session, ticket: Ticket, trace_id: str | None = None) -> QaReport:
    messages = _load_conversation(db, ticket)

    system_prompt = (
        "你是客服质检员。根据对话记录给这次服务打分。\n"
        "四个维度（分值上限）：问题理解 0-25、解决方案 0-40、"
        "信息准确 0-20、服务态度 0-15。\n"
        "comment 写一句话点评，指出最需要改进的一点。"
    )
    user_prompt = f"工单：{ticket.title}\n状态：{ticket.status}\n对话：\n{_transcript(messages)}"

    report = db.execute(
        select(QaReport).where(QaReport.ticket_id == ticket.id)
    ).scalars().first()

    try:
        raw = run_structured(system_prompt, user_prompt, QaScore,
                             scene="qa", db=db, trace_id=trace_id)

        # 转成 QaScore 实例：既拿到类型提示，也做一次校验
        data = QaScore.model_validate(raw)

        dimensions, total = {}, 0
        for code, limit in QA_WEIGHTS.items():
            value = max(0, min(limit, getattr(data, code)))   # 夹紧到 0~上限
            dimensions[code] = value
            total += value
        comment = data.comment[:200]

    except (LLMError, ValueError):
        # 降级给 0 分 + 说明，而不是伪造一个分数。
        # 伪造分比没分更糟：主管会以为已经质检过
        dimensions = {code: 0 for code in QA_WEIGHTS}
        total = 0
        comment = "模型不可用，本次未完成自动质检"

    if report is None:
        report = QaReport(ticket_id=ticket.id)
        db.add(report)

    report.score = total
    report.dimensions = dimensions
    report.comment = comment
    db.flush()
    return report


def review_qa(db: Session, report: QaReport, reviewer_id: int,human_score: int | None = None, comment: str | None = None) -> QaReport:
    report.reviewed = True
    report.reviewer_id = reviewer_id

    dims = dict(report.dimensions or {})

    if human_score is not None:
        human_score = max(0, min(100, human_score))
        diff = abs(report.score - human_score)
        dims["human_score"] = human_score
        dims["review_diff"] = diff
        dims["conflict"] = diff > 20
        report.score = human_score      # 最终分以人工为准

    if comment:
        report.comment = comment

    report.dimensions = dims    # 重新赋值，确保 SQLAlchemy 认为它变了
    return report