from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services.answer import answer_with_kb
from app.services.kb_search import search_kb
from app.services.preset_search import search_presets

class PipelineResult(BaseModel):
    type:str
    content: str = ""
    suggestions: list[dict] = []
    citation:str | None = None

def handle_message(db:Session,question:str) -> PipelineResult:
    presets = search_presets(db,question)
    if presets:
        return PipelineResult(
            type="suggest",
            content="我找到了这几条，你想问哪个？",
            suggestions=[
                {"preset_id": p.preset_id, "question": p.question}
                for p in presets
            ],
        )

    kb = search_kb(db,question)
    if kb.tier == "suggest":
        answer = answer_with_kb(question,kb.hits,db=db)
        return PipelineResult(
            type="answer",
            content=answer.content,
            citation=answer.citations[0]["title"] if answer.citations else None,
        )

    return PipelineResult(
        type="ticket",
        content="这个问题我帮你转接人工客服。",
    )