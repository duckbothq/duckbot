"""Turning a run into something a decision can be made from.

The report is built around one belief: a number without its precision is worse than no
number, because it gets quoted. Every rate is printed with a 95% interval, and the
footer says how many cases would be needed to halve the widest one. A twelve-case run
that reads "83% (95% CI 55%–95%)" cannot be put in a slide as "83%" without somebody
noticing the rest of the line.

Three figures are pulled out of the per-check detail because they map to decisions rather
than to quality:

**Under-classification** is the classification failure that ends in an incident. Overall
accuracy hides it.

**Traditional Chinese** is pass-or-fail for a Hong Kong customer regardless of anything
else.

**Leakage on rewriting** is the one where a fluent, plausible answer is the worst
outcome, because it looks like success.
"""

from __future__ import annotations

from dataclasses import dataclass

from .grading import SCRIPT, UNDER_CLASSIFICATION, CaseResult
from .runner import RunResult
from .stats import Rate, cases_needed, wilson
from .tasks import Task

DECISION_CRITICAL = frozenset({UNDER_CLASSIFICATION, SCRIPT, "no_forbidden_values"})
"""Checks that settle a question by themselves, rather than contributing to a quality score.

Each corresponds to something that cannot be traded off: output a Hong Kong customer
cannot read, content sent to a provider that should not have gone, and an identifying
value surviving the step whose entire purpose was to remove it.
"""


@dataclass(frozen=True)
class TaskScore:
    task: Task
    overall: Rate
    by_check: dict[str, Rate]


def _rate_for(results: list[CaseResult], check_name: str) -> Rate | None:
    relevant = [r for r in results if r.check(check_name) is not None]
    if not relevant:
        return None
    passed = sum(1 for r in relevant if (c := r.check(check_name)) and c.passed)
    return wilson(passed, len(relevant))


def score(run: RunResult) -> list[TaskScore]:
    scores: list[TaskScore] = []
    for task in Task:
        results = [r for r in run.results if r.task is task and not r.error]
        if not results:
            continue
        names = list(dict.fromkeys(c.name for r in results for c in r.checks))
        by_check = {}
        for name in names:
            rate = _rate_for(results, name)
            if rate is not None:
                by_check[name] = rate
        scores.append(
            TaskScore(
                task=task,
                overall=wilson(sum(1 for r in results if r.passed), len(results)),
                by_check=by_check,
            )
        )
    return scores


def format_report(run: RunResult) -> str:
    scores = score(run)
    lines = [
        f"model: {run.model}   (prompt version {run.prompt_version})",
        f"cases: {len(run.results)}   errors: {len(run.errors)}",
        f"tokens: {run.total_tokens_in} in, {run.total_tokens_out} out"
        f"   latency: {run.total_latency_ms} ms total",
        "",
    ]

    if any(name in DECISION_CRITICAL for s in scores for name in s.by_check):
        lines.append(
            "[decision] marks a check that decides something on its own: a Simplified "
            "answer is unusable in Hong Kong whatever else is right, and an "
            "under-classification is the failure that ends in an incident."
        )
        lines.append("")

    for task_score in scores:
        lines.append(f"{task_score.task.value}")
        lines.append(f"  all checks passed   {task_score.overall}")
        for name, rate in task_score.by_check.items():
            marker = "  [decision]" if name in DECISION_CRITICAL else ""
            lines.append(f"  {name:<24}{rate}{marker}".rstrip())
        lines.append("")

    if run.errors:
        lines.append("errors (not scored as wrong answers):")
        lines.extend(f"  {r.case_id}: {r.error}" for r in run.errors)
        lines.append("")

    widest = max(
        (rate for s in scores for rate in [s.overall, *s.by_check.values()]),
        key=lambda r: r.width,
        default=None,
    )
    if widest is not None and widest.total:
        needed = cases_needed(widest.value or 0.5, 0.05)
        lines.append(
            f"The widest interval here spans {widest.width:.0%} on {widest.total} cases. "
            f"Reaching ±5 points at that rate needs about {needed} cases per task. "
            "Read these figures as a direction, not a measurement."
        )

    return "\n".join(lines)


def compare(runs: list[RunResult]) -> str:
    """Two or more models side by side, on the checks that decide things."""
    if not runs:
        return "no runs"
    headline = [UNDER_CLASSIFICATION, SCRIPT, "names_found", "no_forbidden_values"]
    lines = [
        f"{'check':<24}" + "".join(f"{r.model:>26}" for r in runs),
        "-" * (24 + 26 * len(runs)),
    ]
    per_run = [
        {name: rate for s in score(run) for name, rate in s.by_check.items()} for run in runs
    ]
    for name in headline:
        cells = []
        for rates in per_run:
            rate = rates.get(name)
            cells.append(f"{str(rate) if rate else 'n/a':>26}")
        lines.append(f"{name:<24}" + "".join(cells))
    return "\n".join(lines)
