from datetime import datetime 
from pydantic import BaseModel

class TicketOut(BaseModel):
    id: int
    title: str
    category: str
    priority: str                    # P0 / P1 / P2
    status: str                      # pending / assigned / processing / resolved / closed
    assignee_id: int | None
    created_at: datetime
    first_response_at: datetime | None

class MessageItem(BaseModel):
    id: int
    sender: str                      # visitor / ai / agent
    content: str
    created_at: datetime

class TicketDetailOut(TicketOut):

    summary: str | None
    conversation_id: int
    assignee_name: str | None
    messages: list[MessageItem] = []

class ReplyIn(BaseModel):
    """客服回复的请求体。"""
    content: str

class StatusIn(BaseModel):

    target: str