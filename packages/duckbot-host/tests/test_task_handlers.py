from __future__ import annotations

import json
from pathlib import Path

from duckbot_schemas import Money, Task

from duckbot_host import Request, Session, serve_request
from duckbot_host.settings import DesktopSettings, InMemorySettingsRepository

PHONE = "9876 5432"
HKID = "A123456(3)"


class StaticSecretStore:
    available = True
    backend = "test-only"

    def set(self, name: str, secret: str) -> None:
        del name, secret

    def get(self, name: str) -> str | None:
        del name
        return "not-a-real-api-key"

    def has(self, name: str) -> bool:
        del name
        return True

    def delete(self, name: str) -> bool:
        del name
        return True


def call(session: Session, method: str, params: dict | None = None) -> dict:
    response = serve_request(Request(method=method, params=params or {}, id=1), session=session)
    return json.loads(response.to_json())


def test_offline_task_preview_execute_records_cost_and_safe_history() -> None:
    session = Session()
    prepared = call(
        session,
        "task_prepare",
        {"instruction": f"請致電客戶 {PHONE}。", "requester": "office-manager"},
    )["result"]

    assert prepared["destination_is_local"]
    assert prepared["outbound_text"] is None
    assert prepared["sensitivity"] == "ANONYMIZE"
    assert any(item["type"] == "PHONE" for item in prepared["redactions"])

    completed = call(session, "task_execute", {"task_id": prepared["task_id"]})["result"]
    assert completed["kind"] == "completed"
    assert PHONE in completed["text"]
    assert completed["cost"]["amount"] == "0.00000000"

    tasks = call(session, "tasks_list")["result"]
    assert PHONE not in json.dumps(tasks, ensure_ascii=False)
    audit = call(session, "audit_list", {"task_id": prepared["task_id"]})["result"]
    assert audit["verified"]
    assert PHONE not in json.dumps(audit, ensure_ascii=False)


def test_financial_task_waits_for_explicit_desktop_decision() -> None:
    session = Session()
    prepared = call(
        session,
        "task_prepare",
        {
            "instruction": "準備付款。",
            "risk_class": "financial",
            "action_description": "支付供應商港幣 500 元 / Pay supplier HKD 500",
        },
    )["result"]
    paused = call(session, "task_execute", {"task_id": prepared["task_id"]})["result"]

    assert paused["kind"] == "approval_required"
    decided = call(
        session,
        "approval_decide",
        {
            "task_id": prepared["task_id"],
            "approval_id": paused["approval"]["id"],
            "approved": True,
            "decided_by": "owner",
        },
    )["result"]
    assert decided["kind"] == "completed"
    assert decided["task"]["human_interventions"] == 1


def test_scoped_file_context_is_read_locally_and_identified_in_audit(tmp_path: Path) -> None:
    selected = tmp_path / "客戶文件"
    selected.mkdir()
    (selected / "委託.txt").write_text(f"客戶身份證 {HKID}。", encoding="utf-8", newline="\n")
    repository = InMemorySettingsRepository(DesktopSettings(connector_folder=str(selected)))
    session = Session(settings=repository)

    files = call(session, "connector_list")["result"]["files"]
    assert files == ["委託.txt"]
    prepared = call(
        session,
        "task_prepare",
        {"instruction": "摘要文件。", "context_path": "委託.txt"},
    )["result"]

    assert prepared["context_sources"] == ["file:委託.txt"]
    assert prepared["sensitivity"] == "LOCAL_ONLY"
    raw_audit = json.dumps(
        call(session, "audit_list", {"task_id": prepared["task_id"]})["result"],
        ensure_ascii=False,
    )
    assert "file:委託.txt" in raw_audit
    assert HKID not in raw_audit


def test_connector_traversal_error_never_quotes_outside_file(tmp_path: Path) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()
    secret = "outside-sensitive-value"
    (tmp_path / "outside.txt").write_text(secret, encoding="utf-8")
    session = Session(
        settings=InMemorySettingsRepository(DesktopSettings(connector_folder=str(selected)))
    )

    response = call(
        session,
        "task_prepare",
        {"instruction": "摘要文件。", "context_path": "../outside.txt"},
    )
    assert response["error"]["code"] == -32602
    assert secret not in json.dumps(response, ensure_ascii=False)


def test_successful_file_read_is_audited_when_task_preparation_fails(tmp_path: Path) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()
    (selected / "large.txt").write_text("客" * 5_000, encoding="utf-8", newline="\n")
    session = Session(
        settings=InMemorySettingsRepository(
            DesktopSettings(
                connector_folder=str(selected),
                max_context_tokens="128",
                reserve_reply_tokens="32",
            )
        )
    )

    response = call(
        session,
        "task_prepare",
        {"instruction": "摘要文件。", "context_path": "large.txt"},
    )

    assert response["error"]["code"] == -32602
    audit = call(session, "audit_list")["result"]
    assert audit["verified"]
    assert any(event["target"] == "file:large.txt" for event in audit["events"])


def test_monthly_remaining_budget_caps_the_next_task_estimate() -> None:
    settings = DesktopSettings(
        provider="openai",
        provider_model="test-model",
        input_per_mtok="1",
        output_per_mtok="400",
        price_source="synthetic test price",
        price_checked_on="2026-09-19",
        per_task_budget_usd="1.00",
        monthly_budget_usd="25.00",
    )
    session = Session(
        settings=InMemorySettingsRepository(settings),
        secrets=StaticSecretStore(),
    )
    session.stores.tasks.put(
        Task(
            goal="previous safe task",
            requester="office-manager",
            total_cost=Money(amount="24.95", currency="USD"),
        )
    )

    response = call(
        session,
        "task_prepare",
        {"instruction": "整理公開資料。", "requester": "office-manager"},
    )

    assert response["error"]["code"] == -32602
    assert "per-task budget" in response["error"]["message"]
