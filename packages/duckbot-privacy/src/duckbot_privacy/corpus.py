"""The test corpus, and how to extend it.

Documents are written with inline markers::

    新同事[[PERSON_NAME:陳嘉雯]]將於下月報到，身份證號碼[[HKID:Z683365(3)]]。

The loader strips the markers and computes character offsets, so whoever adds a document
writes readable text instead of counting characters. Hand-maintained offset tables rot
within a week, and a corpus nobody will extend is a corpus that stops being true.

**Every value in this corpus is invented.** No real person, company, client or address
appears in it, and none should. If a real document is ever used as the basis for a test
case, the identifying values must be replaced before it is committed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_MARKER = re.compile(r"\[\[(?P<type>[A-Z_]+):(?P<value>.*?)\]\]", re.DOTALL)


@dataclass(frozen=True)
class Span:
    entity_type: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Document:
    id: str
    language: str
    description: str
    text: str
    spans: tuple[Span, ...]


def parse_marked(marked: str) -> tuple[str, tuple[Span, ...]]:
    """Strip markers, returning clean text and the spans they described."""
    spans: list[Span] = []
    out: list[str] = []
    cursor = 0
    position = 0
    for match in _MARKER.finditer(marked):
        literal = marked[cursor : match.start()]
        out.append(literal)
        position += len(literal)

        value = match.group("value")
        spans.append(
            Span(
                entity_type=match.group("type"),
                start=position,
                end=position + len(value),
                text=value,
            )
        )
        out.append(value)
        position += len(value)
        cursor = match.end()

    tail = marked[cursor:]
    out.append(tail)
    return "".join(out), tuple(spans)


def load_documents(path: Path | str) -> list[Document]:
    """Load a corpus file. One JSON array of ``{id, language, description, marked}``."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    documents: list[Document] = []
    for item in raw:
        text, spans = parse_marked(item["marked"])
        documents.append(
            Document(
                id=item["id"],
                language=item["language"],
                description=item["description"],
                text=text,
                spans=spans,
            )
        )
    return documents
