"""DeskFlow 应用入口（uvicorn 的启动目标：app.main:app）

============================================================
【这个文件讲什么】

一个 FastAPI 应用最小能跑起来，只需要三块：
    1. app = FastAPI()              造应用
    2. @app.get(...) 这样的装饰器    挂接口
    3. uvicorn 把它跑起来            这步在命令行做，不在代码里

今天这个文件多了两块，都是为了"像个真项目"：
    4. lifespan    启动/关闭时干点事（打印日志、以后建表连 Redis）
    5. APIRouter   接口分组（现在只有一组"系统"，以后会有 chat/desk/admin）

⚠️ 这是"临时版"配置读取：直接用 os.getenv。
   等配置项超过 5 个（明天 S1 就会超），要抽成 app/core/config.py，
   用 pydantic-settings 统一管理。现在先用最笨的办法，是为了看清它在干什么。

============================================================
【怎么跑】

    cd C:\\Users\\Administrator\\WorkBuddy\\python_study\\deskflow
    .venv\\Scripts\\python.exe -m uvicorn app.main:app --reload --port 8077

    --reload      改代码自动重启（开发用，生产别开）
    app.main:app  含义：app 包 → main 模块 → 里面叫 app 的变量
                  所以那个变量必须叫 app，改名字就启动不了

    然后打开 http://127.0.0.1:8077/docs

============================================================
【本文件的包 / 函数速查】

os（Python 标准库）
    os.getenv(键名, 默认值)
        读环境变量。有就返回字符串，没有就返回默认值。
        注意：读到的永远是【字符串】。想要数字得自己 int() 转，
        这就是为什么后面要换 pydantic-settings（它能按类型自动转）

python-dotenv（第三方，pip 装的）
    load_dotenv()
        把 .env 文件里的 KEY=VALUE 塞进"环境变量"里。
        这样 os.getenv 才读得到。
        ⚠️ 必须在任何 os.getenv 之前调用，因为它只是"加载"，
          加载晚了，前面的 getenv 已经读空了

contextlib.asynccontextmanager（Python 标准库）
    把一个 async 函数变成"可以用在 lifespan 上的上下文管理器"。
    它靠函数里的 yield 分界：
        yield 之前 = 服务开始接客之前执行
        yield 之后 = 服务关闭时执行

fastapi.FastAPI（第三方）
    应用实例。常用参数：
        title      /docs 页面顶部的标题
        version    版本号，会出现在 /docs 和 /openapi.json
        lifespan   启动/关闭钩子
        docs_url   文档路径；设为 None 就在生产环境关掉文档

fastapi.APIRouter（第三方）
    接口分组器。prefix 给这一组接口统一加路径前缀，
    tags 让 /docs 里按组折叠显示。
    为什么不用 @app.get 直接写？因为接口到 40 个时会全堆在一个文件里。

FastAPI.include_router(router)
    把分组"挂"到应用上。不挂等于白写，/docs 里不会出现。

@app.get(路径)（装饰器）
    声明"这个函数处理这个路径的 GET 请求"。
    函数 return 一个 dict，FastAPI 自动转成 JSON 返回（不用自己 json.dumps）
============================================================
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI

# 把 .env 里的配置加载进环境变量。必须在下面读配置之前调用。
load_dotenv()

# 读配置。第二个参数是"读不到时用什么默认值"。
# 默认值很重要：没有它，配置漏了就是 None，报错会出现在很奇怪的地方。
APP_ENV = os.getenv("APP_ENV", "dev")
APP_NAME = os.getenv("APP_NAME", "DeskFlow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动 / 关闭钩子。

    这个函数被 yield 切成两段：
        ┌─ yield 之前 ─┐  服务还没开始接客，在这里做准备
        │    yield     │  分界线
        └─ yield 之后 ─┘  服务已停止接客，在这里收尾

    为什么不能写成普通函数？因为 yield 是"执行到一半暂停、等会儿接着往下跑"，
    普通函数没这个能力，return 一次就结束了。
    忘了写 yield 会直接报错（这个函数就不再是"生成器"了）。

    ⚠️ 后面这里会加：检查数据库表、预热知识库缓存、连 Redis、关连接池。
       现在只打印，是为了让你看见它什么时候执行。
    """
    print(f"[启动] {APP_NAME} 环境={APP_ENV}")

    yield

    print("[关闭] 服务已停止")


app = FastAPI(
    title=f"{APP_NAME} · 智能客服工单平台",
    version="0.1.0",
    lifespan=lifespan,
    # 生产环境把文档关掉：/docs 会暴露全部接口结构，没必要给外人看
    docs_url="/docs" if APP_ENV == "dev" else None,
)


# ══════════════════════════════════════════════════════════
# 系统类接口（健康检查）
# ══════════════════════════════════════════════════════════
# prefix="/api" 的作用：这一组下所有接口路径自动加 /api 前缀。
# 好处是以后 Nginx 只要转发 /api/* 就行，静态页面（chat.html 那些）不经过后端。
health_router = APIRouter(prefix="/api", tags=["系统"])


@health_router.get("/health")
def health():
    """健康检查。返回 200 就代表服务活着。

    为什么故意【不】查数据库：
        这个接口要毫秒级返回，会被 Docker / 监控每隔几秒调一次。
        如果它查库，数据库一慢它自己就超时，监控会误判成"整个服务死了"，
        实际只是库慢。所以"服务活着"和"依赖健康"要拆成两个接口。

    面试可以这么说：健康检查只验证进程存活，依赖健康单独暴露，
    避免把下游故障放大成上游不可用。
    """
    return {
        "status": "ok",
        "app": APP_NAME,
        "env": APP_ENV,
        "version": app.version,
    }


# 把分组挂到应用上。不写这行，上面的接口在 /docs 里根本不出现
app.include_router(health_router)
