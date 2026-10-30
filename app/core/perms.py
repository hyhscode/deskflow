from fastapi import Depends,HTTPException,status

from app.core.deps import collect_permissions,get_current_user
from app.models import User

def require_perm(code:str):

    def checker(user:User = Depends(get_current_user)) -> User:
        granted = collect_permissions(user)
        if code not in granted:
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足：需要 {code}",
            )
        return user
    return checker