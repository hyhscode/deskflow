from typing import Any

from sqlalchemy.orm import Session

from app.models import OperationLog

def write_audit(
    db:Session,
    *,
    action:str,
    user_id:int | None = None,
    user_name: str | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    commit: bool = False,
) -> OperationLog:
    log = OperationLog(
        user_id=user_id,
        user_name=user_name,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
        ip=ip,
        user_agent=user_agent,
    )
    db.add(log)

    if commit:
        db.commit()

    return log

def client_ip(request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None