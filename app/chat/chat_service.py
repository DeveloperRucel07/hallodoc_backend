
import requests
from typing import Generator, Optional

from sqlalchemy.orm import Session as DBSession

from app.core.config import config
from app.ingestion.rag_query import RAGQuery, RAGResponse
from app.models.models import Message
from app.models.models import Session as ChatSession

URGENT_KEYWORDS = [
    "notruf", "112", "notfall", "sofort", "lebensbedrohlich",
    "herzinfarkt", "schlaganfall", "bewusstlos", "starke atemnot",
]
ROUTINE_KEYWORDS = [
    "hausarzt", "termin vereinbaren", "ambulant", "nicht dringend",
    "in den nächsten tagen",
]

# Max history turns sent to the model per request (1 turn = 1 user + 1 AI message)
MAX_HISTORY_TURNS = 10


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
        patient_id: str,
        session_id: Optional[str] = None,
    ) -> ChatSession:
        """Resume active session or create a new one."""
        if session_id:
            session = db.query(ChatSession).filter(
                ChatSession.id == session_id,
                ChatSession.patient_id == patient_id,
                ChatSession.status == "active",
            ).first()
            if session:
                return session

        session = ChatSession(patient_id=patient_id)
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    def get_session(
        self, db: DBSession, session_id: str, patient_id: str
    ) -> Optional[ChatSession]:
        return db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.patient_id == patient_id,
        ).first()

    def get_patient_sessions(
        self, db: DBSession, patient_id: str
    ) -> list[ChatSession]:
        return (
            db.query(ChatSession)
            .filter(ChatSession.patient_id == patient_id)
            .order_by(ChatSession.updated_at.desc())
            .all()
        )

    # ── Core chat ─────────────────────────────────────────────────────────────

    def chat(
        self,
        db: DBSession,
        patient_id: str,
        user_message: str,
        session_id: Optional[str] = None,
    ) -> dict:
        # 1. Get or create session
        session = self.get_or_create_session(db, patient_id, session_id)

        # 2. Load history BEFORE storing the new message
        #    so the current message is never accidentally in the history
        history = self._load_history(db, session.id)

        # 3. Store user message
        user_msg = Message(
            session_id=session.id,
            role="user",
            content=user_message,
        )
        db.add(user_msg)
        db.commit()

        # 4. Query RAG — history gives the model full conversation memory
        rag_response: RAGResponse = self.rag.query(
            question=user_message,
            conversation_history=history,
        )

        # 5. Store AI response with sources
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
            session.status = "active"  # Ensure session is active if emergency detected
            self._generate_summary(db, session.id)  # Generate summary immediately for emergency

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

    # ── Memory ────────────────────────────────────────────────────────────────

    def _load_history(self, db: DBSession, session_id: str) -> list[dict]:
        """
        Load the last N turns from DB as {role, content} dicts.
        Returned in chronological order (oldest first) so the model
        reads the conversation naturally.
        """
        messages = (
            db.query(Message)
            .filter(
                Message.session_id == session_id,
                Message.role.in_(["user", "assistant"]),
            )
            .order_by(Message.created_at.desc())
            .limit(MAX_HISTORY_TURNS * 2)   # *2 because each turn = user + assistant
            .all()
        )
        # Reverse: DB returns newest first, model needs oldest first
        return [
            {"role": m.role, "content": m.content}
            for m in reversed(messages)
        ]

    # ── Urgency detection ─────────────────────────────────────────────────────

    def _detect_urgency(self, answer: str) -> str:
        lower = answer.lower()
        if any(kw in lower for kw in URGENT_KEYWORDS):
            return "emergency"
        if any(kw in lower for kw in ROUTINE_KEYWORDS):
            return "routine"
        return "none"

    # ── Session close + AI summary ────────────────────────────────────────────

    def close_session(self, db: DBSession, session_id: str) -> ChatSession:
        """
        Close a session and generate a proper AI summary of the conversation
        to send to the physician.
        """
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if session:
            session.status  = "closed"
            session.summary = self._generate_summary(db, session_id)
            db.commit()
        return session

    def _generate_summary(self, db: DBSession, session_id: str) -> str:
        """
        Ask Ollama to write a clinical summary of the conversation
        suitable for the physician to read before the appointment.
        """
        messages = (
            db.query(Message)
            .filter(
                Message.session_id == session_id,
                Message.role.in_(["user", "assistant"]),
            )
            .order_by(Message.created_at)
            .all()
        )

        if not messages:
            return "Keine Nachrichten in dieser Sitzung."

        # Format conversation for summary prompt
        conversation = "\n".join(
            f"{'Patient' if m.role == 'user' else 'KI-Assistent'}: {m.content}"
            for m in messages
        )

        summary_prompt = (
            f"Fasse das folgende Patientengespräch als klinische Zusammenfassung "
            f"für den behandelnden Arzt zusammen. Halte es sachlich und präzise.\n\n"
            f"Gespräch:\n{conversation}\n\n"
            f"Zusammenfassung (auf Deutsch, max. 5 Sätze):"
        )

        try:
            resp = requests.post(
                f"{config.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model":  config.OLLAMA_MODEL,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_ctx": 4096},
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Du bist ein klinischer Dokumentationsassistent. "
                                "Schreibe präzise medizinische Zusammenfassungen auf Deutsch."
                            ),
                        },
                        {"role": "user", "content": summary_prompt},
                    ],
                },
                timeout=60,
            )
            return resp.json()["message"]["content"]
        except Exception as exc:
            # Fallback to simple summary if AI call fails
            user_msgs = [m.content for m in messages if m.role == "user"]
            return "Symptome: " + " | ".join(user_msgs[:5])