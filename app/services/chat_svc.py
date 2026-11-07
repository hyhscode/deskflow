from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, Message
from app.services.pipeline import PipelineResult, handle_message
from app.services.classify import classify
from app.services.ticket_svc import create_ticket


class ChatRecord(BaseModel):
    conversation_id : int 
    visitor_message_id:int
    reply_message_id:int
    result:PipelineResult

def get_or_create_conversation(db:Session,visitor_key:str) -> tuple[Conversation,bool]:
    conv = db.execute(
        select(Conversation)
        .where(
            Conversation.visitor_key == visitor_key,
            Conversation.status == "open",
    ).order_by(Conversation.id.desc())
    ).scalars().first()

    if conv is not None:
        return conv, False

    conv = Conversation(
        visitor_key=visitor_key,
        channel="web",
        status="open",
    )
    db.add(conv)
    db.flush()
    return conv, True

def save_message(
    db: Session,
    conversation_id: int,
    sender: str,
    content: str,
    content_type: str = "text",
) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        sender=sender,
        content=content,
        content_type=content_type,
    )
    db.add(msg)
    db.flush()
    return msg

def handle_and_save(db: Session, visitor_key: str, content: str) -> ChatRecord:
    # ① 先分类（纯计算，不碰数据库）
    cls = classify(content)

    # ② 会话 + 存客户消息
    conv, _ = get_or_create_conversation(db, visitor_key)
    visitor_msg = save_message(db, conv.id, "visitor", content)

    # ③ 紧急或投诉 → P1，其余 P2
    priority = "P1" if cls.urgency == "high" or cls.category == "complaint" else "P2"

    # ④ 投诉 / 生气+紧急：不给 AI 处理，直接建单
    if cls.need_human:
        ticket = create_ticket(db, conv.id, content, cls.category, priority)
        result = PipelineResult(
            type="ticket",
            content=f"已为您转接人工客服，工单号 #{ticket.id}，请稍候。",
        )
    else:
        # ⑤ 正常三层分流
        result = handle_message(db, content)

        # ⑥ 三层都答不上 → 这时才建单，并把工单号告诉客户
        if result.type == "ticket":
            ticket = create_ticket(db, conv.id, content, cls.category, priority)
            result = PipelineResult(
                type="ticket",
                content=(
                    f"已为您转接人工客服，工单号 #{ticket.id}，预计 5 分钟内回复。"
                    "也可以点右下角「转人工」催一下。"
                ),
            )

    # ⑦ 存答复 + 提交
    ai_msg = save_message(db, conv.id, "ai", result.content, content_type=result.type)
    db.commit()

    return ChatRecord(
        conversation_id=conv.id,
        visitor_message_id=visitor_msg.id,
        reply_message_id=ai_msg.id,
        result=result,
    )
