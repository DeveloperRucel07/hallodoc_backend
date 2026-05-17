"""
chat_service.py — Business logic for chat sessions and messages.

Handles:
- Creating / resuming sessions
- Storing user + AI messages
- Passing conversation history to the RAG pipeline
- Detecting urgency from AI responses
"""
import json
import re
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from app.chat.models import Message, Session
from app.core.config import config
from app.ingestion.rag_query import RAGQuery, RAGResponse


# ── Urgency keywords ──────────────────────────────────────────────────────────
# If the AI response contains these, we escalate the session urgency level
URGENT_KEYWORDS = [
    "notruf", "112", "notfall", "sofort", "lebensbedrohlich",
    "herzinfarkt", "schlaganfall", "bewusstlos", "atemnot",
    "sofortige behandlung", "sofort arzt",
]
ROUTINE_KEYWORDS = [
    "hausarzt", "termin", "ambulant", "überweisung",
    "in den nächsten", "nicht dringend",
]


class ChatService:
    def __init__(self):
        self.rag = RAGQuery(
            ollama_url=config.OLLAMA_BASE_URL,
            ollama_model=config.OLLAMA_MODEL,
            embedding_model=config.EMBEDDING_MODEL,
            chroma_host=config.CHROMA_HOST,
            chroma_port=config.CHROMA_PORT,
            collection_name=config.COLLECTION_NAME,
            chroma_token=config.CHROMA_TOKEN,
        )

    # ── Session management ────────────────────────────────────────────────────

    def get_or_create_session(
        self,
        db: DBSession,
        user_id: str,
        session_id: Optional[str] = None,
    ) -> Session:
        """
        Resume an existing session by ID, or create a new one.
        This is how users continue a previous consultation.
        """
        if session_id:
            session = db.query(Session).filter(
                Session.id == session_id,
                Session.user_id == user_id,
                Session.status == "active",
            ).first()
            if session:
                return session

        # Create new session
        session = Session(user_id=user_id)
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    def get_session(self, db: DBSession, session_id: str, user_id: str) -> Optional[Session]:
        return db.query(Session).filter(
            Session.id == session_id,
            Session.user_id == user_id,
        ).first()

    def get_user_sessions(self, db: DBSession, user_id: str) -> list[Session]:
        return (
            db.query(Session)
            .filter(Session.user_id == user_id)
            .order_by(Session.updated_at.desc())
            .all()
        )

    # ── Core chat logic ───────────────────────────────────────────────────────

    def chat(
        self,
        db: DBSession,
        user_id: str,
        user_message: str,
        session_id: Optional[str] = None,
    ) -> dict:
        """
        Main entry point. Handles:
        1. Get or create session
        2. Store user message
        3. Build conversation history for context
        4. Query RAG
        5. Store AI response
        6. Detect urgency
        7. Return full response
        """
        # 1. Session
        session = self.get_or_create_session(db, user_id, session_id)

        # 2. Store user message
        user_msg = Message(
            session_id=session.id,
            role="user",
            content=user_message,
        )
        db.add(user_msg)
        db.commit()

        # 3. Build conversation history (last 10 messages for context)
        history = self._build_history(db, session.id)

        # 4. Query RAG with history context
        rag_response: RAGResponse = self.rag.query(
            question=user_message,
            conversation_history=history,
        )

        # 5. Store AI response
        ai_msg = Message(
            session_id=session.id,
            role="assistant",
            content=rag_response.answer,
            sources=rag_response.sources,
        )
        db.add(ai_msg)

        # 6. Detect urgency and update session
        urgency = self._detect_urgency(rag_response.answer)
        if urgency != "none":
            session.urgency = urgency
            if urgency == "emergency":
                session.status = "urgent"

        db.commit()

        return {
            "session_id":    session.id,
            "message_id":    ai_msg.id,
            "answer":        rag_response.answer,
            "sources":       rag_response.sources,
            "urgency":       urgency,
            "context_found": rag_response.context_found,
            "chunks_used":   rag_response.chunks_used,
        }

    def close_session(self, db: DBSession, session_id: str, summary: str = "") -> Session:
        """Close a session and store a summary."""
        session = db.query(Session).filter(Session.id == session_id).first()
        if session:
            session.status = "closed"
            session.summary = summary or self._auto_summary(db, session_id)
            db.commit()
        return session

    # ── History builder ───────────────────────────────────────────────────────

    def _build_history(self, db: DBSession, session_id: str) -> list[dict]:
        """
        Return the last 10 messages as a list of {role, content} dicts
        for passing to the LLM as conversation context.
        """
        messages = (
            db.query(Message)
            .filter(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(10)
            .all()
        )
        return [{"role": m.role, "content": m.content} for m in reversed(messages)]



    def _detect_urgency(self, answer: str) -> str:
        answer_lower = answer.lower()
        if any(kw in answer_lower for kw in URGENT_KEYWORDS):
            return "emergency"
        if any(kw in answer_lower for kw in ROUTINE_KEYWORDS):
            return "routine"
        return "none"


    def _auto_summary(self, db: DBSession, session_id: str) -> str:
        """Build a simple summary from user messages."""
        user_messages = (
            db.query(Message)
            .filter(Message.session_id == session_id, Message.role == "user")
            .order_by(Message.created_at)
            .all()
        )
        symptoms = [m.content for m in user_messages[:5]]
        return "Symptome: " + " | ".join(symptoms)