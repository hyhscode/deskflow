from datetime import datetime,timezone
from typing import TYPE_CHECKING

from sqlalchemy import JSON,DateTime,ForeignKey,Index,String,Text
from sqlalchemy.orm import Mapped,mapped_column,relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.ticket import Ticket


class Conversation(Base):
    __tablename__ = "conversations"
    id:Mapped[int] = mapped_column(primary_key=True)
    visitor_key: Mapped[str] = mapped_column(String(64), index=True)
    channel: Mapped[str] = mapped_column(String(16), default="web")
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)

    created_at:Mapped[datetime] = mapped_column(
        DateTime(timezone=True),default=lambda:datetime.now(timezone.utc)
    )
    closed_at:Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages:Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all,delete-orphan",
        order_by="Message.id",
    )

    ticket:Mapped["Ticket | None"] = relationship(
        back_populates="conversation",
        uselist=False
    )

class Message(Base):
    __tablename__ = "messages"

    id:Mapped[int] = mapped_column(primary_key=True)
    conversation_id:Mapped[int] = mapped_column(
        ForeignKey("conversations.id",ondelete="CASCADE")
    )

    sender:Mapped[str] = mapped_column(String(16))
    agent_id:Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    content:Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(16), default="text")
    tokens: Mapped[int | None] = mapped_column()
    latency_ms: Mapped[int | None] = mapped_column()
    kb_article_ids: Mapped[list[int] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    __table_args__ = (
        Index("ix_messages_conv_created", "conversation_id", "created_at"),
    )
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


