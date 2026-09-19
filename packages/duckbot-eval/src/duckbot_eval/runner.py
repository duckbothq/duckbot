"""Running an evaluation against a model.

The runner takes a ``ChatClient`` from ``duckbot-gateway``, which is what makes a local
model and a hosted one one line apart — and what lets the whole suite run offline in CI
against a scripted client, so the harness itself is tested without anybody's key.

It deliberately does **not** go through ``ModelGateway``. The gateway's job is to route
by sensitivity and refuse what may not leave; an evaluation needs to send the same case to
whichever model it is measuring, including sending sensitive-looking content to a hosted
model to find out how that model classifies it. Those are opposite requirements, and
bending the gateway to allow it would weaken the thing the gateway exists for.

Which is why the dataset contains only invented values, and why that rule is not
negotiable: this is the one component in the system that sends evaluation content
wherever it is told.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter

from duckbot_gateway import AdapterFailure, ChatClient

from .dataset import Case
from .grading import CaseResult, grade
from .tasks import PROMPT_VERSION, PROMPTS


@dataclass(frozen=True)
class RunResult:
    model: str
    prompt_version: int
    results: tuple[CaseResult, ...] = ()
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_latency_ms: int = 0
    notes: tuple[str, ...] = field(default=())

    @property
    def errors(self) -> tuple[CaseResult, ...]:
        return tuple(r for r in self.results if r.error)


class EvaluationRunner:
    def __init__(self, client: ChatClient, *, model: str) -> None:
        self._client = client
        self._model = model

    def run(self, cases: list[Case]) -> RunResult:
        results: list[CaseResult] = []
        tokens_in = tokens_out = latency = 0

        for case in cases:
            prompt = PROMPTS[case.task].format(content=case.content)
            started = perf_counter()
            try:
                completion = self._client.chat(prompt)
            except AdapterFailure as exc:
                # A provider failure is not a wrong answer, and scoring it as one would
                # make an unreliable model look like an inaccurate one. It is counted
                # separately and the report says so.
                results.append(
                    CaseResult(
                        case_id=case.id,
                        task=case.task,
                        output="",
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
                latency += int((perf_counter() - started) * 1000)
                continue

            tokens_in += completion.tokens_in
            tokens_out += completion.tokens_out
            latency += completion.latency_ms or int((perf_counter() - started) * 1000)
            results.append(grade(case, completion.text))

        return RunResult(
            model=self._model,
            prompt_version=PROMPT_VERSION,
            results=tuple(results),
            total_tokens_in=tokens_in,
            total_tokens_out=tokens_out,
            total_latency_ms=latency,
        )
