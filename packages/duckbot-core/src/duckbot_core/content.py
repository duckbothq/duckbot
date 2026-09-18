"""The trust boundary between what the user asked for and what Duckbot read.

Prompt injection is not a prompt-wording problem. Content retrieved from a document, an
email or a web page is data, and the type system should make it awkward to treat as
anything else. A browser operator that follows instructions embedded in a page it visits
is a critical vulnerability, not a quirk.

Two types, deliberately not interchangeable:

* :class:`Instruction` — what a human asked Duckbot to do.
* :class:`UntrustedContent` — everything Duckbot read while doing it.

There is no implicit conversion. Promoting retrieved content to an instruction requires
:func:`promote_to_instruction`, which demands a human approval id and says so in the
audit trail. That is deliberately more effort than doing it correctly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from duckbot_schemas import new_id

from .errors import UntrustedContentMisuse


@dataclass(frozen=True)
class Instruction:
    """Something a human asked for. Safe to act on."""

    text: str
    requester: str
    id: str = field(default_factory=lambda: new_id("instr"))

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("an instruction cannot be empty")
        if not self.requester.strip():
            raise ValueError("an instruction must have a requester")


@dataclass(frozen=True)
class UntrustedContent:
    """Something Duckbot read. Data, never instruction.

    ``__str__`` is deliberately not the text. A stray f-string is the most common way
    retrieved content ends up concatenated into a prompt, and this makes that mistake
    visible in review rather than silent at runtime.
    """

    text: str
    source: str
    id: str = field(default_factory=lambda: new_id("cont"))

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("retrieved content must record where it came from")

    def __str__(self) -> str:
        return f"<UntrustedContent from {self.source}, {len(self.text)} chars>"

    __repr__ = __str__

    def as_data(self) -> str:
        """The text, for classification, extraction and display.

        Named so that a reviewer can see at a glance that the caller is treating this as
        data. If you find yourself reaching for this to build a prompt, stop.
        """
        return self.text


def promote_to_instruction(
    content: UntrustedContent, *, approval_id: str, requester: str
) -> Instruction:
    """Turn retrieved content into an instruction. Requires a human approval.

    This exists because the case is real — a user may genuinely want to act on something
    inside a document — and pretending otherwise would push people to work around the
    boundary instead of through it. The approval id is required so the decision appears
    in the audit trail.
    """
    if not approval_id.strip():
        raise UntrustedContentMisuse(
            "retrieved content can only become an instruction with a human approval; "
            "this is the prompt-injection boundary and it is not optional"
        )
    return Instruction(text=content.text, requester=requester)
