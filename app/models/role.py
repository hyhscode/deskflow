from typing import TYPE_CHECKING

from sqlalchemy import Boolean,String
from sqlalchemy.orm import Mapped,mapped_column,relationship

from app.db.base import Base
from app.models.associations import role_permissions,user_roles

# 同 user.py 的道理：只在类型检查时导入，运行时不用，避免循环导入。
if TYPE_CHECKING:
    from app.models.user import User

class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    name: Mapped[str] = mapped_column(String(50))

    description: Mapped[str | None] = mapped_column(String(200))
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    users: Mapped[list["User"]] = relationship(
        secondary=user_roles,        
        back_populates="roles",       
    )
    permissions: Mapped[list["Permission"]] = relationship(
        secondary=role_permissions,
        back_populates="roles",
    )

class Permission(Base):
    __tablename__ = "permissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    resource: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(String(200))
    roles: Mapped[list[Role]] = relationship(
        secondary=role_permissions,
        back_populates="permissions",
    )