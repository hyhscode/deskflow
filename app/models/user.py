from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.associations import user_roles

# TYPE_CHECKING 在运行时永远是 False，所以这个 import 实际上【不会执行】。
# 它的唯一作用是让编辑器和 mypy 知道 Role 是什么类型，从而消除红线、
# 并且能对 Mapped[list["Role"]] 做类型检查。
# 为什么不直接 from app.models.role import Role：
#     role.py 里也引用了 "User"，直接互相 import 会循环导入（ImportError）。
if TYPE_CHECKING:
    from app.models.role import Role

class User(Base):
    __tablename__ = "users"
    id:Mapped[int] = mapped_column(primary_key=True)
    username:Mapped[str] = mapped_column(String(50),unique=True,index=True)
    password_hash:Mapped[str] = mapped_column(String(255))
    real_name: Mapped[str | None] = mapped_column(String(50))
    email:Mapped[str | None] = mapped_column(String(120))
    phone:Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    skills: Mapped[list[str] | None] = mapped_column(JSON)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #时间戳
    created_at:Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda:datetime.now(timezone.utc),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── 关系：这个人有哪些角色 ──
    # 注意：它不是一列数据，users 表【不会】多出 roles 这一列。
    # lazy="selectin"：查用户时用一条额外 SQL 批量把角色一起查出来，避免 N+1。
    roles: Mapped[list["Role"]] = relationship(
        secondary=user_roles,
        back_populates="users",
        lazy="selectin",
    )


class UserStatus:
    ACTIVE = "active"
    DISABLED = "disabled"