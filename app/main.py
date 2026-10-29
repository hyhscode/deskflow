from app.core.config import settings
from contextlib import asynccontextmanager
from fastapi import APIRouter,FastAPI


@asynccontextmanager
async def lifespan(app:FastAPI):
    print(f"[启动] {settings.app_name} 环境={settings.app_env}")
    yield
    print("[关闭] 服务已停止")

app = FastAPI(
    title=f"{settings.app_name} · 智能客服工单平台",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs"if settings.is_dev else None,
)

health_router = APIRouter(prefix="/api",tags=["系统"])

@health_router.get("/health")
def health():
    return{
        "status": "ok",           # 固定值，约定俗成
        "app": settings.app_name,          # 哪个应用
        "env": settings.app_env,           # 哪个环境（dev/prod）
        "version": app.version,
    }

app.include_router(health_router)