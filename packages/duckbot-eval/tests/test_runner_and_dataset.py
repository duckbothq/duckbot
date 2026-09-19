"""The harness end to end, and invariants the shipped dataset must satisfy.

No test here opens a socket: the runner takes a ``ChatClient``, so a scripted one stands
in for a model. That is the same seam that makes a local model and a hosted one one line
apart when the harness is used for real.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from duckbot_gateway import AdapterFailure, ScriptedClient
from duckbot_privacy import detect_all, hkid

from duckbot_eval import (
    IDENTIFYING_ENTITIES,
    Case,
    EvaluationRunner,
    Task,
    compare,
    format_report,
    load_cases,
    score,
)

DATASET = Path(__file__).resolve().parents[1] / "datasets" / "hk_local_model_v1.json"


@pytest.fixture(scope="module")
def cases() -> list[Case]:
    return load_cases(DATASET)


class TestTheShippedDataset:
    def test_it_loads_and_covers_every_task(self, cases: list[Case]) -> None:
        assert {c.task for c in cases} == set(Task)

    def test_ids_are_unique(self, cases: list[Case]) -> None:
        ids = [c.id for c in cases]
        assert len(ids) == len(set(ids))

    def test_every_forbidden_value_is_actually_in_the_content(self, cases: list[Case]) -> None:
        """Otherwise the leak check passes for free and measures nothing."""
        for case in cases:
            for value in case.forbidden:
                assert value in case.content, f"{case.id}: {value!r} is not in the content"

    def test_every_retained_term_is_actually_in_the_content(self, cases: list[Case]) -> None:
        """A model cannot retain what was never there."""
        for case in cases:
            for term in case.must_retain:
                assert term in case.content, f"{case.id}: {term!r} is not in the content"

    def test_retained_terms_are_not_themselves_identifiers(self, cases: list[Case]) -> None:
        """Otherwise two checks contradict: keep this, but do not keep identifiers."""
        for case in cases:
            for term in case.must_retain:
                found = [d for d in detect_all(term) if d.entity_type in IDENTIFYING_ENTITIES]
                assert not found, f"{case.id}: {term!r} is detected as {found}"

    def test_every_identity_number_in_the_dataset_is_internally_valid(
        self, cases: list[Case]
    ) -> None:
        """An invented HKID with a wrong check digit would make the classification cases
        unanswerable by a model that validates, and would quietly measure the wrong thing."""
        for case in cases:
            for value in case.forbidden:
                if "(" in value and any(ch.isdigit() for ch in value):
                    continue
            if "身份證" in case.content or "HKID" in case.content:
                assert hkid.find_all(case.content), case.id

    def test_the_expected_names_appear_in_their_content(self, cases: list[Case]) -> None:
        for case in cases:
            for name in case.expected_names:
                assert name in case.content, f"{case.id}: {name!r} is not in the content"


def perfect_answers(cases: list[Case]) -> list[str]:
    replies: list[str] = []
    for case in cases:
        if case.task is Task.CLASSIFY:
            assert case.expected_label is not None
            replies.append(case.expected_label.name)
        elif case.task is Task.EXTRACT_NAMES:
            replies.append("\n".join(case.expected_names) if case.expected_names else "無")
        else:
            replies.append("已改寫：" + "、".join(case.must_retain) + "嘅安排照舊進行。")
    return replies


class TestRunner:
    def test_a_model_that_answers_perfectly_scores_perfectly(self, cases: list[Case]) -> None:
        runner = EvaluationRunner(ScriptedClient(perfect_answers(cases)), model="fake/perfect")
        result = runner.run(cases)
        assert [r.case_id for r in result.results if not r.passed] == []
        assert result.errors == ()

    def test_a_simplified_answer_is_caught_across_the_board(self, cases: list[Case]) -> None:
        chinese = [c for c in cases if c.expects_chinese and c.task is Task.CLASSIFY]
        runner = EvaluationRunner(
            ScriptedClient(
                [
                    "这段内容係 " + (c.expected_label.name if c.expected_label else "")
                    for c in chinese
                ]
            ),
            model="fake/simplified",
        )
        result = runner.run(chinese)
        assert all(not r.passed for r in result.results)

    def test_a_provider_failure_is_not_scored_as_a_wrong_answer(self, cases: list[Case]) -> None:
        """An unreliable model must not be made to look like an inaccurate one."""

        class Broken:
            def chat(self, prompt: str):
                raise AdapterFailure("503 from provider")

        result = EvaluationRunner(Broken(), model="fake/broken").run(cases[:3])
        assert len(result.errors) == 3
        assert score(result) == []

    def test_token_usage_is_accumulated(self, cases: list[Case]) -> None:
        subset = cases[:3]
        result = EvaluationRunner(
            ScriptedClient(perfect_answers(subset)), model="fake/perfect"
        ).run(subset)
        assert result.total_tokens_in > 0
        assert result.total_tokens_out > 0

    def test_the_prompt_version_is_recorded(self, cases: list[Case]) -> None:
        """So an old run and a new one cannot be silently put in the same table."""
        subset = cases[:1]
        result = EvaluationRunner(
            ScriptedClient(perfect_answers(subset)), model="fake/perfect"
        ).run(subset)
        assert result.prompt_version >= 1


class TestReport:
    def test_it_names_the_model_and_the_tasks(self, cases: list[Case]) -> None:
        result = EvaluationRunner(ScriptedClient(perfect_answers(cases)), model="fake/perfect").run(
            cases
        )
        rendered = format_report(result)
        assert "fake/perfect" in rendered
        for task in Task:
            assert task.value in rendered

    def test_every_figure_carries_its_interval(self, cases: list[Case]) -> None:
        """A number without its precision gets quoted. That is the whole point of this."""
        result = EvaluationRunner(ScriptedClient(perfect_answers(cases)), model="fake/perfect").run(
            cases
        )
        rendered = format_report(result)
        assert rendered.count("95% CI") >= 3
        assert "Read these figures as a direction, not a measurement." in rendered

    def test_it_says_how_many_cases_would_settle_it(self, cases: list[Case]) -> None:
        result = EvaluationRunner(ScriptedClient(perfect_answers(cases)), model="fake/perfect").run(
            cases
        )
        assert "±5 points" in format_report(result)

    def test_two_models_can_be_put_side_by_side(self, cases: list[Case]) -> None:
        good = EvaluationRunner(ScriptedClient(perfect_answers(cases)), model="fake/good").run(
            cases
        )
        bad = EvaluationRunner(ScriptedClient(["PUBLIC"] * len(cases)), model="fake/bad").run(cases)
        table = compare([good, bad])
        assert "fake/good" in table and "fake/bad" in table
        assert "not_under_classified" in table
