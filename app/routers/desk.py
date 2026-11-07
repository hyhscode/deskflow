from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import collect_permissions
from app.core.perms import require_perm
from app.db.session import get_db
from app.models import Message, Ticket, User
from app.schemas.desk import (
    MessageItem,
    ReplyIn,
    StatusIn,
    TicketDetailOut,
    TicketOut,
)
from app.services.ticket_svc import (
    DATA_SCOPE_ALL,
    InvalidTransition,
    change_status,
    list_tickets,
    reply_ticket,
)
from app.models import Message, QaReport, Ticket, User
from app.schemas.desk import (
    DraftIn, DraftOut, QaOut, ReplyIn, ReviewIn,
    StatusIn, SummaryOut, TicketDetailOut, TicketOut,
)
from app.services.assist import draft_reply, review_qa, score_qa, summarize_ticket


router = APIRouter(prefix="/api/desk", tags=["客服端·工单"])

def _get_ticket_or_404(db: Session, ticket_id: int) -> Ticket:
    """按主键取工单，没有就 404。"""
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"工单 {ticket_id} 不存在",
        )
    return ticket

def _ensure_can_access(ticket: Ticket, user: User) -> None:
    if ticket.assignee_id == user.id:
        return
    if DATA_SCOPE_ALL in collect_permissions(user):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="这张工单没有派给你",
    )

@router.get("/tickets", response_model=list[TicketOut])
def get_tickets(
    status_filter:str | None = None,
    user:User = Depends(require_perm("ticket:read")),
    db:Session = Depends(get_db),
):
    rows = list_tickets(db, user, collect_permissions(user), status_filter)
    return [TicketOut.model_validate(row,from_attributes=True) for row in rows]


@router.get("/tickets/{ticket_id}", response_model=TicketDetailOut)
def get_ticket_detail(
    ticket_id: int,
    user: User = Depends(require_perm("ticket:read")),
    db: Session = Depends(get_db),
):
    """工单详情：字段 + 完整对话记录。"""
    ticket = _get_ticket_or_404(db, ticket_id)
    _ensure_can_access(ticket, user)

    messages = db.execute(
        select(Message)
        .where(Message.conversation_id == ticket.conversation_id)
        .order_by(Message.id)
    ).scalars().all()

    assignee = db.get(User, ticket.assignee_id) if ticket.assignee_id else None

    return TicketDetailOut(
        id=ticket.id,
        title=ticket.title,
        category=ticket.category,
        priority=ticket.priority,
        status=ticket.status,
        assignee_id=ticket.assignee_id,
        assignee_name=assignee.real_name if assignee else None,
        created_at=ticket.created_at,
        first_response_at=ticket.first_response_at,
        summary=ticket.summary,
        conversation_id=ticket.conversation_id,
        messages=[
            MessageItem(
                id=m.id, sender=m.sender, content=m.content, created_at=m.created_at
            )
            for m in messages
        ],
    )


@router.post("/tickets/{ticket_id}/reply", response_model=MessageItem)
def post_reply(
    ticket_id: int,
    data: ReplyIn,
    user: User = Depends(require_perm("ticket:read")),
    db: Session = Depends(get_db),
):
    """回复客户。回复完客户在聊天窗口里能立刻看到。"""
    ticket = _get_ticket_or_404(db, ticket_id)
    _ensure_can_access(ticket, user)

    # 已关闭的单不能再回，否则客户收到消息也无法继续对话
    if ticket.status == "closed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="工单已关闭，不能再回复",
        )

    msg = reply_ticket(db, ticket, user, data.content)
    db.commit()

    return MessageItem(
        id=msg.id, sender=msg.sender, content=msg.content, created_at=msg.created_at
    )


@router.post("/tickets/{ticket_id}/status", response_model=TicketOut)
def post_status(
    ticket_id: int,
    data: StatusIn,
    user: User = Depends(require_perm("ticket:read")),
    db: Session = Depends(get_db),
):
    """改状态：接单、标记解决、关单。非法跳转返回 400。"""
    ticket = _get_ticket_or_404(db, ticket_id)
    _ensure_can_access(ticket, user)

    try:
        change_status(db, ticket, data.target, operator_id=user.id)
    except InvalidTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    db.commit()
    return TicketOut.model_validate(ticket, from_attributes=True)

@router.post("/tickets/{ticket_id}/draft", response_model=DraftOut)
def post_draft(
    ticket_id: int,
    data: DraftIn,
    user: User = Depends(require_perm("ticket:read")),
    db: Session = Depends(get_db),
):
    """生成回复草稿。客服点一下，框里出现一段话，改完自己发。"""
    ticket = _get_ticket_or_404(db, ticket_id)
    _ensure_can_access(ticket, user)

    result = draft_reply(db, ticket, data.instruction)
    db.commit()      # 提交是为了把 llm_logs 落盘

    return DraftOut(**result)


@router.post("/tickets/{ticket_id}/summarize", response_model=SummaryOut)
def post_summarize(
    ticket_id: int,
    user: User = Depends(require_perm("ticket:read")),
    db: Session = Depends(get_db),
):
    """生成工单摘要，写进 tickets.summary。

    这个接口没有请求体：前端发一个空 body 即可（POST 允许无 body）。
    """
    ticket = _get_ticket_or_404(db, ticket_id)
    _ensure_can_access(ticket, user)

    summary = summarize_ticket(db, ticket)
    db.commit()
    return SummaryOut(summary=summary)


@router.post("/tickets/{ticket_id}/qa", response_model=QaOut)
def post_qa(
    ticket_id: int,
    user: User = Depends(require_perm("qa:review")),
    db: Session = Depends(get_db),
):
    """跑一次 AI 质检。需要 qa:review（主管）。"""
    ticket = _get_ticket_or_404(db, ticket_id)

    report = score_qa(db, ticket)
    db.commit()

    return QaOut(
        id=report.id, ticket_id=report.ticket_id, score=report.score,
        dimensions=report.dimensions or {}, comment=report.comment,
        reviewed=report.reviewed,
    )


@router.post("/qa/{report_id}/review", response_model=QaOut)
def post_qa_review(
    report_id: int,
    data: ReviewIn,
    user: User = Depends(require_perm("qa:review")),
    db: Session = Depends(get_db),
):
    """人工复核。给了 human_score 就做分差检测。"""
    report = db.get(QaReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="质检报告不存在")

    review_qa(db, report, user.id, data.human_score, data.comment)
    db.commit()

    return QaOut(
        id=report.id, ticket_id=report.ticket_id, score=report.score,
        dimensions=report.dimensions or {}, comment=report.comment,
        reviewed=report.reviewed,
    )
