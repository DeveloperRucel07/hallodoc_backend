
import requests
from dataclasses import dataclass, field
from typing import Optional

import chromadb
from chromadb.config import Settings
from app.prompts.system_prompt import system_prompt as SYSTEM_PROMPT


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
        history = conversation_history or []
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
                    "Dazu habe ich leider keine passenden Informationen in meinen "
                    "Unterlagen. Ich empfehle Ihnen, direkt einen Arzt aufzusuchen."
                ),
                context_found=False,
            )

        context_parts = []
        sources = []
        for i, (doc, meta, _) in enumerate(relevant, 1):
            source = meta.get("source_file") or meta.get("source", "Leitlinie")
            section = meta.get("section", "")
            label = f"[{i}] {source}" + (f" — {section}" if section else "")
            context_parts.append(f"{label}:\n{doc}")
            if source not in sources:
                sources.append(source)

        context = "\n\n".join(context_parts)

        messages = self._build_messages(history, question, context)

        answer = self._generate(messages)

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


    def _build_messages(self, history: list[dict], context: str, question: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        messages.extend(history)
        current_prompt = (
            f"Relevante Informationen aus den medizinischen Leitlinien:\n\n"
            f"{context}\n\n"
            f"{'─' * 50}\n\n"
            f"Patient: {question}\n\n"
            f"Beantworte die Frage auf Basis der Leitlinien und des bisherigen "
            f"Gesprächsverlaufs. Fasse relevante frühere Symptome mit ein."
        )
        messages.append({"role": "user", "content": current_prompt})
        return messages
    

    def _generate(self, messages: list[dict]) -> str:
        resp = requests.post(
            f"{self.ollama_url}/api/chat",
            json={
                "model":  self.ollama_model,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "top_p":       0.9,
                    "num_ctx":     8192,
                },
                "messages": messages,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]