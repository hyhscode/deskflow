from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.services.audit import client_ip, write_audit 
from app.core.deps import collect_permissions, get_current_user
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas.auth import LoginRequest, MeOut, TokenOut


router = APIRouter(prefix="/api/desk",tags=["客服端认证"])

@router.post("/login",response_model=TokenOut)
def login(data:LoginRequest,request:Request,db:Session = Depends(get_db)):
    user = db.execute(
        select(User).where(User.username == data.username)
    ).scalar_one_or_none()

    if(
        user is None
        or user.is_deleted
        or user.status != "active"
        or not verify_password(data.password, user.password_hash)
    ):
        write_audit(
            db,
            action="login_failed",
            user_id=user.id if user else None,   # 账号不存在时没有 id
            user_name=data.username,             # 记下"尝试登录的那个用户名"
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(user.id)

    write_audit(
        db,
        action="login",
        user_id=user.id,
        user_name=user.real_name or user.username,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        commit=True,
    )
    
    return TokenOut(
        access_token=token,
        token_type="bearer",
        expires_in = settings_expire_seconds(),
    )

def settings_expire_seconds() -> int:
    from app.core.config import settings
    return settings.token_expire_minutes *60

@router.get("/me",response_model=MeOut)
def read_me(user:User = Depends(get_current_user)):
    return MeOut(
        id=user.id,
        username=user.username,
        real_name=user.real_name,
        roles=[role.code for role in user.roles],
        permissions=collect_permissions(user),
    )