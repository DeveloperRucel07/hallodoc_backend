
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum,
    ForeignKey, JSON, String, Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _now():
    return datetime.now(timezone.utc)


def _uuid():
    return str(uuid.uuid4())


class Practice(Base):
    """
    A medical practice. Patients register via practice_code.
    Multiple physicians belong to one practice.
    """
    __tablename__ = "practices"

    id           = Column(String(36), primary_key=True, default=_uuid)
    code         = Column(String(20), unique=True, nullable=False, index=True)
    name         = Column(String(255), nullable=False)
    address      = Column(Text, nullable=True)
    phone        = Column(String(50), nullable=True)
    email        = Column(String(255), nullable=True)
    is_active    = Column(Boolean, default=True, nullable=False)
    created_at   = Column(DateTime(timezone=True), default=_now)

    physicians = relationship(
        "Physician",
        back_populates="practice",
        cascade="all, delete-orphan",
    )
    patients = relationship(
        "Patient",
        back_populates="practice",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Practice '{self.name}' code={self.code}>"


class Physician(Base):
    """
    A physician belonging to a practice.
    Receives session summaries after AI triage.
    """
    __tablename__ = "physicians"

    id              = Column(String(36), primary_key=True, default=_uuid)
    practice_id     = Column(String(36), ForeignKey("practices.id"), nullable=False, index=True)
    email           = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    first_name      = Column(String(100), nullable=False)
    last_name       = Column(String(100), nullable=False)
    title           = Column(String(50), nullable=True)    # Dr., Prof. Dr., etc.
    specialty       = Column(String(100), nullable=True)   # Allgemeinmedizin, Kardiologie
    is_active       = Column(Boolean, default=True, nullable=False)
    created_at      = Column(DateTime(timezone=True), default=_now)
    updated_at      = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    practice = relationship("Practice", back_populates="physicians")

    @property
    def full_name(self) -> str:
        parts = [self.title, self.first_name, self.last_name]
        return " ".join(p for p in parts if p)

    def __repr__(self):
        return f"<Physician {self.full_name} ({self.specialty})>"


class Patient(Base):
    """
    A patient registered to a practice via practice_code.
    Authenticates with email + password.
    """
    __tablename__ = "patients"

    id              = Column(String(36), primary_key=True, default=_uuid)
    practice_id     = Column(String(36), ForeignKey("practices.id"), nullable=False, index=True)
    email           = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    first_name      = Column(String(100), nullable=False)
    last_name       = Column(String(100), nullable=False)
    date_of_birth   = Column(Date, nullable=True)
    phone           = Column(String(50), nullable=True)
    is_active       = Column(Boolean, default=True, nullable=False)
    created_at      = Column(DateTime(timezone=True), default=_now)
    updated_at      = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    practice = relationship("Practice", back_populates="patients")
    sessions = relationship(
        "Session",
        back_populates="patient",
        cascade="all, delete-orphan",
        order_by="Session.created_at.desc()",
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def __repr__(self):
        return f"<Patient {self.full_name} ({self.email})>"


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=_uuid)

    patient_id = Column(
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
    )

    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)
    status = Column(
        Enum("active", "closed", name="session_status"),
        default="active",
        nullable=False,
    )

    patient = relationship("Patient", back_populates="sessions")

    messages = relationship(
        "Message",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

class Message(Base):
    """
    A single message in a session — from patient or AI.
    sources: list of RAG document filenames used to generate the answer.
    """
    __tablename__ = "messages"

    id= Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=False, index=True)
    role= Column(
        Enum("user", "assistant", "system", name="message_role"),
        nullable=False,
    )
    content  = Column(Text, nullable=False)
    sources = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    session = relationship("Session", back_populates="messages")

    def __repr__(self):
        preview = self.content[:40].replace("\n", " ")
        return f"<Message [{self.role}] '{preview}...'>"