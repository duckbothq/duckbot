"""Reading what a model actually said.

Small models do not follow output instructions reliably. A grader that demanded exact
format would mostly measure instruction-following, which is worth knowing but is not the
question — we are asking whether the model *can do the job*, and the application can
always parse leniently.

So parsing here is forgiving: it looks for the answer inside whatever wrapping the model
put around it. That leniency is a deliberate choice and it flatters the model, which is
why it is written down here rather than hidden inside a regular expression.
"""

from __future__ import annotations

import re

from duckbot_schemas import SensitivityLevel

_LEVELS = [level.name for level in SensitivityLevel]
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)、]|\(\d+\))\s*")
_NO_NAMES = ("無", "无", "沒有", "没有", "none", "n/a")


def parse_label(output: str) -> SensitivityLevel | None:
    """The first sensitivity level named anywhere in the output.

    'I think this is LOCAL_ONLY because…' counts. A model that got the answer right and
    the format wrong has still got the answer right.
    """
    upper = output.upper()
    hits = [(upper.find(name), name) for name in _LEVELS if name in upper]
    if not hits:
        return None
    return SensitivityLevel[min(hits)[1]]


def parse_names(output: str) -> list[str]:
    """One name per line, with bullets, numbering and stray punctuation removed.

    An explicit "no names" answer parses to an empty list rather than to a list
    containing the word "無".
    """
    if output.strip().casefold() in _NO_NAMES:
        return []
    names: list[str] = []
    for line in output.splitlines():
        cleaned = _BULLET.sub("", line).strip().strip("。，、,.;:：；")
        if not cleaned or cleaned.casefold() in _NO_NAMES:
            continue
        if len(cleaned) > 20:
            # A sentence, not a name. Models sometimes explain instead of listing, and
            # counting the explanation as a name would punish twice for one failure.
            continue
        names.append(cleaned)
    return list(dict.fromkeys(names))
