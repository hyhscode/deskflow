
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class KbCategory(Base):
    """知识分类。分类的作用是让检索先缩小范围，不用全库比。"""

    __tablename__ = "kb_categories"

    id: Mapped[int] = mapped_column(primary_key=True)

    # code 和 name 分开，跟 Role 一个道理：
    # code = "billing"（程序用，稳定），name = "账单发票"（界面显示，可改）
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    name: Mapped[str] = mapped_column(String(50))

    # 排序序号，小的在前。默认 0 表示"没特意指定就排在最前"
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # 停用某个分类后，它下面的知识不参与检索，但数据还在
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    articles: Mapped[list["KbArticle"]] = relationship(back_populates="category")


class KbArticle(Base):
    """一条知识。检索的基本单位 —— 一条知识就是一个 chunk。"""

    __tablename__ = "kb_articles"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 标题单独加索引：检索时按标题算分权重最高（0.45）
    title: Mapped[str] = mapped_column(String(200), index=True)

    category_id: Mapped[int] = mapped_column(ForeignKey("kb_categories.id"), index=True)

    content: Mapped[str] = mapped_column(Text)

    # 标签，例如 ["发票", "开票"]。JSON 存，因为只在 Python 里算命中，不做 SQL 统计。
    tags: Mapped[list[str] | None] = mapped_column(JSON)


    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)

    # draft（草稿）/ published（已发布）/ archived（归档）
    # 只有 published 参与检索 —— 这条规则写在检索代码里，不是写在这里
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)


    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    useful_count: Mapped[int] = mapped_column(Integer, default=0)
    useless_count: Mapped[int] = mapped_column(Integer, default=0)

    # ── 软删除 + 回收站 ──
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # 复合索引：(分类, 状态) —— 检索时的固定条件就是"这个分类里已发布的"
    __table_args__ = (
        Index("ix_kb_articles_cat_status", "category_id", "status"),
    )

    category: Mapped["KbCategory"] = relationship(back_populates="articles")
