"""Duckbot local memory and the context compiler.

Workstream C of the engineering handover, second half. Storage with retention that is
enforced rather than recorded, retrieval that works on Traditional Chinese, and the
compiler that decides what a given request may and can afford to carry.
"""

from .compiler import FRAMING, Budget, CompiledContext, ContextCompiler, Exclusion
from .counting import HeuristicTokenCounter, TokenCounter
from .errors import BudgetTooSmall, LocalOnlyViolation, MemoryError_
from .index import Embedder, EmbeddingIndex, Hit, LexicalIndex
from .retention import (
    MAX_AGE,
    Deletable,
    RetentionSweeper,
    SweepResult,
    expires_at,
    is_expired,
)
from .sqlite_store import SqliteMemoryStore
from .store import InMemoryMemoryStore, MemoryStore
from .tokenise import is_cjk, normalise, tokenise

__all__ = [
    "FRAMING",
    "MAX_AGE",
    "Budget",
    "BudgetTooSmall",
    "CompiledContext",
    "ContextCompiler",
    "Deletable",
    "Embedder",
    "EmbeddingIndex",
    "Exclusion",
    "HeuristicTokenCounter",
    "Hit",
    "InMemoryMemoryStore",
    "LexicalIndex",
    "LocalOnlyViolation",
    "MemoryError_",
    "MemoryStore",
    "RetentionSweeper",
    "SqliteMemoryStore",
    "SweepResult",
    "TokenCounter",
    "expires_at",
    "is_cjk",
    "is_expired",
    "normalise",
    "tokenise",
]
