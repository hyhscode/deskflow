
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OperationLog(Base):

    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int | None] = mapped_column(Integer, index=True)


    user_name: Mapped[str | None] = mapped_column(String(50))

    # 动作：create / update / delete / login / reset_password
    action: Mapped[str] = mapped_column(String(32), index=True)

    target_type: Mapped[str | None] = mapped_column(String(32), index=True)
    target_id: Mapped[int | None] = mapped_column()

    detail: Mapped[dict | None] = mapped_column(JSON)

    ip: Mapped[str | None] = mapped_column(String(45))       # 45 是 IPv6 的最大长度
    user_agent: Mapped[str | None] = mapped_column(String(255))

    # 日志表最常按时间查（"昨天下午谁改的"），所以时间列建索引
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class LlmLog(Base):
    """每次调用大模型的记录。成本、性能、错误都从这里看。"""

    __tablename__ = "llm_logs"

    id: Mapped[int] = mapped_column(primary_key=True)


    trace_id: Mapped[str | None] = mapped_column(String(64), index=True)

    # 哪一步调的：classify（分类）/ answer（回答）/ qa（质检）
    # 拆词：scene = 场景
    scene: Mapped[str] = mapped_column(String(16), index=True)

    model: Mapped[str] = mapped_column(String(64))

    # 输入和输出的 token 数，算钱用
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)

    latency_ms: Mapped[int | None] = mapped_column(Integer)

    success: Mapped[bool] = mapped_column(Boolean, default=True)

    # 失败原因，成功时是 None
    error_msg: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )


class SystemConfig(Base):

    __tablename__ = "system_configs"

    id: Mapped[int] = mapped_column(primary_key=True)


    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # 值一律存字符串，读的时候按 value_type 转
    value: Mapped[str | None] = mapped_column(String(255))


    value_type: Mapped[str] = mapped_column(String(16), default="string")

    description: Mapped[str | None] = mapped_column(String(255))

    # 是否允许在后台修改。有些配置（如系统版本）只读。
    editable: Mapped[bool] = mapped_column(Boolean, default=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
