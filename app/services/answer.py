import time 

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import LlmLog
from app.services.kb_search import KbHit

DISCLAIMER = "\n\n以上内容仅供参考，如未解决可点右下角「转人工」。"
MAX_CONTEXT = 3
LLM_TIMEOUT = 20

class AnswerResult(BaseModel):
    content:str
    citations:list[dict]
    source: str
    latency_ms:int

def _build_prompt(question:str,hits:list[KbHit]) -> list[dict]:
    context_blocks = []
    for i, hit in enumerate(hits[:MAX_CONTEXT],start=1):
        context_blocks.append(
            f"【资料{i}】标题：{hit.title}\n内容：{hit.content}"
        )
    context_text = "\n\n".join(context_blocks)

    system_prompt = (
        "你是 SaaS 公司的客服助手。回答规则：\n"
        "1. 只能依据下面【资料】里的内容回答，资料里没有的一律不要编造；\n"
        "2. 如果资料不足以回答，就直接说「这个问题需要人工客服处理」；\n"
        "3. 回答控制在 80 字以内，用简洁的客服口吻，不要用 markdown 语法；\n"
        "4. 不要向客户提及「资料」「文档」这类词，直接给答案；\n"
        "5. 不要自己加任何免责声明或落款，那部分由系统添加。"
    )

    user_prompt = f"{context_text}\n\n【客户问题】{question}"

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

def _call_llm(messages:list[dict]) -> tuple[str,int,int]:
    import httpx
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 300,
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=LLM_TIMEOUT) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()

    data = resp.json()
    text = data["choices"][0]["message"]["content"].strip()
    usage = data.get("usage", {})
    return text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)

def answer_with_kb(
    question:str,
    hits:list[KbHit],
    db:Session | None = None,
    trace_id:str |None = None,

) -> AnswerResult:
    started = time.perf_counter()

    if not hits:
        return AnswerResult(
            content="这个问题我需要请人工客服同事帮您看一下。"+ DISCLAIMER,
            citations=[],
            source="fallback",
            latency_ms=0,
        )

    if not settings.llm_api_key:
        return _fallback(hits, started, reason="未配置 LLM_API_KEY")

    try:
        messages = _build_prompt(question, hits)
        text, prompt_tokens, completion_tokens = _call_llm(messages)

        latency = int((time.perf_counter() - started) * 1000)

        if not text:
            raise ValueError("模型返回空内容")

        _log(db, trace_id, prompt_tokens, completion_tokens, latency, True, None)

        return AnswerResult(
            content=text + DISCLAIMER,          # ← 免责声明由代码加，不经过模型
            citations=[
                {"article_id": h.article_id, "title": h.title}
                for h in hits[:MAX_CONTEXT]
            ],
            source="llm",
            latency_ms=latency,
        )

    except Exception as exc:
        latency = int((time.perf_counter() - started) * 1000)
        _log(db, trace_id, 0, 0, latency, False, str(exc)[:500])
        return _fallback(hits, started, reason=str(exc))

def _fallback(hits: list[KbHit], started: float, reason: str) -> AnswerResult:
    body = hits[0].content.strip()[:200]
    return AnswerResult(
        content=body + DISCLAIMER,
        citations=[{"article_id": hits[0].article_id, "title": hits[0].title}],
        source="fallback",
        latency_ms=int((time.perf_counter() - started) * 1000),
    )

def _log(
    db: Session | None,
    trace_id: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    success: bool,
    error_msg: str | None,
) -> None:
    if db is None:
        return
    db.add(LlmLog(
        trace_id=trace_id,
        scene="answer",
        model=settings.llm_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        success=success,
        error_msg=error_msg,
    ))
    db.commit()