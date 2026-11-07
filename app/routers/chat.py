from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from sqlalchemy import select
from app.db.session import get_db
from app.models import Conversation, Message, PresetQa
from app.schemas.chat import ChatMessageIn, ChatMessageOut, ChatSelectIn, MessageOut, SuggestionOut
from app.services.chat_svc import get_or_create_conversation, handle_and_save, save_message

router = APIRouter(prefix="/api/chat", tags=["访客端"])


@router.post("/message", response_model=ChatMessageOut)
def send_message(data:ChatMessageIn,db:Session = Depends(get_db)):
    record = handle_and_save(db,data.visitor_key,data.content)
    result = record.result

    return ChatMessageOut(
        type=result.type,
        content=result.content,
        suggestions=[SuggestionOut(**s) for s in result.suggestions],
        citation=result.citation,
    )

@router.get("/history", response_model=list[MessageOut])
def get_history(visitor_key:str,db:Session = Depends(get_db)):
    conv = db.execute(
        select(Conversation)
        .where(Conversation.visitor_key == visitor_key, Conversation.status == "open")
        .order_by(Conversation.id.desc())
    ).scalars().first()

    if conv is None:
        return []

    messages = db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.id)          
    ).scalars().all()

    return [
        MessageOut(
            id=m.id,
            sender=m.sender,
            content=m.content,
            content_type=m.content_type,
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.post("/select", response_model=ChatMessageOut)
def select_preset(data: ChatSelectIn, db: Session = Depends(get_db)):
    """客户点选预设候选：直接返回预设里写死的答案，一个字都不生成。

    这就是"零幻觉"的落点：答案是运营审核过的文本，模型没机会参与。
    """
    preset = db.get(PresetQa, data.preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="预设问题不存在")

    conv, _ = get_or_create_conversation(db, data.visitor_key)

    # 存两条：客户的选择 + 答案。历史记录里能看出"他是点进来的"
    save_message(db, conv.id, "visitor", preset.question, content_type="select")
    save_message(db, conv.id, "ai", preset.answer, content_type="answer")

    # 命中计数：以后决定"哪些问题该从知识升级成预设"，就靠它排序
    preset.ask_count = (preset.ask_count or 0) + 1
    db.commit()

    return ChatMessageOut(type="answer", content=preset.answer)