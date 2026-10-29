"""配置中心：所有"会变的值"都从这里出去，别在业务代码里写死。

============================================================
【这个文件在干什么】

把 .env 里的配置读进一个对象 settings，全项目都用 settings.xxx 访问。

为什么不能到处 os.getenv("DATABASE_URL")？
    1. 拼错名字不报错，只在运行时拿到 None → 500，很难查
    2. 没有默认值、没有类型转换，拿到的一定是字符串
    3. 想在测试里换一套配置，得改环境变量，很脏

============================================================
【本文件的包 / 函数速查】

pydantic_settings.BaseSettings —— 第三方（pip 装的 pydantic-settings）
    自动读取 .env，并把每个字段按"类型注解"转好：
    注解写 int，读到的 "480" 会变成 480（而不是字符串 "480"）

    model_config = SettingsConfigDict(env_file=".env")
        告诉它去哪个文件找变量

pydantic.SecretStr —— 第三方（pydantic 自带）
    专门包密码/密钥的类型。打印时会显示 **，避免日志里泄露 key

functools.lru_cache —— Python 标准库
    缓存函数结果。`@lru_cache` 让 get_settings() 只真正执行一次，
    后面每次调用直接返回第一次造好的对象。
    为什么需要：配置读一次就够，每个请求都重新读文件是浪费

    名字拆解：lru = Least Recently Used（最近最少使用，一种淘汰策略）
              cache = 缓存
============================================================
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """一个字段对应 .env 里的一行。名字大小写不敏感。"""

    # ── 运行环境 ──
    # dev / prod。用它控制"要不要开 SQL 日志""要不要暴露 /docs"
    app_env: str = "dev"

    app_name: str = "DeskFlow"

    # ── 数据库 ──
    # sqlite:///./deskflow.db 里三个斜杠的意思是：后面是相对路径
    database_url: str = "sqlite:///./deskflow.db"

    # ── 认证 ──
    # 用 SecretStr 包一层：即使不小心 print(settings)，也只会看到 '**********'
    # 真要取值必须显式调 .get_secret_value()
    secret_key: SecretStr = SecretStr("dev-only-not-for-production")
    token_expire_minutes: int = 480  # 8 小时

    # ── LLM ──
    llm_api_key: str = ""  # 空字符串 = 没配 key，走降级模板回答
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"

    # 允许 @property 用 is_dev 这种"算出来的值"
    model_config = SettingsConfigDict(
        env_file=".env",          # 去这个文件找变量
        env_file_encoding="utf-8",
        extra="ignore",           # .env 里有多余的键不报错（比如以后加的配置）
    )

    @property
    def is_dev(self) -> bool:
        """是不是开发环境。业务代码里用 settings.is_dev 判断，比到处比字符串干净。"""
        return self.app_env == "dev"


@lru_cache
def get_settings() -> Settings:
    """取配置单例。第一次调用时读 .env，之后都返回同一个对象。

    注意：@lru_cache 意味着测试里想换配置，必须调 get_settings.cache_clear()。
    这是它的代价，也是它"只读一次"的代价。
    """
    return Settings()


# 模块级单例：其他文件直接 `from app.core.config import settings` 就行
settings = get_settings()
