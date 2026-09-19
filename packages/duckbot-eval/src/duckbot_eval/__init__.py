"""Duckbot evaluation harness.

Answers one question: is a small local model good enough at the jobs Duckbot gives a
local model? Not whether it is a good chatbot — that would be true and irrelevant.
"""

from .chinese import SIMPLIFIED_ONLY, looks_simplified, simplified_characters
from .dataset import Case, load_cases
from .grading import IDENTIFYING_ENTITIES, CaseResult, Check, grade
from .parsing import parse_label, parse_names
from .report import TaskScore, compare, format_report, score
from .runner import EvaluationRunner, RunResult
from .stats import Rate, cases_needed, wilson
from .tasks import PROMPT_VERSION, PROMPTS, TASK_PURPOSE, Task

__all__ = [
    "IDENTIFYING_ENTITIES",
    "PROMPTS",
    "PROMPT_VERSION",
    "SIMPLIFIED_ONLY",
    "TASK_PURPOSE",
    "Case",
    "CaseResult",
    "Check",
    "EvaluationRunner",
    "Rate",
    "RunResult",
    "Task",
    "TaskScore",
    "cases_needed",
    "compare",
    "format_report",
    "grade",
    "load_cases",
    "looks_simplified",
    "parse_label",
    "parse_names",
    "score",
    "simplified_characters",
    "wilson",
]
