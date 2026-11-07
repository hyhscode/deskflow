from time import perf_counter

from langchain_core.callbacks import BaseCallbackHandler

from app.core.config import settings
from app.models import LlmLog

class DbLogHandler(BaseCallbackHandler):
    def __init__(self,db,scene:str,trace_id:str | None = None) ->None:
        self.db = db
        self.scene = scene          # answer / summary / draft / qa
        self.trace_id = trace_id
        self._started = perf_counter()

    def on_llm_end(self, response, **kwargs) -> None:
        """模型正常返回。"""
        prompt_tokens, completion_tokens = self._extract_usage(response)
        self._write(True, prompt_tokens, completion_tokens, None)

    def on_llm_error(self, error, **kwargs) -> None:
        
        self._write(False, 0, 0, str(error)[:500])

    @staticmethod
    def _extract_usage(response) -> tuple[int,int]:
        try:
            message = response.generations[0][0].message
            usage = getattr(message, "usage_metadata", None) or {}
            return usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        except Exception:
            return 0, 0

    def _write(self, success: bool, prompt_tokens: int,
               completion_tokens: int, error_msg: str | None) -> None:
        if self.db is None:
            return
        latency = int((perf_counter() - self._started) * 1000)
        self.db.add(LlmLog(
            trace_id=self.trace_id,
            scene=self.scene,
            model=settings.llm_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency,
            success=success,
            error_msg=error_msg,
        ))