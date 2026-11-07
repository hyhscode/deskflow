from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.chat import ChatMessageIn,ChatMessageOut,SuggestionOut
from app.services.pipeline import handle_message

router = APIRouter("/message",responses_model=ChatMessageOut)

def send_message(data:ChatMessageIn,db:Session = Depends(get_db)):
    result = handle_message(db,data.content)
    return ChatMessageOut(
        type=result.type,
        content=result.content,
        suggestions=[SuggestionOut(**s) for s in result.suggestions],
        citation=result.citation,
    )
    