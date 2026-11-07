from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.core.config import settings
from app.services.callbacks import DbLogHandler

TIMEOUT_SECONDS = 20

class LLMError(Exception):
    pass

def _build_llm(temperature:float,max_tokens:int) -> ChatOpenAI:
    if not settings.llm_api_key:
        raise LLMError("未配置 LLM_API_KEY")

    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=temperature,      # 越低越稳定
        max_tokens=max_tokens,
        timeout=TIMEOUT_SECONDS,
    )

def run_text(
    system: str,
    user_input: str,
    scene: str,
    db=None,
    trace_id: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 500,
) -> str:
    try:
        chain = (
            ChatPromptTemplate.from_messages([
                ("system", system),
                ("user", "{input}"),
            ])
            | _build_llm(temperature, max_tokens)
            | StrOutputParser()
        )
        text = chain.invoke(
            {"input": user_input},
            config={"callbacks": [DbLogHandler(db, scene, trace_id)]},
        )
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(str(exc)[:300]) from exc

    text = (text or "").strip()
    if not text:
        raise LLMError("模型返回空内容")     # 限流时会出现
    return text


def run_structured(
    system: str,
    user_input: str,
    schema: type[BaseModel],
    scene: str,
    db=None,
    trace_id: str | None = None,
    max_tokens: int = 400,
) -> BaseModel:
    try:
        model = _build_llm(0.0, max_tokens).with_structured_output(
            schema,
            method="function_calling",   # ★ DeepSeek 必须显式指定，默认的 json_schema 会 400
        )
        result = model.invoke(
            [("system", system), ("user", user_input)],
            config={"callbacks": [DbLogHandler(db, scene, trace_id)]},
        )
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(str(exc)[:300]) from exc

    if result is None:
        raise LLMError("结构化输出解析失败")
    return result