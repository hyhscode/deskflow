
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import TokenError, decode_access_token
from app.db.session import get_db
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate":"Bearer"}

def get_current_user(
    credentials:HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db:Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录：请在请求头带上 Authorization: Bearer <token>",
            headers=_UNAUTHORIZED_HEADERS,
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers=_UNAUTHORIZED_HEADERS,
        ) from exc

    user_id = int(payload["sub"])

    user = db.get(User,user_id)

    if user is None or user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号不存在或已被删除，请重新登录",
            headers=_UNAUTHORIZED_HEADERS,
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号已被禁用，请联系管理员",
            headers=_UNAUTHORIZED_HEADERS,
        )

    return user

def collect_permissions(user:User) -> list[str]:
    codes = {
        permission.code
        for role in user.roles          # 用户的角色（User.roles 已设 lazy="selectin"，一次查完）
        for permission in role.permissions   # 角色下的权限点
    }
    return sorted(codes)