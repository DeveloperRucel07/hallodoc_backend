
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.auth.dependencies import get_current_physician
from app.models.database import get_db
from app.models.models import Physician
from app.physician.physician_service import PhysicianService

router = APIRouter(prefix="/physician", tags=["Physician Dashboard"])
service = PhysicianService()


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class UpdateProfileRequest(BaseModel):
    first_name: Optional[str] = None
    last_name:  Optional[str] = None
    title:      Optional[str] = None
    specialty:  Optional[str] = None


class TriageRequest(BaseModel):
    urgency:            Optional[str] = None  # none|routine|urgent|emergency
    status:             Optional[str] = None  # active|closed|urgent|routine
    physician_id:       Optional[str] = None  # assign to physician


class CloseSessionRequest(BaseModel):
    closing_note: Optional[str] = None


class NoteRequest(BaseModel):
    session_id: str
    content:    str


class UpdateNoteRequest(BaseModel):
    content: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _patient_out(p) -> dict:
    sessions = sorted(p.sessions, key=lambda s: s.created_at, reverse=True)
    return {
        "id":            p.id,
        "full_name":     p.full_name,
        "email":         p.email,
        "date_of_birth": p.date_of_birth.isoformat() if p.date_of_birth else None,
        "phone":         p.phone,
        "is_active":     p.is_active,
        "created_at":    p.created_at.isoformat(),
        "session_count": len(p.sessions),
        "last_session":  sessions[0].updated_at.isoformat() if sessions else None,
        "last_urgency":  sessions[0].urgency if sessions else "none",
    }


