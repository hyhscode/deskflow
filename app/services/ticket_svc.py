from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Ticket, TicketLog, User
from app.services.assign import pick_assignee

TRANSITIONS: dict[str, set[str]] = {
    "pending": {"assigned", "closed"},                              # 待派 → 派出 / 直接关
    "assigned": {"processing", "pending", "closed"},                # 已派 → 开始处理 / 退回池 / 关
    "processing": {"resolved", "assigned", "closed"},               # 处理中 → 解决 / 转交 / 关
    "resolved": {"closed", "processing"},                           # 已解决 → 关单 / 客户又反馈
    "closed": set(),                                                # 关闭是终点
}

class InvalidTransition(Exception):
    pass

def create_ticket(
    db:Session,
    conversation_id:int,
    question:str,
    category:str |None = None,
    priority:str = "P2"
) -> Ticket:
    ticket = Ticket(
        conversation_id=conversation_id,
        title=question[:100],       # 标题截断，避免超长撑爆列表页
        summary=question[:200],     # 摘要先用原话，接上模型后换成 AI 生成的
        category=category or "other",
        priority=priority,
        status="pending",
    )
    db.add(ticket)
    db.flush()           

    db.add(TicketLog(
        ticket_id=ticket.id,
        operator_id = None,
        action="create",
        to_value={"status": "pending"},
    ))

    assign_ticket(db,ticket)
    return ticket

def assign_ticket(db:Session,ticket:Ticket) -> User | None:
    agent = pick_assignee(db,ticket.category)
    if agent is None:
        return None

    ticket.assignee_id = agent.id
    ticket.status = "assigned"
    ticket.assigned_at = datetime.now(timezone.utc)

    db.add(TicketLog(
        ticket_id=ticket.id,
        operator_id=None,           # 系统自动派单，没有操作人
        action="assign",
        to_value={"assignee_id": agent.id},
    ))
    return agent

def change_status(
    db: Session,
    ticket: Ticket,
    target: str,
    operator_id: int | None = None,
) -> Ticket:
    allowed = TRANSITIONS.get(ticket.status,set())
    if target not in allowed:
        raise InvalidTransition(f"{ticket.status}不能直接变成{target}")

    previous = ticket.status
    ticket.status = target

    now = datetime.now(timezone.utc)
    if target == "resolved":
        ticket.resolved_at = now
    elif target == "closed":
        ticket.closed_at = now

    db.add(TicketLog(
        ticket_id=ticket.id,
        operator_id=operator_id,
        action="status",
        from_value={"status": previous},
        to_value={"status": target},
    ))
    return ticket