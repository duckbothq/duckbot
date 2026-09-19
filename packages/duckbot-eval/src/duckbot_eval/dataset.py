"""Evaluation cases.

Same discipline as the privacy corpus, for the same reasons. **Every value is invented.**
No real person, company, client or address appears in any case, and none may. A model
evaluation is a place where real documents feel especially tempting to use, because the
whole point is realism — and it is a place where those documents would end up being sent
to a hosted provider by the harness itself.

A case says what good looks like in a way a grader can check. For the rewriting task that
means two lists rather than one: values that must **not** survive, and meaning that must.
A rewrite that deletes everything leaks nothing and is worthless, and an eval that only
checked for leaks would score it perfect.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from duckbot_schemas import SensitivityLevel

from .tasks import Task


@dataclass(frozen=True)
class Case:
    id: str
    task: Task
    content: str
    note: str = ""

    expected_label: SensitivityLevel | None = None
    """CLASSIFY only."""

    expected_names: tuple[str, ...] = ()
    """EXTRACT_NAMES only. Empty means the correct answer is "no names"."""

    forbidden: tuple[str, ...] = field(default=())
    """DERIVE_REWRITE: values that must not appear in the output."""

    must_retain: tuple[str, ...] = field(default=())
    """DERIVE_REWRITE: meaning that must survive, so that deleting everything fails."""

    expects_chinese: bool = True
    """Whether the answer should be in Traditional Chinese. See :mod:`duckbot_eval.chinese`."""

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError(f"case {self.id} has no content")
        if self.task is Task.CLASSIFY and self.expected_label is None:
            raise ValueError(f"case {self.id} is a classification case with no expected label")
        if self.task is Task.DERIVE_REWRITE and not self.must_retain:
            raise ValueError(
                f"case {self.id} is a rewrite case with nothing it must retain. A rewrite "
                "that deletes everything leaks nothing and is useless; without a retention "
                "requirement the grader would score it perfect."
            )


def load_cases(path: Path | str) -> list[Case]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    cases: list[Case] = []
    for item in raw:
        label = item.get("expected_label")
        cases.append(
            Case(
                id=item["id"],
                task=Task(item["task"]),
                content=item["content"],
                note=item.get("note", ""),
                expected_label=SensitivityLevel[label] if label else None,
                expected_names=tuple(item.get("expected_names", ())),
                forbidden=tuple(item.get("forbidden", ())),
                must_retain=tuple(item.get("must_retain", ())),
                expects_chinese=item.get("expects_chinese", True),
            )
        )
        if len({c.id for c in cases}) != len(cases):
            raise ValueError(f"duplicate case id: {item['id']}")
    return cases
