"""What we are actually measuring, and why it is not a benchmark score.

The question this package exists to answer is narrow: **is a small local model good
enough at the jobs Duckbot gives a local model?** Not whether it is a good chatbot. The
difference matters, because a general benchmark would tell us something true and
irrelevant, and we would then make a product decision on it anyway.

The architecture gives a local model exactly three jobs. Each is a task here.

**Classification.** Decide how sensitive a piece of content is. Errors are asymmetric in
a way a plain accuracy figure hides: calling sensitive content harmless sends it to a
hosted provider, and calling harmless content sensitive only costs a little usefulness.
The grader scores those differently and the report keeps them apart.

**Chinese name extraction.** The rule layer in ``duckbot-privacy`` says in its own
docstring that names are the model's job, and measures itself at 90.9% recall on the
corpus. So this task has a baseline that already exists and a decision attached to it: a
local model that cannot beat the rules on the one thing the rules admit they are bad at
is not earning its place.

**Derived rewriting.** Producing a version of content that carries the meaning without
the identifying values — the ``DERIVE`` policy action. This is the task where a
plausible-looking answer can be the worst outcome, because a fluent summary that still
names the client has defeated the entire purpose while appearing to have worked.

Two things every task is scored on regardless, because both are ways a model can fail
that a task-specific grader would miss: whether it answered in Traditional Chinese, and
whether it leaked a value it was given.
"""

from __future__ import annotations

from enum import StrEnum


class Task(StrEnum):
    CLASSIFY = "classify"
    EXTRACT_NAMES = "extract_names"
    DERIVE_REWRITE = "derive_rewrite"


TASK_PURPOSE: dict[Task, str] = {
    Task.CLASSIFY: "decide how sensitive this content is",
    Task.EXTRACT_NAMES: "list the personal names in this content",
    Task.DERIVE_REWRITE: "rewrite this carrying the meaning but no identifying values",
}
"""Passed through to ``ModelCall.purpose`` so an evaluation run is visible in the cost
records as what it was, rather than as unexplained traffic."""


PROMPTS: dict[Task, str] = {
    Task.CLASSIFY: (
        "以下係一段香港公司嘅文件內容。請判斷佢嘅敏感程度，"
        "只回覆其中一個詞：PUBLIC、MINIMIZE、ANONYMIZE、LOCAL_ONLY。"
        "如果內容含有身份證號碼，答 LOCAL_ONLY。\n\n內容：\n{content}"
    ),
    Task.EXTRACT_NAMES: (
        "以下係一段香港公司嘅文件內容。請列出入面所有人名，"
        "每行一個，唔好加任何解釋。如果冇人名，回覆「無」。\n\n內容：\n{content}"
    ),
    Task.DERIVE_REWRITE: (
        "以下係一段香港公司嘅文件內容。請用繁體中文改寫，保留意思同可以行動嘅資訊，"
        "但唔好出現任何人名、身份證號碼、電話、電郵或者公司登記號碼。\n\n內容：\n{content}"
    ),
}
"""The prompts are part of what is being measured.

A model that fails with one prompt and succeeds with another has not changed, but the
measurement has. So these live in version control, they are the same for every model
compared, and changing one invalidates comparisons against results recorded before the
change. The dataset records which prompt version produced a result for that reason.
"""

PROMPT_VERSION = 1
"""Bump when any prompt above changes. Results carry it, so an old run and a new one
cannot be silently put in the same table."""
