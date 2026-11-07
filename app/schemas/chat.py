from pydantic import BaseModel

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