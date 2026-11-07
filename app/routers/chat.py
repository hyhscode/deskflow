from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session

from sqlalchemy import select
from app.models import Conversation, Message
from app.schemas.chat import ChatMessageIn, ChatMessageOut, MessageOut, SuggestionOut
from app.services.chat_svc import handle_and_save

from app.db.session import get_db
from app.schemas.chat import ChatMessageIn,ChatMessageOut,SuggestionOut
from app.services.pipeline import handle_message

router = APIRouter(prefix="/api/chat", tags=["访客端"])


@router.post("/message", response_model=ChatMessageOut)
def send_message(data:ChatMessageIn,db:Session = Depends(get_db)):
    record = handle_and_save(db,data.visitor_key,data.content)
    result = record.result

    return ChatMessageOut(
        type=result.type,
        content=result.content,
        suggestions=[SuggestionOut(**s) for s in result.suggestions],
        citation=result.citation,
    )

@router.get("/history",response_model=list[Message])
def get_history(visitor_key:str,db:Session = Depends(get_db)):
    conv = db.execute(
        select(Conversation)
        .where(Conversation.visitor_key == visitor_key, Conversation.status == "open")
        .order_by(Conversation.id.desc())
    ).scalars().first()

    if conv is None:
        return []

    messages = db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.id)          
    ).scalars().all()

    return [
        MessageOut(
            id=m.id,
            sender=m.sender,
            content=m.content,
            content_type=m.content_type,
            created_at=m.created_at,
        )
        for m in messages
    ]