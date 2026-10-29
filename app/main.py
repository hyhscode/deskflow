"""应用入口：这个文件是 uvicorn 的启动目标（app.main:app）。

============================================================
【这个文件在干什么】

只做四件事，一行业务逻辑都不放：
    1. 创建 FastAPI 实例（app = FastAPI(...)）
    2. 挂 lifespan：启动时做什么、关闭时做什么
    3. 注册路由（现在是空的，明天开始往里加）
    4. 提供 /api/health 健康检查

为什么业务逻辑一行都不放这里？
    因为入口文件是"接线板"，不是"电器"。接线板一改，整个项目都要重启验证；
    逻辑放在 services/ 里，可以单独 pytest，改坏了立刻知道。

============================================================
【本文件的包 / 函数速查】

fastapi.FastAPI —— 第三方
    创建应用实例。参数：
        title    /docs 页面顶部显示的标题
        version  版本号，会显示在 /docs 和 /openapi.json 里
        lifespan 启动/关闭钩子（见下）
        docs_url 文档地址；设为 None 就在生产环境关掉

fastapi.APIRouter —— 第三方
    路由分组器。把一组接口写在一个文件里，再用 app.include_router() 挂上去。
    名字拆解：API + Router（路由器）

@asynccontextmanager —— Python 标准库 contextlib
    把一个"带 yield 的函数"变成上下文管理器，专门给 lifespan 用。
    yield 之前 = 启动时执行，yield 之后 = 关闭时执行。
    名字拆解：async 异步 + context 上下文 + manager 管理器

============================================================
【怎么跑】

    cd python_study\\deskflow
    .venv\\Scripts\\python.exe -m uvicorn app.main:app --reload --port 8077

    --reload     改代码自动重启（只在开发时用，生产别开）
    app.main:app 意思是"app 包 → main 模块 → 里面叫 app 的变量"
============================================================
"""

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动/关闭钩子。

    注意：这个函数必须"先 yield 再返回"，yield 是分界线。
    写成普通函数或者忘了 yield，FastAPI 启动时会直接报错。
    """
    # ── yield 之前：服务开始接收请求之前执行 ──
    # 后面会在这里做：建表检查、预热知识库缓存、初始化 Redis 连接池
    print(f"[启动] {settings.app_name} 环境={settings.app_env} 数据库={settings.database_url}")

    yield  # ← 分界线：这行之后，服务开始对外提供服务

    # ── yield 之后：服务关闭时执行 ──
    # 后面会在这里做：关闭数据库连接池、关 Redis
    print("[关闭] 连接已释放")


app = FastAPI(
    title=f"{settings.app_name} · 智能客服工单平台",
    version="0.1.0",
    lifespan=lifespan,
    # 生产环境把文档关掉：/docs 会暴露所有接口结构，没必要给外人看
    docs_url="/docs" if settings.is_dev else None,
    redoc_url=None,  # 有 /docs 就够了，redoc 是重复的
)


# ── 健康检查 ──
# 单独一个 router，因为运维（Docker healthcheck、Nginx、监控）只需要这一个接口。
# 为什么必须有：部署后第一件事就是"服务到底活着没"，没有这个接口只能靠猜。
health_router = APIRouter(prefix="/api", tags=["系统"])


@health_router.get("/health")
def health():
    """返回服务状态。返回 200 就代表活着。

    注意这里不查数据库。健康检查要快（毫秒级），查库会拖慢它，
    而且数据库挂了应该由 /api/health/db 这种单独接口暴露，
    否则监控会误判成"整个服务死了"。
    """
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "version": app.version,
    }


app.include_router(health_router)
