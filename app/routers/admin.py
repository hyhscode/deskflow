from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.perms import require_perm
from app.db.session import get_db
from app.models import Role, User
from app.schemas.admin import RoleOut, RolesIn, UserCreateIn, UserOut
from app.services.audit import client_ip, write_audit
from app.services.user_svc import (
    create_user, disable_user, list_users, set_roles,
)

router = APIRouter(prefix="/api/admin", tags=["后台·员工"])


def _to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id, username=user.username, real_name=user.real_name,
        email=user.email, phone=user.phone, status=user.status,
        skills=user.skills, roles=[r.code for r in user.roles],
        created_at=user.created_at,
    )


@router.get("/roles", response_model=list[RoleOut])
def get_roles(
    user: User = Depends(require_perm("user:read")),
    db: Session = Depends(get_db),
):
    """角色字典。前端建员工时要选角色。"""
    rows = db.execute(select(Role).order_by(Role.id)).scalars().all()
    return [RoleOut(id=r.id, code=r.code, name=r.name) for r in rows]


@router.get("/users", response_model=list[UserOut])
def get_users(
    keyword: str | None = None,
    user: User = Depends(require_perm("user:read")),
    db: Session = Depends(get_db),
):
    return [_to_out(u) for u in list_users(db, keyword)]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def post_user(
    data: UserCreateIn,
    request: Request,
    user: User = Depends(require_perm("user:write")),
    db: Session = Depends(get_db),
):
    try:
        new_user = create_user(
            db, data.username, data.password, data.real_name,
            data.email, data.phone, data.role_codes, data.skills,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc

    write_audit(
        db, action="create", user_id=user.id,
        user_name=user.real_name or user.username,
        target_type="user", target_id=new_user.id,
        detail={"username": new_user.username, "roles": data.role_codes},
        ip=client_ip(request),
    )
    db.commit()      # 业务数据 + 审计日志一起提交
    return _to_out(new_user)


@router.post("/users/{user_id}/roles", response_model=UserOut)
def post_user_roles(
    user_id: int,
    data: RolesIn,
    request: Request,
    user: User = Depends(require_perm("role:write")),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="员工不存在")

    before = sorted(r.code for r in target.roles)
    try:
        after = set_roles(db, target, data.role_codes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc

    write_audit(
        db, action="update", user_id=user.id,
        user_name=user.real_name or user.username,
        target_type="user", target_id=target.id,
        detail={"roles": [before, after]},      # 改前改后都要记
        ip=client_ip(request),
    )
    db.commit()
    return _to_out(target)


@router.post("/users/{user_id}/disable", response_model=UserOut)
def post_user_disable(
    user_id: int,
    request: Request,
    user: User = Depends(require_perm("user:write")),
    db: Session = Depends(get_db),
):
    if user_id == user.id:      # 防呆：不能禁用自己
        raise HTTPException(status_code=400, detail="不能禁用自己")

    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="员工不存在")

    disable_user(db, target)
    write_audit(
        db, action="update", user_id=user.id,
        user_name=user.real_name or user.username,
        target_type="user", target_id=target.id,
        detail={"status": ["active", "disabled"]},
        ip=client_ip(request),
    )
    db.commit()
    return _to_out(target)
