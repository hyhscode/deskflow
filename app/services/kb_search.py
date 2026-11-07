from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KbArticle, KbCategory
from app.services.text import cosine, tokenize


WEIGHTS = {"title": 0.65, "tags": 0.35}
MATCH_THRESHOLD = 0.45
TOP_K = 3
NO_CATEGORY_FILTER = ("complaint", "consult")

class KbHit(BaseModel):
    article_id:int
    title:str
    content:str
    score:float

class KbResult(BaseModel):
    tier:str
    hits:list[KbHit]
    best_score:float

def search_kb(
    db:Session,
    question:str,
    category:str | None = None,
    top_k: int = TOP_K,
) -> KbResult:
    conditions = [KbArticle.status == "published", KbArticle.is_deleted == False]
    if category and category not in NO_CATEGORY_FILTER:
        cat_id = db.execute(
            select(KbCategory.id).where(KbCategory.code == category)
        ).scalar_one_or_none()

        if cat_id is not None:
            conditions.append(KbArticle.category_id == cat_id)

    articles = db.execute(select(KbArticle).where(*conditions)).scalars().all()

    query_grams = tokenize(question)
    scored:list[tuple[float,KbArticle]] = []

    for article in articles:
        title_score = cosine(query_grams,tokenize(article.title))
        tags_text = " ".join(article.tags or [])
        tags_score = cosine(query_grams,tokenize(tags_text))

        total = WEIGHTS["title"] * title_score + WEIGHTS["tags"] *tags_score

        if total > 0:
            scored.append((total,article))

    scored.sort(key=lambda item: item[0], reverse=True)

    hits = [
        KbHit(
            article_id=article.id,
            title=article.title,
            content=article.content or "",
            score=round(score, 4),      # 保留 4 位，日志里好读
        )
        for score, article in scored[:top_k]
    ]

    best_score = hits[0].score if hits else 0.0
    tier = "suggest" if best_score >= MATCH_THRESHOLD else "none"

    return KbResult(tier=tier, hits=hits, best_score=best_score)