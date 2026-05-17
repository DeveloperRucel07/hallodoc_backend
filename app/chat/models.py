"""
models.py — SQLAlchemy models for chat sessions and messages.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, Enum, JSON
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _now():
    return datetime.now(timezone.utc)


def _uuid():
    return str(uuid.uuid4())


class Session(Base):
    """
    A conversation session between a user and the AI.
    One session = one medical consultation context.
    """
    __tablename__ = "sessions"

    id           = Column(String(36), primary_key=True, default=_uuid)
    user_id      = Column(String(36), nullable=False, index=True)
    physician_id = Column(String(36), nullable=True)   # assigned after triage
    status       = Column(
        Enum("active", "closed", "urgent", "routine", name="session_status"),
        default="active",
        nullable=False,
    )
    urgency      = Column(
        Enum("none", "routine", "urgent", "emergency", name="urgency_level"),
        default="none",
        nullable=False,
    )
    summary      = Column(Text, nullable=True)         # filled when session closes
    created_at   = Column(DateTime(timezone=True), default=_now)
    updated_at   = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    messages = relationship(
        "Message",
        back_populates="session",
        order_by="Message.created_at",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Session {self.id[:8]} user={self.user_id} status={self.status}>"


class Message(Base):

    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=False, index=True)
    role = Column(
        Enum("user", "assistant", "system", name="message_role"),
        nullable=False,
    )
    content= Column(Text, nullable=False)
    sources= Column(JSON, nullable=True)   # list of source filenames from RAG
    created_at = Column(DateTime(timezone=True), default=_now)
    session = relationship("Session", back_populates="messages")
    def __repr__(self):
        preview = self.content[:40].replace("\n", " ")
        return f"<Message {self.role} '{preview}...'>"