
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import pymupdf 

from .chunker import Chunk, MedicalChunker


class PDFIngestor:
    def __init__(self, chunker: MedicalChunker):
        self.chunker = chunker

    def ingest(
        self,
        pdf_path: str,
        metadata_override: Optional[dict] = None,
    ) -> List[Chunk]:
        """Ingest a single PDF file."""
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        doc = pymupdf.open(str(path))
        text_parts: List[str] = []

        for page_num, page in enumerate(doc, start=1):
            # "blocks" mode preserves reading order better for two-column layouts
            page_text = page.get_text("text")
            if page_text.strip():
                text_parts.append(page_text)

        doc.close()
        full_text = "\n".join(text_parts)

        if not full_text.strip():
            print(f"  ⚠ No extractable text in {path.name} (scanned PDF?)")
            return []

        base_metadata = {
            "source": path.name,
            "source_path": str(path.resolve()),
            "source_type": "pdf",
            "document_type": "leitlinie",
            "language": "de",
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "doc_id": hashlib.md5(path.name.encode()).hexdigest()[:10],
            **(metadata_override or {}),
        }

        return self.chunker.chunk(full_text, base_metadata)

    def ingest_directory(
        self,
        directory: str,
        metadata_override: Optional[dict] = None,
    ) -> List[Chunk]:
        """Ingest all PDFs in a directory."""
        pdf_files = sorted(Path(directory).glob("*.pdf"))
        if not pdf_files:
            print(f"  ⚠ No PDFs found in {directory}")
            return []

        all_chunks: List[Chunk] = []
        for pdf_file in pdf_files:
            print(f" {pdf_file.name}", end="  ", flush=True)
            try:
                chunks = self.ingest(str(pdf_file), metadata_override)
                all_chunks.extend(chunks)
                print(f"→ {len(chunks)} chunks")
            except Exception as exc:
                print(f"→ ERROR: {exc}")

        return all_chunks