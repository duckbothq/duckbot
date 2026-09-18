"""Retrieval over local memory.

**This is lexical search, not semantic search, and it is labelled that way everywhere
it appears.** It is BM25 over the tokeniser in :mod:`duckbot_memory.tokenise`. It finds
memories that share words with the query. It will not find 「租約」 when you ask about
「tenancy agreement」, and it will not find a paraphrase.

That is a deliberate first step, not an oversight. The alternatives were to add an
embedding model as a dependency before anyone has measured whether retrieval quality is
the bottleneck, or to ship something that calls itself semantic and is not. Lexical
search on a few thousand memories is fast, has no dependencies, is completely
predictable, and — because the whole thing is one small file — is cheap to replace once
:class:`Embedder` has a real implementation behind it.

The ``Embedder`` seam is here so that replacing it does not mean rewriting the compiler.
Note the one rule it carries: an embedder that is not local may never see a LOCAL_ONLY
memory. :class:`~duckbot_schemas.MemoryItem` refuses to record that combination, and
:class:`EmbeddingIndex` refuses to create it.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

from duckbot_schemas import MemoryItem, SensitivityLevel

from .errors import LocalOnlyViolation
from .tokenise import tokenise

_K1 = 1.5
"""Term-frequency saturation. The standard value; nobody here has tuned it on real data,
and pretending otherwise by picking an unusual number would be worse."""

_B = 0.75
"""Length normalisation. Same."""


@dataclass(frozen=True)
class Hit:
    item: MemoryItem
    score: float


@dataclass
class LexicalIndex:
    """BM25 over memory text. Rebuilt in full; at this scale that is the simple answer."""

    _docs: dict[str, list[str]] = field(default_factory=dict)
    _items: dict[str, MemoryItem] = field(default_factory=dict)
    _df: Counter[str] = field(default_factory=Counter)

    def add(self, item: MemoryItem) -> None:
        if item.id in self._docs:
            self.remove(item.id)
        tokens = tokenise(item.text)
        self._docs[item.id] = tokens
        self._items[item.id] = item
        for term in set(tokens):
            self._df[term] += 1

    def remove(self, item_id: str) -> bool:
        tokens = self._docs.pop(item_id, None)
        if tokens is None:
            return False
        self._items.pop(item_id, None)
        for term in set(tokens):
            self._df[term] -= 1
            if self._df[term] <= 0:
                del self._df[term]
        return True

    def rebuild(self, items: list[MemoryItem]) -> None:
        self._docs.clear()
        self._items.clear()
        self._df.clear()
        for item in items:
            self.add(item)

    def __len__(self) -> int:
        return len(self._docs)

    @property
    def _average_length(self) -> float:
        if not self._docs:
            return 0.0
        return sum(len(t) for t in self._docs.values()) / len(self._docs)

    def search(self, query: str, *, limit: int = 20) -> list[Hit]:
        """Memories sharing terms with the query, best first.

        Ties are broken by recency, then by id, so the same query over the same store
        always returns the same order. A retrieval layer that shuffles equal-scoring
        results makes every bug report above it irreproducible.
        """
        terms = tokenise(query)
        if not terms or not self._docs:
            return []

        total = len(self._docs)
        average = self._average_length
        scored: list[Hit] = []

        for item_id, tokens in self._docs.items():
            counts = Counter(tokens)
            length = len(tokens)
            score = 0.0
            for term in terms:
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                df = self._df.get(term, 0)
                idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
                denominator = frequency + _K1 * (1 - _B + _B * length / average)
                score += idf * (frequency * (_K1 + 1)) / denominator
            if score > 0:
                scored.append(Hit(item=self._items[item_id], score=score))

        scored.sort(key=lambda h: (-h.score, -h.item.created_at.timestamp(), h.item.id))
        return scored[:limit]


class Embedder(Protocol):
    """A future home for a real model. Nothing in this package implements one yet.

    ``is_local`` is not decoration. It is the fact the rest of the system reasons about:
    whether using this embedder means the text left the machine.
    """

    @property
    def is_local(self) -> bool: ...

    def embed(self, text: str) -> list[float]: ...


class EmbeddingIndex:
    """Holds the rule that survives whatever model is eventually plugged in.

    There is no similarity search here yet on purpose — adding one before there is an
    embedder to produce vectors would be code nobody has run. What is here is the check
    that must not be forgotten when somebody does add it.
    """

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder

    @property
    def is_local(self) -> bool:
        return self._embedder.is_local

    def embed_item(self, item: MemoryItem) -> MemoryItem:
        """Embed a memory, refusing to send a local-only one to a remote service.

        The schema already refuses to *record* a LOCAL_ONLY memory as remotely embedded.
        This refuses to *perform* the embedding, which is the step that would actually
        transmit the text. A validator that catches it afterwards catches it too late.
        """
        if item.sensitivity is SensitivityLevel.LOCAL_ONLY and not self._embedder.is_local:
            raise LocalOnlyViolation(
                f"memory {item.id} is LOCAL_ONLY and this embedder is a remote service. "
                "Embedding it would send the text off the machine, which is the one thing "
                "that classification means it may not do."
            )
        self._embedder.embed(item.text)
        return item.model_copy(
            update={
                "embedding_ref": f"vec_{item.id}",
                "embedded_remotely": not self._embedder.is_local,
            }
        )
