from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PresetQa
from app.services.text import cosine, is_contained, tokenize

PRESET_MATCH_THRESHOLD = 0.55
PRESET_TOP_K = 3

class PresetHit(BaseModel):
    preset_id: int
    question: str
    answer: str
    score: float
    matched_by: str 

def _score_preset(query: str, preset: PresetQa) -> tuple[float, str]:
    phrases = [preset.question, *(preset.variants or [])]
    for phrase in phrases:
        if is_contained(query, phrase):
            return 1.0, "exact"
        query_grams = tokenize(query)
        best = 0.0
        for phrase in phrases:
            score = cosine(query_grams, tokenize(phrase))
            if score > best:
                best = score

        return round(best, 4), "fuzzy"


def search_presets(
    db: Session,
    query: str,
    category: str | None = None,
    top_k: int = PRESET_TOP_K,
) -> list[PresetHit]:
    conditions = [PresetQa.enabled == True]

    if category:
        conditions.append(PresetQa.category == category)

    presets = db.execute(select(PresetQa).where(*conditions)).scalars().all()

    scored: list[tuple[float, str, PresetQa]] = []

    for preset in presets:
        score, matched_by = _score_preset(query, preset)
        if score >= PRESET_MATCH_THRESHOLD:
            scored.append((score, matched_by, preset))

    if not scored:
        return []
    scored.sort(
        key=lambda item: (
            -item[0],
            item[2].sort_order,
            -item[2].ask_count,
        )
    )
    return [
        PresetHit(
            preset_id=preset.id,
            question=preset.question,
            answer=preset.answer,
            score=score,
            matched_by=matched_by,
        )
        for score, matched_by, preset in scored[:top_k]
    ]