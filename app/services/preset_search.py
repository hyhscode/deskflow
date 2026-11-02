from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PresetQa

TOP_K = 3

class PresetHit(BaseModel):
    """一条命中的预设。"""
    preset_id: int
    question: str
    answer: str
    matched_keywords: list[str]

def search_presets(db: Session, query: str, top_k: int = TOP_K) -> list[PresetHit]:
    presets = db.execute(
        select(PresetQa).where(PresetQa.enabled == True)
    ).scalars().all()
    scored = []
    for preset in presets:
        keyword_pool = [preset.question, *(preset.variants or [])]
        matched = [kw for kw in keyword_pool if kw and kw in query]

        if matched:
            scored.append((len(matched), preset.sort_order, -preset.ask_count, preset, matched))
            scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=False)

            return [
        PresetHit(
            preset_id=preset.id,
            question=preset.question,
            answer=preset.answer,
            matched_keywords=matched,
        )
        for _, _, _, preset, matched in scored[:top_k]
    ]