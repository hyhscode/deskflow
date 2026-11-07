import httpx
import numpy as np

from app.core.config import settings

TIMEOUT_SECONDS = 30
BATCH_SIZE = 32 

class EmbeddingError(Exception):
    pass


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, 0), dtype="float32")

    if not settings.embedding_api_key:
        raise EmbeddingError("未配置 EMBEDDING_API_KEY")

    url = f"{settings.embedding_base_url.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.embedding_api_key}",
        "Content-Type": "application/json",
    }

    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        try:
            resp = httpx.post(
                url,
                json={"model": settings.embedding_model, "input": batch},
                headers=headers,
                timeout=TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            raise EmbeddingError(str(exc)[:300]) from exc

        vectors.extend(item["embedding"] for item in data["data"])

    arr = np.array(vectors, dtype="float32")

    # 归一化：每行除以自己的长度。之后 faiss 的 IndexFlatIP 内积 = 余弦
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0        # 防除零
    return arr / norms


def embed_query(text: str) -> np.ndarray:
    """单条文本 → 一维向量。"""
    return embed_texts([text])[0]