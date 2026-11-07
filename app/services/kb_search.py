from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KbArticle, KbCategory
from app.services.text import cosine, tokenize
from app.models import KbArticle, KbCategory

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

VECTOR_THRESHOLD = 0.60    # 向量相似度阈值。实测：口语化问题普遍在 0.68~0.72
RRF_K = 60                 # RRF 的平滑常数，用行业默认值


def _rrf_fuse(
    keyword_hits: list[KbHit],
    vector_hits: list[tuple[int, float]],
) -> list[int]:
    scores: dict[int, float] = {}

    for rank, hit in enumerate(keyword_hits, start=1):
        scores[hit.article_id] = scores.get(hit.article_id, 0.0) + 1.0 / (RRF_K + rank)

    for rank, (article_id, _) in enumerate(vector_hits, start=1):
        scores[article_id] = scores.get(article_id, 0.0) + 1.0 / (RRF_K + rank)

    return [aid for aid, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)]


def search_kb_hybrid(
    db: Session,
    question: str,
    category: str | None = None,
    top_k: int = TOP_K,
) -> KbResult:
    # ① 关键词通道（已有实现，多取几条用于融合）
    keyword_result = search_kb(db, question, category=category, top_k=top_k + 3)

    # ② 向量通道
    try:
        from app.services.vector_search import search_vectors
        vector_hits = search_vectors(question, top_k=top_k + 3)
    except Exception:
        # 索引没建 / embedding 挂了 → 只用关键词，服务继续
        return keyword_result

    if not vector_hits:
        return keyword_result

    # ③ 向量命中但关键词没命中的，查库补成 KbHit（否则前端拿不到标题）
    known_ids = {h.article_id for h in keyword_result.hits}
    missing_ids = [aid for aid, _ in vector_hits if aid not in known_ids]
    extra: dict[int, KbHit] = {}
    if missing_ids:
        rows = db.execute(
            select(KbArticle).where(KbArticle.id.in_(missing_ids))
        ).scalars().all()
        score_map = dict(vector_hits)
        for row in rows:
            extra[row.id] = KbHit(
                article_id=row.id,
                title=row.title,
                content=row.content or "",
                score=round(score_map.get(row.id, 0.0), 4),
            )

    # ④ 融合排序
    merged = {h.article_id: h for h in keyword_result.hits}
    merged.update(extra)
    ordered_ids = _rrf_fuse(keyword_result.hits, vector_hits)

    hits = [merged[i] for i in ordered_ids if i in merged][:top_k]

    # ⑤ 分档：两个阈值各自独立，不融合
    best_keyword = keyword_result.best_score
    best_vector = vector_hits[0][1]
    tier = (
        "suggest"
        if best_keyword >= MATCH_THRESHOLD or best_vector >= VECTOR_THRESHOLD
        else "none"
    )

    return KbResult(
        tier=tier,
        hits=hits,
        best_score=round(max(best_keyword, best_vector), 4),
    )