
import requests
from dataclasses import dataclass, field
from typing import Optional

import chromadb
from chromadb.config import Settings
from app.prompts.system_prompt import system_prompt as SYSTEM_PROMPT


# SYSTEM_PROMPT = """Du bist ein medizinischer Assistent für das HalloDOC-System.
# Deine Aufgabe ist es, Patienten auf Basis medizinischer Leitlinien zu informieren.

# REGELN:
# 1. Nutze die bereitgestellten Dokumentenabschnitte als Grundlage deiner Antwort.
# 2. Fasse die relevanten Informationen aus den Dokumenten zusammen und beantworte
#    die Frage des Patienten verständlich — auch wenn die Frage nicht wörtlich
#    im Dokument steht. Schlussfolgerungen aus dem Kontext sind erlaubt.
# 3. Erfinde KEINE Fakten, Medikamente, Dosierungen oder Diagnosen die nicht
#    aus den Dokumenten ableitbar sind.
# 4. Wenn die Dokumente wirklich keine relevanten Informationen enthalten, sage:
#    "Dazu habe ich leider keine Information in meinen Unterlagen."
# 5. Bei Notfallsymptomen (Brustschmerz, Lähmung, starke Atemnot) weise auf
#    den Notruf 112 hin.
# 6. Schließe jede Antwort mit dem Hinweis ab, dass ein Arzt konsultiert
#    werden sollte für eine persönliche Diagnose.

# Antworte auf Deutsch, einfühlsam und klar verständlich — auch für Nicht-Mediziner."""


@dataclass
class RAGResponse:
    answer: str
    sources: list[str] = field(default_factory=list)
    chunks_used: int = 0
    context_found: bool = True


class RAGQuery:
    def __init__(
        self,
        ollama_url: str,
        ollama_model: str,
        embedding_model: str,
        chroma_host: str,
        chroma_port: int,
        collection_name: str,
        chroma_token: str = "",
        top_k: int = 5,
    ):
        self.ollama_url     = ollama_url.rstrip("/")
        self.ollama_model   = ollama_model
        self.embedding_model = embedding_model
        self.top_k          = top_k

        headers = {"Authorization": f"Bearer {chroma_token}"} if chroma_token else {}
        self.chroma = chromadb.HttpClient(
            host=chroma_host,
            port=chroma_port,
            headers=headers,
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.chroma.get_or_create_collection(collection_name)


    def query(self, question: str, conversation_history: list[dict] | None = None, session_id: Optional[str] = None) -> RAGResponse:
        """
        Full RAG pipeline: embed → retrieve → generate.
        Returns a RAGResponse with answer + sources.
        """
        question_embedding = self._embed(question)

        results = self.collection.query(
            query_embeddings=[question_embedding],
            n_results=self.top_k,
            include=["documents", "metadatas", "distances"],
        )

        docs      = results["documents"][0]      # list of chunk texts
        metadatas = results["metadatas"][0]      # list of metadata dicts
        distances = results["distances"][0]      # cosine distances (lower = better)

        relevant = [
            (doc, meta, dist)
            for doc, meta, dist in zip(docs, metadatas, distances)
            if dist < 0.85
        ]

        if not relevant:
            return RAGResponse(
                answer=(
                    "Diese Information ist in meinen medizinischen Unterlagen "
                    "nicht vorhanden. Bitte wenden Sie sich an Ihren Arzt."
                ),
                context_found=False,
            )

        context_parts = []
        sources = []
        for i, (doc, meta, _) in enumerate(relevant, 1):
            source = meta.get("source_file") or meta.get("source", "Unbekannt")
            section = meta.get("section", "")
            label = f"[{i}] {source}" + (f" — {section}" if section else "")
            context_parts.append(f"{label}:\n{doc}")
            if source not in sources:
                sources.append(source)

        context = "\n\n".join(context_parts)

        prompt = self._build_prompt(context, question)

        answer = self._generate(prompt, conversation_history or [])

        return RAGResponse(
            answer=answer,
            sources=sources,
            chunks_used=len(relevant),
            context_found=True,
        )


    def _embed(self, text: str) -> list[float]:
        resp = requests.post(
            f"{self.ollama_url}/api/embed",
            json={"model": self.embedding_model, "input": [text[:1500]]},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["embeddings"][0]


    def _build_prompt(self, context: str, question: str) -> str:
        return (
            f"Hier sind relevante Abschnitte aus medizinischen Leitlinien:\n\n"
            f"{context}\n\n"
            f"{'─' * 60}\n\n"
            f"Patient schreibt: {question}\n\n"
            f"Beantworte die Frage des Patienten auf Basis der obigen Abschnitte. "
            f"Fasse die relevanten Informationen zusammen und erkläre sie verständlich. "
            f"Du darfst aus dem Kontext schlussfolgern — aber keine Fakten erfinden "
            f"die nicht aus den Abschnitten ableitbar sind."
        )


    def _generate(self, prompt: str, conversation_history: list[dict]) -> str:
        resp = requests.post(
            f"{self.ollama_url}/api/chat",
            json={
                "model": self.ollama_model,
                "stream": False,

                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]