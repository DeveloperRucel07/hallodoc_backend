import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum,
    ForeignKey, JSON, String, Text, UniqueConstraint,
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

    id         = Column(String(36), primary_key=True, default=_uuid)
    code       = Column(String(20), unique=True, nullable=False, index=True)
    name       = Column(String(255), nullable=False)
    address    = Column(Text, nullable=True)
    phone      = Column(String(50), nullable=True)
    email      = Column(String(255), nullable=True)
    is_active  = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)
    is_deleted_at   = Column(DateTime(timezone=True), nullable=True)
    physicians = relationship(
        "Physician",
        back_populates="practice",
    )
    patients = relationship(
        "Patient",
        back_populates="practice",
    )

    def __repr__(self):
        return f"<Practice '{self.name}' code={self.code}>"


class PhysicianInvite(Base):
    __tablename__ = "physician_invites"

    id = Column(String(36), primary_key=True, default=_uuid)
    practice_id = Column(ForeignKey("practices.id"), nullable=False,index=True, )
    email = Column(String(255),nullable=False, index=True, )
    token_hash = Column(String(255), nullable=False,  unique=True,)
    expires_at = Column(DateTime(timezone=True),nullable=False,)
    used_at = Column(DateTime(timezone=True),)
    created_by = Column(ForeignKey("physicians.id"), nullable=False,)
    created_at = Column( DateTime(timezone=True), default=_now,)
    __table_args__ = (
        UniqueConstraint(
            "practice_id",
            "email",
            name="uq_active_invite"
        ),
    )

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
    title           = Column(String(50), nullable=True)
    specialty       = Column(String(100), nullable=True)
    role            = Column(Enum("physician","admin","supervisor",name="physician_role"))
    is_active       = Column(Boolean, default=True, nullable=False)
    created_at      = Column(DateTime(timezone=True), default=_now)
    updated_at      = Column(DateTime(timezone=True), default=_now, onupdate=_now)
    last_login_at   = Column(DateTime(timezone=True), nullable=True)
    is_deleted_at   = Column(DateTime(timezone=True), nullable=True)
    patients = relationship("Patient", back_populates="physician")
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
    physician_id     = Column(String(36), ForeignKey("physicians.id"), nullable=True, index=True)
    practice_id     = Column(String(36), ForeignKey("practices.id"), nullable=False, index=True)
    email           = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    first_name      = Column(String(100), nullable=False)
    last_name       = Column(String(100), nullable=False)
    date_of_birth   = Column(Date, nullable=True)
    gender = Column(
        Enum( "male", "female","diverse", "unknown", name="patient_gender" )
    )
    phone           = Column(String(50), nullable=True)
    is_active       = Column(Boolean, default=True, nullable=False)
    created_at      = Column(DateTime(timezone=True), default=_now)
    updated_at      = Column(DateTime(timezone=True), default=_now, onupdate=_now)
    is_deleted_at   = Column(DateTime(timezone=True), nullable=True)
    physician = relationship("Physician", back_populates="patients")
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
    physician_id = Column(
        ForeignKey("physicians.id"),
        nullable=True,
        index=True,
    )
    status = Column(
        Enum("active", "closed", name="session_status"),
        default="active",
        nullable=False,
    )
    urgency = Column(
        Enum("none", "routine", "urgent", "emergency", name="urgency_level"),
        default="none",
        nullable=False,
    )

    created_at = Column(DateTime(timezone=True), default=_now)
    started_at = Column(DateTime(timezone=True), nullable=True)
    stopped_at = Column(DateTime(timezone=True), nullable=True)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)
    patient   = relationship("Patient",   back_populates="sessions")
    physician = relationship("Physician")
    messages = relationship(
        "Message",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    summary = relationship(
        "SessionSummary",
        back_populates="session",
        uselist=False
    )


class Message(Base):
    __tablename__ = "messages"

    id         = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=False, index=True)
    role       = Column(
        Enum("user", "assistant", "system", name="message_role"),
        nullable=False,
    )
    content    = Column(Text, nullable=False)
    sources    = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    session = relationship("Session", back_populates="messages")

    def __repr__(self):
        preview = self.content[:40].replace("\n", " ")
        return f"<Message [{self.role}] '{preview}...'>"

class SessionSummary(Base):
    __tablename__ = "session_summaries"

    id         = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=False, unique=True, index=True)
    summary    = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)
    generated_by = Column(Enum("assistant", "patient"), nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=True)
    urgency = Column(
        Enum( "routine", "urgent", "emergency", name="summary_urgency_level"),
        default="routine",
        name="summary_level",
    )
    email_status = Column(Enum("not_sent","pending", "sent", "failed"), default="not_sent", nullable=False)
    email_sent_at = Column(DateTime(timezone=True), nullable=True)
    session = relationship("Session", back_populates="summary")

    def __repr__(self):
        preview = self.summary[:40].replace("\n", " ")
        return f"<SessionSummary urgency={self.urgency} '{preview}...'>"


class PhysicianNote(Base):
    __tablename__ = "physician_notes"

    id           = Column(String(36), primary_key=True, default=_uuid)
    session_id   = Column(String(36), ForeignKey("sessions.id"),   nullable=False, index=True)
    physician_id = Column(String(36), ForeignKey("physicians.id"), nullable=False, index=True)
    content      = Column(Text, nullable=False)
    created_at   = Column(DateTime(timezone=True), default=_now)
    updated_at   = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    session   = relationship("Session",   backref="notes")
    physician = relationship("Physician", backref="notes")
    deleted_at = Column(DateTime(timezone=True))
    def __repr__(self):
        return f"<PhysicianNote by={self.physician_id} session={self.session_id}>"


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(String(36), primary_key=True, default=_uuid)

    actor_id = Column(String(36))

    actor_type = Column(
        Enum(
            "physician",
            "system",
            name="actor_type"
        )
    )

    patient_id = Column(
        String(36),
        ForeignKey("patients.id"),
    )

    resource = Column(String(100))

    action = Column(String(100))

    ip_address = Column(String(45))

    user_agent = Column(Text)

    created_at = Column(DateTime(timezone=True))


class PasswordResetToken(Base):

    __tablename__="password_reset_tokens"

    id = Column(String(36), primary_key=True, default=_uuid)

    user_id = Column(String(36))

    token_hash = Column(String(255))

    expires_at = Column(DateTime(timezone=True))

    used_at = Column(DateTime(timezone=True))
