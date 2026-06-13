
import os
import uuid
from typing import List, Optional

import requests
import chromadb
from chromadb.config import Settings

from .chunker import Chunk


class ChromaStore:
    def __init__(
        self,
        host: str,
        port: int,
        collection_name: str,
        ollama_url: str,
        embedding_model: str,
        chroma_token: Optional[str] = None,
    ):
        self.ollama_url = ollama_url.rstrip("/")
        self.embedding_model = embedding_model

        # Auth token: param → env var → None (no auth, for local dev without token)
        token = chroma_token or os.environ.get("CHROMA_TOKEN")

        if token:
            self.client = chromadb.HttpClient(
                host=host,
                port=port,
                headers={"Authorization": f"Bearer {token}"},
                settings=Settings(anonymized_telemetry=False),
            )
        else:
            # No token configured — works for local ChromaDB without auth
            self.client = chromadb.HttpClient(
                host=host,
                port=port,
                settings=Settings(anonymized_telemetry=False),
            )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={
                "hnsw:space": "cosine",
                "description": "Medical RAG — Germany",
            },
        )
        print(f"  ✓ Collection '{collection_name}' ready "
              f"({self.collection.count()} chunks already stored)")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store_chunks(self, chunks: List[Chunk], batch_size: int = 32) -> None:
        """Embed and upsert chunks into ChromaDB in batches."""
        if not chunks:
            print("  ⚠ No chunks to store.")
            return

        total = len(chunks)
        num_batches = (total - 1) // batch_size + 1

        for batch_num, start in enumerate(range(0, total, batch_size), 1):
            batch = chunks[start : start + batch_size]
            texts = [c.text for c in batch]
            metadatas = self._sanitize_metadatas([c.metadata for c in batch])
            ids = [str(uuid.uuid4()) for _ in batch]

            print(
                f"    Embedding batch {batch_num}/{num_batches} "
                f"({len(batch)} chunks)…",
                end=" ",
                flush=True,
            )
            embeddings = self._embed_batch(texts)
            print("storing…", end=" ", flush=True)

            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
            print("✓")

    def count(self) -> int:
        return self.collection.count()

    # ------------------------------------------------------------------
    # Embedding via Ollama
    # ------------------------------------------------------------------

    # nomic-embed-text: 2048 tokens max
    # ~3 chars/token for German medical text (longer words than English)
    # 512 tokens * 3 = 1536 chars — conservative safe limit
    MAX_CHARS = 1500

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed one text at a time so a single oversized chunk never
        kills the whole batch. Truncates to MAX_CHARS before sending.
        """
        embeddings = []
        for text in texts:
            safe = text[:self.MAX_CHARS]
            try:
                resp = requests.post(
                    f"{self.ollama_url}/api/embed",
                    json={"model": self.embedding_model, "input": [safe]},
                    timeout=60,
                )
                resp.raise_for_status()
                embeddings.append(resp.json()["embeddings"][0])
            except Exception as e:
                print(f"\n  ⚠ Embedding failed for chunk ({len(text)} chars): {e}")
                # fallback: use a zero vector so ingestion continues
                embeddings.append([0.0] * 768)
        return embeddings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_metadatas(metadatas: List[dict]) -> List[dict]:
        """
        ChromaDB only accepts str / int / float / bool in metadata.
        Convert anything else to string.
        """
        clean = []
        for meta in metadatas:
            clean.append(
                {
                    k: v if isinstance(v, (str, int, float, bool)) else str(v)
                    for k, v in meta.items()
                }
            )
        return clean