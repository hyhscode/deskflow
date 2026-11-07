from sqlalchemy import func,select
from sqlalchemy.orm import Session

from app.models import Role,Ticket,User

MAX_LOAD = 8

ACTIVE_STATUSES = ("assigned", "processing")

# 谁能接单。主管也接单 —— 投诉类只有主管有技能标签，不把他算进来就没人可派
ASSIGNEE_ROLES = ("agent", "supervisor")

def load_of(db:Session,user_id:int) ->int:
    return db.execute(
        select(func.count(Ticket.id)).where(
            Ticket.assignee_id == user_id,
            Ticket.status.in_(ACTIVE_STATUSES),
        )
    ).scalar_one()

def pick_assignee(db:Session,category:str | None) -> User | None:
    agents = db.execute(
        select(User)
        .join(User.roles)
        .where(
            Role.code.in_(ASSIGNEE_ROLES),
            User.status == "active",
            User.is_deleted == False,
        )
    ).scalars().unique().all()

    candidates = []
    for agent in agents:
        skill_hit = 1 if category and category in (agent.skills or []) else 0
        load = load_of(db,agent.id)

        if load >= MAX_LOAD:
            continue

        candidates.append((skill_hit,load,agent))

    if not candidates:
        return None

    candidates.sort(key=lambda item:(-item[0], item[1], item[2].id))
    return candidates[0][2]