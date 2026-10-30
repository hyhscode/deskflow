from fastapi import APIRouter,Depends,HTTPException,status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import collect_permissions, get_current_user
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas.auth import LoginRequest, MeOut, TokenOut


router = APIRouter(prefix="/api/desk",tags=["客服端认证"])

@router.post("/login",response_model=TokenOut)
def login(data:LoginRequest,db:Session = Depends(get_db)):
    user = db.execute(
        select(User).where(User.username == data.username)
    ).scalar_one_or_none()

    if(
        user is None
        or user.is_deleted
        or user.status != "active"
        or not verify_password(data.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(user.id)

    return TokenOut(
        access_token=token,
        token_tyre="bearer",
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