
from typing import Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session as DBSession

from app.models.models import (
    AuditLog, Message, Patient, Physician,
    PhysicianNote, Session as ChatSession, _now,
)


class PhysicianService:


    def update_profile(
        self,
        db: DBSession,
        physician: Physician,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        title: Optional[str] = None,
        specialty: Optional[str] = None,
    ) -> Physician:
        if first_name: physician.first_name = first_name
        if last_name:  physician.last_name  = last_name
        if title:      physician.title      = title
        if specialty:  physician.specialty  = specialty
        db.commit()
        db.refresh(physician)
        return physician


    def get_patients(
        self,
        db: DBSession,
        physician: Physician,
        search: Optional[str] = None,
        is_active: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        query = db.query(Patient).filter(
            Patient.practice_id == physician.practice_id,
            Patient.is_active == is_active,
        )
        if search:
            term = f"%{search.lower()}%"
            query = query.filter(
                or_(
                    Patient.first_name.ilike(term),
                    Patient.last_name.ilike(term),
                    Patient.email.ilike(term),
                )
            )
        total = query.count()
        patients = query.offset(offset).limit(limit).all()
        return {"total": total, "limit": limit, "offset": offset, "patients": patients}

    def get_patient(
        self,
        db: DBSession,
        physician: Physician,
        patient_id: str,
    ) -> Optional[Patient]:
        """Returns patient only if they belong to the physician's practice."""
        return db.query(Patient).filter(
            Patient.id == patient_id,
            Patient.practice_id == physician.practice_id,
        ).first()


    def get_sessions(
        self,
        db: DBSession,
        physician: Physician,
        status: Optional[str] = None,
        urgency: Optional[str] = None,
        order_by: str = "updated_at",
        limit: int = 30,
        offset: int = 0,
    ) -> dict:
        """All sessions from this physician's practice."""
        # Join Patient to enforce practice isolation at DB level
        query = (
            db.query(ChatSession)
            .join(Patient, ChatSession.patient_id == Patient.id)
            .filter(Patient.practice_id == physician.practice_id)
        )
        if status:  query = query.filter(ChatSession.status == status)
        if urgency: query = query.filter(ChatSession.urgency == urgency)

        # Dynamic order
        order_col = {
            "created_at": ChatSession.created_at,
            "updated_at": ChatSession.updated_at,
            "urgency":    ChatSession.urgency,
        }.get(order_by, ChatSession.updated_at)

        total = query.count()
        sessions = query.order_by(order_col.desc()).offset(offset).limit(limit).all()
        return {"total": total, "limit": limit, "offset": offset, "sessions": sessions}

    def get_urgent_sessions(self, db: DBSession, physician: Physician) -> list:
        return (
            db.query(ChatSession)
            .join(Patient, ChatSession.patient_id == Patient.id)
            .filter(
                Patient.practice_id == physician.practice_id,
                ChatSession.urgency == "emergency",
            )
            .order_by(ChatSession.updated_at.desc())
            .all()
        )

    def get_session(
        self,
        db: DBSession,
        physician: Physician,
        session_id: str,
        request_ip: Optional[str] = None,
    ) -> Optional[ChatSession]:
        """
        Fetch full session + write audit log.
        Returns None if session is outside physician's practice.
        """
        session = (
            db.query(ChatSession)
            .join(Patient, ChatSession.patient_id == Patient.id)
            .filter(
                ChatSession.id == session_id,
                Patient.practice_id == physician.practice_id,
            )
            .first()
        )
        if session:
            self._write_audit(
                db, physician, session,
                action="session_viewed",
                ip=request_ip,
            )
        return session

    def triage_session(
        self,
        db: DBSession,
        physician: Physician,
        session_id: str,
        urgency: Optional[str] = None,
        status: Optional[str] = None,
        assign_physician_id: Optional[str] = None,
        request_ip: Optional[str] = None,
    ) -> Optional[ChatSession]:
        session = self._get_session_safe(db, physician, session_id)
        if not session:
            return None

        if urgency: session.urgency = urgency
        if status:  session.status  = status
        if assign_physician_id:
            # Verify assigned physician belongs to same practice
            target = db.query(Physician).filter(
                Physician.id == assign_physician_id,
                Physician.practice_id == physician.practice_id,
            ).first()
            if target:
                session.physician_id = assign_physician_id

        db.commit()
        db.refresh(session)

        self._write_audit(db, physician, session, action="session_triaged", ip=request_ip)
        return session

    def close_session(
        self,
        db: DBSession,
        physician: Physician,
        session_id: str,
        closing_note: Optional[str] = None,
        request_ip: Optional[str] = None,
    ) -> Optional[ChatSession]:
        session = self._get_session_safe(db, physician, session_id)
        if not session:
            return None
        if session.status == "closed":
            raise ValueError("Diese Sitzung ist bereits geschlossen.")

        session.status = "closed"
        if closing_note:
            note = PhysicianNote(
                session_id=session.id,
                physician_id=physician.id,
                content=closing_note,
            )
            db.add(note)

        db.commit()
        db.refresh(session)
        self._write_audit(db, physician, session, action="session_closed", ip=request_ip)
        return session


    def add_note(
        self,
        db: DBSession,
        physician: Physician,
        session_id: str,
        content: str,
        request_ip: Optional[str] = None,
    ) -> Optional[PhysicianNote]:
        session = self._get_session_safe(db, physician, session_id)
        if not session:
            return None

        note = PhysicianNote(
            session_id=session_id,
            physician_id=physician.id,
            content=content.strip(),
        )
        db.add(note)
        db.commit()
        db.refresh(note)

        self._write_audit(db, physician, session, action="note_added", ip=request_ip)
        return note

    def get_notes(
        self,
        db: DBSession,
        physician: Physician,
        session_id: str,
    ) -> list[PhysicianNote]:
        """Only returns notes by this physician — not colleagues."""
        return (
            db.query(PhysicianNote)
            .filter(
                PhysicianNote.session_id == session_id,
                PhysicianNote.physician_id == physician.id,
            )
            .order_by(PhysicianNote.created_at)
            .all()
        )

    def get_note(
        self,
        db: DBSession,
        physician: Physician,
        note_id: str,
    ) -> Optional[PhysicianNote]:
        """Ownership check built-in."""
        return db.query(PhysicianNote).filter(
            PhysicianNote.id == note_id,
            PhysicianNote.physician_id == physician.id,
        ).first()

    def update_note(
        self,
        db: DBSession,
        physician: Physician,
        note_id: str,
        content: str,
    ) -> Optional[PhysicianNote]:
        note = self.get_note(db, physician, note_id)
        if not note:
            return None
        note.content = content.strip()
        db.commit()
        db.refresh(note)
        return note

    def delete_note(
        self,
        db: DBSession,
        physician: Physician,
        note_id: str,
    ) -> bool:
        note = self.get_note(db, physician, note_id)
        if not note:
            return False
        db.delete(note)
        db.commit()
        return True


    def get_audit_logs(
        self,
        db: DBSession,
        physician: Physician,
        session_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        query = db.query(AuditLog).filter(AuditLog.physician_id == physician.id)
        if session_id:
            query = query.filter(AuditLog.session_id == session_id)
        total = query.count()
        logs = query.order_by(AuditLog.accessed_at.desc()).offset(offset).limit(limit).all()
        return {"total": total, "logs": logs}

    def _get_session_safe(
        self,
        db: DBSession,
        physician: Physician,
        session_id: str,
    ) -> Optional[ChatSession]:
        """Practice-isolated session fetch — no audit log written."""
        return (
            db.query(ChatSession)
            .join(Patient, ChatSession.patient_id == Patient.id)
            .filter(
                ChatSession.id == session_id,
                Patient.practice_id == physician.practice_id,
            )
            .first()
        )

    def _write_audit(
        self,
        db: DBSession,
        physician: Physician,
        session: ChatSession,
        action: str,
        ip: Optional[str] = None,
    ) -> None:
        log = AuditLog(
            actor_id=physician.id,
            actor_type="physician",
            patient_id=session.patient_id,
            resource=f"session:{session.id}",
            action=action,
            ip_address=ip,
            created_at=_now(),
        )
        db.add(log)
        db.commit()