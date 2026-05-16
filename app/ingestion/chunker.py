
import re
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)


class MedicalChunker:
    # Patterns that indicate a new section header in German medical docs
    HEADER_PATTERNS = [
        r"^#{1,4}\s+.+$",                      
        r"^\d+[\.\d]*\s+[A-ZÄÖÜ].{3,}$",        
        r"^[A-ZÄÖÜ][A-ZÄÖÜ\s\-]{6,}$",      
        r"^(Einleitung|Diagnos|Therap|Symptom|"
        r"Notfall|Ursach|Prognose|Prophylax|"
        r"Definition|Ätiologie|Epidemiologie|"
        r"Pathophysiologie|Klassifikation|"
        r"Differentialdiagnose|Komplikationen|"
        r"Behandlung|Medikament|Indikation|"
        r"Kontraindikation).{0,40}$",
    ]

    def __init__(self, max_chunk_size: int = 600, overlap: int = 80):
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap
        self._compiled = [
            re.compile(p, re.IGNORECASE | re.MULTILINE)
            for p in self.HEADER_PATTERNS
        ]


    def chunk(self, text: str, base_metadata: dict) -> List[Chunk]:
        """Split text into semantically coherent medical chunks."""
        text = self._clean(text)
        sections = self._split_into_sections(text)
        chunks: List[Chunk] = []

        for section_title, section_text in sections:
            if not section_text.strip():
                continue
            meta = {**base_metadata, "section": section_title}
            chunks.extend(self._chunk_section(section_text, meta))

        return chunks


    def _clean(self, text: str) -> str:
        """Remove boilerplate noise common in scraped/PDF medical text."""
        # Remove page markers added by PDF ingestor ("[Seite N]")
        text = re.sub(r"\[Seite \d+\]", "", text)
        # Collapse 3+ blank lines → 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Remove lone page numbers (a line with only digits)
        text = re.sub(r"^\s*\d+\s*$", "", text, flags=re.MULTILINE)
        return text.strip()

    def _is_header(self, line: str) -> bool:
        line = line.strip()
        if len(line) < 4 or len(line) > 120:
            return False
        return any(p.match(line) for p in self._compiled)

    def _split_into_sections(self, text: str) -> List[Tuple[str, str]]:
        lines = text.split("\n")
        sections: List[Tuple[str, str]] = []
        current_title = "Einleitung"
        current_lines: List[str] = []

        for line in lines:
            if self._is_header(line):
                if current_lines:
                    sections.append((current_title, "\n".join(current_lines).strip()))
                current_title = re.sub(r"^#+\s*", "", line).strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines:
            sections.append((current_title, "\n".join(current_lines).strip()))

        return sections or [("Dokument", text)]

    def _chunk_section(self, text: str, metadata: dict) -> List[Chunk]:
        """Sliding-window word-based chunking within a single section."""
        words = text.split()

        # Small enough → single chunk
        if len(words) <= self.max_chunk_size:
            return [Chunk(text=text.strip(), metadata=metadata)]

        chunks: List[Chunk] = []
        start = 0
        idx = 0

        while start < len(words):
            end = min(start + self.max_chunk_size, len(words))
            chunk_text = " ".join(words[start:end])
            chunks.append(
                Chunk(
                    text=chunk_text,
                    metadata={**metadata, "chunk_index": idx},
                )
            )
            idx += 1
            start += self.max_chunk_size - self.overlap  # slide with overlap

        return chunks