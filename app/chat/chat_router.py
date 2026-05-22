
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession
from app.chat.chat_service import ChatService
from app.models.database import get_db
from app.auth.dependencies import get_current_patient
from app.models.models import Patient
router = APIRouter(prefix="/chat", tags=["Chat"])
service = ChatService()



class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    message_id: str
    answer: str
    sources: list[str]
    urgency: str 
    context_found: bool


class SessionSummary(BaseModel):
    session_id: str
    status: str
    urgency: str
    created_at: str
    message_count: int



@router.post("/message", response_model=ChatResponse)
def send_message(req: ChatRequest, db: DBSession = Depends(get_db), current_patient: Patient = Depends(get_current_patient),):
    """
    Send a message to the AI. Pass session_id to continue an existing
    conversation, or omit it to start a new one.
    """
    try:
        result = service.chat(
            db=db,
            patient_id=current_patient.id,
            user_message=req.message,
            session_id=req.session_id,
        )
        return ChatResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{patient_id}", response_model=list[SessionSummary])
def get_sessions(patient_id: str, db: DBSession = Depends(get_db), current_patient: Patient = Depends(get_current_patient),):
    """Return all sessions for a user, newest first."""
    sessions = service.get_user_sessions(db, patient_id)
    return [
        SessionSummary(
            session_id=s.id,
            status=s.status,
            # urgency=s.urgency,
            created_at=s.created_at.isoformat(),
            message_count=len(s.messages),
        )
        for s in sessions
    ]


@router.get("/session/{session_id}/messages")
def get_messages(session_id: str, patient_id: str, db: DBSession = Depends(get_db), current_patient: Patient = Depends(get_current_patient),):
    """Return all messages in a session (for resuming a conversation)."""
    session = service.get_session(db, session_id, patient_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return [
        {
            "id":         m.id,
            "role":       m.role,
            "content":    m.content,
            "sources":    m.sources,
            "created_at": m.created_at.isoformat(),
        }
        for m in session.messages
    ]


@router.post("/session/{session_id}/close")
def close_session(session_id: str, db: DBSession = Depends(get_db), current_patient: Patient = Depends(get_current_patient),):
    """Close a session and generate a summary."""
    session = service.close_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "closed", "summary": session.summary}