
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.chat.chat_service import ChatService
from app.chat.database import get_db

router = APIRouter(prefix="/chat", tags=["Chat"])
service = ChatService()



class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: Optional[str] = None   # omit to start a new session


class ChatResponse(BaseModel):
    session_id: str
    message_id: str
    answer: str
    sources: list[str]
    urgency: str          # none | routine | emergency
    context_found: bool


class SessionSummary(BaseModel):
    session_id: str
    status: str
    urgency: str
    created_at: str
    message_count: int



@router.post("/message", response_model=ChatResponse)
def send_message(req: ChatRequest, db: DBSession = Depends(get_db)):
    """
    Send a message to the AI. Pass session_id to continue an existing
    conversation, or omit it to start a new one.
    """
    try:
        result = service.chat(
            db=db,
            user_id=req.user_id,
            user_message=req.message,
            session_id=req.session_id,
        )
        return ChatResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{user_id}", response_model=list[SessionSummary])
def get_sessions(user_id: str, db: DBSession = Depends(get_db)):
    """Return all sessions for a user, newest first."""
    sessions = service.get_user_sessions(db, user_id)
    return [
        SessionSummary(
            session_id=s.id,
            status=s.status,
            urgency=s.urgency,
            created_at=s.created_at.isoformat(),
            message_count=len(s.messages),
        )
        for s in sessions
    ]


@router.get("/session/{session_id}/messages")
def get_messages(session_id: str, user_id: str, db: DBSession = Depends(get_db)):
    """Return all messages in a session (for resuming a conversation)."""
    session = service.get_session(db, session_id, user_id)
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
def close_session(session_id: str, db: DBSession = Depends(get_db)):
    """Close a session and generate a summary."""
    session = service.close_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "closed", "summary": session.summary}