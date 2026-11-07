from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Role, User


def list_users(db: Session, keyword: str | None = None) -> list[User]:
    stmt = select(User).where(User.is_deleted == False)
    if keyword:
        stmt = stmt.where(User.username.contains(keyword))
    return db.execute(stmt.order_by(User.id)).scalars().all()


def create_user(db: Session, username: str, password: str,
                real_name: str | None = None, email: str | None = None,
                phone: str | None = None, role_codes: list[str] | None = None,
                skills: list[str] | None = None) -> User:
    exists = db.execute(select(User).where(User.username == username)).scalars().first()
    if exists is not None:
        raise ValueError(f"用户名 {username} 已存在")

    user = User(
        username=username,
        password_hash=hash_password(password),   # 永远不存明文
        real_name=real_name, email=email, phone=phone,
        skills=skills or [], status="active", is_deleted=False,
    )

    role_codes = role_codes or []
    if role_codes:
        roles = db.execute(select(Role).where(Role.code.in_(role_codes))).scalars().all()
        _check_missing_roles(role_codes, roles)
        user.roles = list(roles)

    db.add(user)
    db.flush()      # 拿 id，写审计日志要用
    return user


def set_roles(db: Session, user: User, role_codes: list[str]) -> list[str]:
    """覆盖角色（不是追加）。"""
    roles = db.execute(select(Role).where(Role.code.in_(role_codes))).scalars().all()
    _check_missing_roles(role_codes, roles)
    user.roles = list(roles)
    return sorted(role_codes)


def disable_user(db: Session, user: User) -> User:
    """禁用（软删除，不删数据）。"""
    user.status = "disabled"
    return user


def _check_missing_roles(role_codes: list[str], roles: list[Role]) -> None:
    """不存在的角色要报错，不能静默忽略。"""
    found = {r.code for r in roles}
    missing = set(role_codes) - found
    if missing:
        raise ValueError(f"角色不存在: {sorted(missing)}")
