from pydantic import BaseModel
from datetime import datetime

class ChatMessageIn(BaseModel):
    visitor_key:str
    content:str

class ChatSelectIn(BaseModel):
    """客户点选预设候选。

    只带 preset_id，不带 content：客户点的是"哪一条"，
    答案由后端按 id 取，前端传什么内容都不影响结果（防篡改）。
    """
    visitor_key: str
    preset_id: int

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