def _session_out(s, include_messages: bool = False, include_notes: bool = False) -> dict:
    out = {
        "session_id":    s.id,
        "patient_id":    s.patient_id,
        "patient_name":  s.patient.full_name if s.patient else None,
        "physician_id":  s.physician_id,
        "status":        s.status,
        "urgency":       s.urgency,
        "summary":       s.summary,
        "message_count": len(s.messages),
        "created_at":    s.created_at.isoformat(),
        "updated_at":    s.updated_at.isoformat(),
    }
    if include_messages:
        out["messages"] = [
            {
                "id":         m.id,
                "role":       m.role,
                "content":    m.content,
                "sources":    m.sources,
                "created_at": m.created_at.isoformat(),
            }
            for m in s.messages
        ]
    if include_notes:
        out["notes"] = [
            {
                "id":           n.id,
                "physician_id": n.physician_id,
                "content":      n.content,
                "created_at":   n.created_at.isoformat(),
            }
            for n in s.notes
        ]
    if include_messages:
        patient = s.patient
        out["patient"] = {
            "id":            patient.id,
            "full_name":     patient.full_name,
            "email":         patient.email,
            "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        }
    return out


def _note_out(n) -> dict:
    return {
        "id":           n.id,
        "session_id":   n.session_id,
        "physician_id": n.physician_id,
        "content":      n.content,
        "created_at":   n.created_at.isoformat(),
        "updated_at":   n.updated_at.isoformat(),
    }


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    return forwarded.split(",")[0].strip() if forwarded else request.client.host


@router.get("/me")
def get_my_profile(current: Physician = Depends(get_current_physician)):
    return {
        "id":          current.id,
        "full_name":   current.full_name,
        "email":       current.email,
        "title":       current.title,
        "first_name":  current.first_name,
        "last_name":   current.last_name,
        "specialty":   current.specialty,
        "practice_id": current.practice_id,
        "is_active":   current.is_active,
        "created_at":  current.created_at.isoformat(),
    }


@router.patch("/me")
def update_profile(
    req: UpdateProfileRequest,
    db: DBSession = Depends(get_db),
    current: Physician = Depends(get_current_physician),
):
    updated = service.update_profile(
        db, current,
        first_name=req.first_name,
        last_name=req.last_name,
        title=req.title,
        specialty=req.specialty,
    )
    return {
        "message":   "Profil aktualisiert.",
        "full_name": updated.full_name,
        "specialty": updated.specialty,
    }


@router.get("/patients")
def get_patients(
    search: Optional[str] = None,
    is_active: bool = True,
    limit: int = 50,
    offset: int = 0,
    db: DBSession = Depends(get_db),
    current: Physician = Depends(get_current_physician),
):
    if limit > 100:
        raise HTTPException(status_code=422, detail="Limit darf maximal 100 sein.")

    result = service.get_patients(db, current, search=search, is_active=is_active, limit=limit, offset=offset)
    return {
        "total":    result["total"],
        "limit":    result["limit"],
        "offset":   result["offset"],
        "patients": [_patient_out(p) for p in result["patients"]],
    }


@router.get("/patients/{patient_id}")
def get_patient(
    patient_id: str,
    db: DBSession = Depends(get_db),
    current: Physician = Depends(get_current_physician),
):
    patient = service.get_patient(db, current, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient nicht gefunden oder außerhalb Ihrer Praxis.")

    sessions = sorted(patient.sessions, key=lambda s: s.created_at, reverse=True)
    return {
        **_patient_out(patient),
        "sessions": [
            {
                "session_id":    s.id,
                "status":        s.status,
                "urgency":       s.urgency,
                "summary":       s.summary,
                "message_count": len(s.messages),
                "created_at":    s.created_at.isoformat(),
                "updated_at":    s.updated_at.isoformat(),
            }
            for s in sessions
        ],
    }


@router.get("/sessions")
def get_sessions(
    status:   Optional[str] = None,
    urgency:  Optional[str] = None,
    order_by: str = "updated_at",
    limit:    int = 30,
    offset:   int = 0,
    db: DBSession = Depends(get_db),
    current: Physician = Depends(get_current_physician),
):
    if limit > 100:
        raise HTTPException(status_code=422, detail="Limit darf maximal 100 sein.")

    result = service.get_sessions(
        db, current,
        status=status, urgency=urgency,
        order_by=order_by, limit=limit, offset=offset,
    )
    return {
        "total":    result["total"],
        "limit":    result["limit"],
        "offset":   result["offset"],
        "sessions": [_session_out(s) for s in result["sessions"]],
    }


@router.get("/sessions/urgent")
def get_urgent_sessions(
    db: DBSession = Depends(get_db),
    current: Physician = Depends(get_current_physician),
):
    sessions = service.get_urgent_sessions(db, current)
    return {
        "count":    len(sessions),
        "sessions": [
            {
                "session_id":   s.id,
                "patient_name": s.patient.full_name if s.patient else None,
                "urgency":      s.urgency,
                "summary":      s.summary,
                "updated_at":   s.updated_at.isoformat(),
            }
            for s in sessions
        ],
    }


@router.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    request: Request,
    db: DBSession = Depends(get_db),
    current: Physician = Depends(get_current_physician),
):
    session = service.get_session(db, current, session_id, request_ip=_get_ip(request))
    if not session:
        raise HTTPException(status_code=404, detail="Sitzung nicht gefunden oder außerhalb Ihrer Praxis.")
    return _session_out(session, include_messages=True, include_notes=True)


@router.patch("/sessions/{session_id}/triage")
def triage_session(
    session_id: str,
    req: TriageRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    current: Physician = Depends(get_current_physician),
):
    valid_urgency = {"none", "routine", "urgent", "emergency"}
    valid_status  = {"active", "closed", "urgent", "routine"}

    if req.urgency and req.urgency not in valid_urgency:
        raise HTTPException(status_code=400, detail=f"Ungültiger urgency-Wert. Erlaubt: {valid_urgency}")
    if req.status and req.status not in valid_status:
        raise HTTPException(status_code=400, detail=f"Ungültiger status-Wert. Erlaubt: {valid_status}")

    session = service.triage_session(
        db, current, session_id,
        urgency=req.urgency,
        status=req.status,
        assign_physician_id=req.physician_id,
        request_ip=_get_ip(request),
    )
    if not session:
        raise HTTPException(status_code=404, detail="Sitzung nicht gefunden.")
    return {
        "message":    "Sitzung aktualisiert.",
        "session_id": session.id,
        "urgency":    session.urgency,
        "status":     session.status,
    }


@router.post("/sessions/{session_id}/close")
def close_session(
    session_id: str,
    req: CloseSessionRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    current: Physician = Depends(get_current_physician),
):
    try:
        session = service.close_session(
            db, current, session_id,
            closing_note=req.closing_note,
            request_ip=_get_ip(request),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not session:
        raise HTTPException(status_code=404, detail="Sitzung nicht gefunden.")
    return {
        "message":    "Sitzung geschlossen.",
        "session_id": session.id,
        "status":     session.status,
        "summary":    session.summary,
    }


# ── Notes ─────────────────────────────────────────────────────────────────────

@router.post("/notes", status_code=status.HTTP_201_CREATED)
def add_note(
    req: NoteRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    current: Physician = Depends(get_current_physician),
):
    if not req.content.strip():
        raise HTTPException(status_code=422, detail="Notizinhalt darf nicht leer sein.")

    note = service.add_note(
        db, current, req.session_id, req.content,
        request_ip=_get_ip(request),
    )
    if not note:
        raise HTTPException(status_code=404, detail="Sitzung nicht gefunden oder außerhalb Ihrer Praxis.")
    return _note_out(note)


@router.get("/notes/session/{session_id}")
def get_notes(
    session_id: str,
    db: DBSession = Depends(get_db),
    current: Physician = Depends(get_current_physician),
):
    notes = service.get_notes(db, current, session_id)
    return {
        "session_id": session_id,
        "notes": [_note_out(n) for n in notes],
    }


@router.patch("/notes/{note_id}")
def update_note(
    note_id: str,
    req: UpdateNoteRequest,
    db: DBSession = Depends(get_db),
    current: Physician = Depends(get_current_physician),
):
    if not req.content.strip():
        raise HTTPException(status_code=422, detail="Notizinhalt darf nicht leer sein.")
    note = service.update_note(db, current, note_id, req.content)
    if not note:
        raise HTTPException(status_code=404, detail="Notiz nicht gefunden oder gehört nicht Ihnen.")
    return _note_out(note)


@router.delete("/notes/{note_id}")
def delete_note(
    note_id: str,
    db: DBSession = Depends(get_db),
    current: Physician = Depends(get_current_physician),
):
    deleted = service.delete_note(db, current, note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Notiz nicht gefunden oder gehört nicht Ihnen.")
    return {"message": "Notiz gelöscht."}


@router.get("/audit")
def get_audit_logs(
    session_id: Optional[str] = None,
    limit:  int = 50,
    offset: int = 0,
    db: DBSession = Depends(get_db),
    current: Physician = Depends(get_current_physician),
):
    result = service.get_audit_logs(db, current, session_id=session_id, limit=limit, offset=offset)
    return {
        "total": result["total"],
        "logs": [
            {
                "id":           l.id,
                "session_id":   l.session_id,
                "patient_id":   l.patient_id,
                "action":       l.action,
                "ip_address":   l.ip_address,
                "accessed_at":  l.accessed_at.isoformat(),
            }
            for l in result["logs"]
        ],
    }