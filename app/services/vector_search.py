import threading
from pathlib import Path

import faiss
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KbArticle
from app.services.embedding import embed_query, embed_texts

INDEX_PATH = Path(__file__).resolve().parents[2] / "data" / "kb.index"

_index = None          # 进程内缓存，避免每次检索都读文件
_lock = threading.Lock()

class VectorIndexMissing(Exception):
    pass

def _load() -> faiss.Index:
    global _index
    if _index is not None:
        return _index

    with _lock:                    # 双检锁：多线程同时进来只读一次
        if _index is None:
            if not INDEX_PATH.exists():
                raise VectorIndexMissing(f"索引不存在：{INDEX_PATH}")
            _index = faiss.read_index(str(INDEX_PATH))
    return _index

def build_index(db: Session) -> int:
    articles = db.execute(
        select(KbArticle).where(
            KbArticle.status == "published",
            KbArticle.is_deleted == False,
        )
    ).scalars().all()

    if not articles:
        raise VectorIndexMissing("没有可索引的知识")

    # 一条知识拼成一段文本：标题权重靠前，标签补同义词，正文取前 300 字
    texts = []
    for a in articles:
        tags = " ".join(a.tags or [])
        texts.append(f"{a.title}\n{tags}\n{(a.content or '')[:300]}")

    vectors = embed_texts(texts)

    base = faiss.IndexFlatIP(vectors.shape[1])
    index = faiss.IndexIDMap2(base)
    index.add_with_ids(vectors, np.array([a.id for a in articles], dtype="int64"))

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(INDEX_PATH))

    global _index
    _index = index              # 立刻生效，不用重启
    return len(articles)


def search_vectors(question: str, top_k: int = 5) -> list[tuple[int, float]]:
    """向量检索。返回 [(article_id, 相似度)]，相似度 0~1，越大越像。"""
    index = _load()
    query_vector = embed_query(question).reshape(1, -1)

    # index.ntotal 是索引里的条数；top_k 超过它会报错
    scores, ids = index.search(query_vector, min(top_k, index.ntotal))

    results = []
    for article_id, score in zip(ids[0], scores[0]):
        if article_id == -1:      # faiss 用 -1 表示"不够 k 条"
            continue
        results.append((int(article_id), float(score)))
    return results