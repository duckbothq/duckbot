"""The placeholder map: the single most sensitive artefact in the system.

This is deliberately **not** a pydantic model and has no ``model_dump``. It cannot be
serialised into an audit record, a task record, or an outbound payload by accident,
because there is nothing to serialise it with. That is the point: the mapping between
real values and placeholders never leaves the machine, and the type system should make
the mistake hard rather than the documentation asking people not to make it.

A test asserts that this class is not a ``BaseModel`` and that no schema in this package
has a field typed to hold it. If someone later makes it serialisable, that test fails,
which is the intended alarm.
"""

from __future__ import annotations

from typing import Iterator

from .common import new_id


class PlaceholderMap:
    """Local-only, in-memory mapping of placeholder token to real value."""

    __slots__ = ("_forward", "_reverse")

    def __init__(self) -> None:
        self._forward: dict[str, str] = {}  # token -> real value
        self._reverse: dict[str, str] = {}  # real value -> token

    def token_for(self, real_value: str, entity_type: str) -> str:
        """Return a stable token for a value, creating one on first sight.

        Stability matters: the same customer name appearing three times in a document
        must become the same token, or the model loses the thread of who is who.
        """
        existing = self._reverse.get(real_value)
        if existing is not None:
            return existing
        token = f"[{entity_type.upper()}_{new_id('x').split('_')[1][:6]}]"
        self._forward[token] = real_value
        self._reverse[real_value] = token
        return token

    def restore(self, text: str) -> str:
        """Put the real values back. Runs locally, on the machine, always."""
        for token, real in self._forward.items():
            text = text.replace(token, real)
        return text

    def tokens(self) -> Iterator[str]:
        return iter(self._forward)

    def __len__(self) -> int:
        return len(self._forward)

    def __repr__(self) -> str:  # pragma: no cover - defensive
        return f"<PlaceholderMap {len(self._forward)} entries, values withheld>"

    __str__ = __repr__
