"""
chat_router.py — Protected chat endpoints. Requires valid JWT.

Endpoints:
    POST /chat/message          — standard request/response
    POST /chat/message/stream   — streaming (token by token, like Claude)
    GET  /chat/sessions         — all sessions for logged-in patient
    GET  /chat/session/{id}/messages — full history of a session
    POST /chat/session/{id}/close   — close + generate AI summary
"""
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.chat.chat_service import ChatService
from app.core.config import config
from app.auth.dependencies import get_current_patient
from app.models.database import get_db
from app.models.models import Message
from app.models.models import Patient
from app.models.models import Session as ChatSession

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
    chunks_used: int


@router.post("/message", response_model=ChatResponse)
def send_message(
    req: ChatRequest,
    db: DBSession = Depends(get_db),
    current_patient: Patient = Depends(get_current_patient),
):
    """Send a message, get a complete response."""
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


@router.post("/message/stream")
def send_message_stream(
    req: ChatRequest,
    db: DBSession = Depends(get_db),
    current_patient: Patient = Depends(get_current_patient),
):
    """
    Streaming response — tokens arrive one by one like Claude/ChatGPT.
    The session and messages are saved to DB after the stream completes.

    Client reads a text/event-stream:
        data: {"token": "Guten"}\n\n
        data: {"token": " Tag"}\n\n
        data: {"done": true, "session_id": "...", "sources": [...]}\n\n
    """
    # Setup session + history before streaming
    session = service.get_or_create_session(db, current_patient.id, req.session_id)
    history = service._load_history(db, session.id)

    # Store user message immediately
    user_msg = Message(session_id=session.id, role="user", content=req.message)
    db.add(user_msg)
    db.commit()

    # Get RAG context (non-streaming part)
    embedding = service.rag._embed(req.message)
    results = service.rag.collection.query(
        query_embeddings=[embedding],
        n_results=8,
        include=["documents", "metadatas", "distances"],
    )
    relevant = [
        (doc, meta)
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
        if dist < 0.85
    ]
    sources = list({
        meta.get("source_file") or meta.get("source", "Leitlinie")
        for _, meta in relevant
    })
    context = "\n\n".join(
        f"[{i}] {meta.get('source_file', '')}:\n{doc}"
        for i, (doc, meta) in enumerate(relevant, 1)
    ) or "Kein spezifischer Kontext gefunden."

    messages = service.rag._build_messages(history, req.message, context)

    def stream_generator():
        full_answer = []
        try:
            resp = requests.post(
                f"{config.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model":  config.OLLAMA_MODEL,
                    "stream": True,          # key difference
                    "options": {
                        "temperature": 0.2,
                        "num_ctx": 8192,
                    },
                    "messages": messages,
                },
                stream=True,
                timeout=120,
            )

            import json
            for line in resp.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                if token:
                    full_answer.append(token)
                    yield f"data: {json.dumps({'token': token})}\n\n"

                if chunk.get("done"):
                    # Save AI message to DB
                    answer = "".join(full_answer)
                    ai_msg = Message(
                        session_id=session.id,
                        role="assistant",
                        content=answer,
                        sources=sources,
                    )
                    db.add(ai_msg)

                    # Update urgency
                    urgency = service._detect_urgency(answer)
                    if urgency != "none":
                        session.urgency = urgency
                    if urgency == "emergency":
                        session.status = "active"  # Ensure session is active if emergency detected
                        service._generate_summary(db, session.id)  # Generate summary immediately for emergency
                    db.commit()

                    # Send final metadata
                    yield f"data: {json.dumps({'done': True, 'session_id': session.id, 'message_id': ai_msg.id, 'sources': sources, 'urgency': urgency})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering if used
        },
    )


@router.get("/sessions")
def get_sessions(
    db: DBSession = Depends(get_db),
    current_patient: Patient = Depends(get_current_patient),
):
    sessions = service.get_patient_sessions(db, current_patient.id)
    return [
        {
            "session_id":    s.id,
            "status":        s.status,
            "urgency":       s.urgency,
            "created_at":    s.created_at.isoformat(),
            "updated_at":    s.updated_at.isoformat(),
            "message_count": len(s.messages),
            "summary":       s.summary,
        }
        for s in sessions
    ]


@router.get("/session/{session_id}/messages")
def get_messages(
    session_id: str,
    db: DBSession = Depends(get_db),
    current_patient: Patient = Depends(get_current_patient),
):
    """Full message history — used to restore a conversation."""
    session = service.get_session(db, session_id, current_patient.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session nicht gefunden.")
    return {
        "session_id": session.id,
        "status":     session.status,
        "urgency":    session.urgency,
        "messages": [
            {
                "id":         m.id,
                "role":       m.role,
                "content":    m.content,
                "sources":    m.sources,
                "created_at": m.created_at.isoformat(),
            }
            for m in session.messages
        ],
    }


@router.post("/session/{session_id}/close")
def close_session(
    session_id: str,
    db: DBSession = Depends(get_db),
    current_patient: Patient = Depends(get_current_patient),
):
    """Close a session and generate an AI clinical summary for the physician."""
    session = service.get_session(db, session_id, current_patient.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session nicht gefunden.")
    closed = service.close_session(db, session_id)
    return {
        "status":  "closed",
        "summary": closed.summary,
    }