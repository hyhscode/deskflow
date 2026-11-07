from pydantic import BaseModel
from datetime import datetime

class ChatMessageIn(BaseModel):
    visitor_key:str
    content:str

class SuggestionOut(BaseModel):
    question:str
    preset_id:int | None = None
    article_id: int | None= None

class ChatMessageOut(BaseModel):
    type: str                                           
    content: str = ""                                      
    suggestions: list[SuggestionOut] = []                  
    citation: str | None = None


class MessageOut(BaseModel):
    """一条历史消息。"""
    id: int
    sender: str
    content: str
    content_type: str
    created_at: datetime
