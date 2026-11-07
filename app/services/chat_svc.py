from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, Message
from app.services.pipeline import PipelineResult, handle_message

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
    ).scalar().first()

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
    conv,_=get_or_create_conversation(db,visitor_key)
    visitor_msg = save_message(db,conv.id,"visitor",content)
    result = handle_message(db,content)

    ai_msg = save_message(
        db, conv.id, "ai", result.content, content_type=result.type
    )
    db.commit()

    return ChatRecord(
        conversation_id=conv.id,
        visitor_message_id=visitor_msg.id,
        reply_message_id=ai_msg.id,
        result=result,
    )