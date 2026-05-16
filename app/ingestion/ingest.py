"""
ingest.py — Orchestrate the full Medical RAG ingestion pipeline.

Usage:
    python ingest.py                    # ingest everything (PDFs + web)
    python ingest.py --pdfs-only        # only AWMF PDFs
    python ingest.py --web-only         # only web sources
    python ingest.py --stats            # just show collection stats
"""
import argparse
import sys
import time

from app.core.config import config
from app.ingestion.chunker import MedicalChunker
from app.ingestion.chroma_store import ChromaStore
from app.ingestion.pdf_ingestor import PDFIngestor



def build_store() -> ChromaStore:
    return ChromaStore(
        host=config.CHROMA_HOST,
        port=config.CHROMA_PORT,
        collection_name=config.COLLECTION_NAME,
        ollama_url=config.OLLAMA_BASE_URL,
        embedding_model=config.EMBEDDING_MODEL,
        chroma_token=config.CHROMA_TOKEN or None,
    )


def ingest_pdfs(store: ChromaStore, chunker: MedicalChunker) -> int:
    print("\n📄 PDF Ingestion (AWMF Leitlinien)")
    print("─" * 40)
    ingestor = PDFIngestor(chunker)
    chunks = ingestor.ingest_directory(config.PDF_DIR)
    if chunks:
        store.store_chunks(chunks)
    return len(chunks)


def main():
    parser = argparse.ArgumentParser(description="Medical RAG Ingestion")
    parser.add_argument("--pdfs-only", action="store_true")
    parser.add_argument("--web-only", action="store_true")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    print("═" * 50)
    print("  🏥 Medical RAG — Ingestion Pipeline")
    print(f"  Collection : {config.COLLECTION_NAME}")
    print(f"  Embedding  : {config.EMBEDDING_MODEL} via Ollama")
    print(f"  Chunk size : {config.CHUNK_SIZE} words / overlap {config.CHUNK_OVERLAP}")
    print("═" * 50)

    t0 = time.time()

    try:
        store = build_store()
    except Exception as exc:
        print(f"\n✗ Cannot connect to ChromaDB at "
              f"{config.CHROMA_HOST}:{config.CHROMA_PORT}\n  {exc}")
        sys.exit(1)

    if args.stats:
        print(f"\n📊 '{config.COLLECTION_NAME}': {store.count()} chunks stored")
        return

    chunker = MedicalChunker(
        max_chunk_size=config.CHUNK_SIZE,
        overlap=config.CHUNK_OVERLAP,
    )

    total_chunks = 0

    if not args.web_only:
        total_chunks += ingest_pdfs(store, chunker)

    # if not args.pdfs_only:
    #     total_chunks += ingest_web(store, chunker)

    elapsed = time.time() - t0
    print("\n" + "═" * 50)
    print(f"  ✅ Done in {elapsed:.1f}s")
    print(f"  Chunks ingested this run : {total_chunks}")
    print(f"  Total in collection      : {store.count()}")
    print("═" * 50)


if __name__ == "__main__":
    main()