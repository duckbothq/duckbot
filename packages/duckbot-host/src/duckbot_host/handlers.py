"""JSON-RPC methods exposed to the thin desktop shell.

Placeholder maps, provider credentials and raw local-file content stay in this process.
Only redacted previews, final locally restored answers and safe record projections cross
the pipe.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from duckbot_core import (
    ApprovalStore,
    AuditLog,
    AuditStore,
    DuckbotError,
    InMemoryApprovalStore,
    InMemoryAuditStore,
    InMemoryTaskStore,
    SqliteStores,
    TaskStore,
    UntrustedContent,
)
from duckbot_engine import (
    ApprovalPending,
    ConnectorDocument,
    LocalFileConnector,
    StoreBundle,
    TaskCancelled,
    TaskEngine,
    TaskPreview,
    TaskRequest,
    TaskResult,
)
from duckbot_gateway import GatewayError
from duckbot_memory import Budget
from duckbot_privacy import PrivacyGateway
from duckbot_schemas import (
    SCHEMA_VERSION,
    AuditAction,
    ModelTier,
    Money,
    PlaceholderMap,
    PolicyAction,
    RiskClass,
    TaskState,
    new_id,
)

from .protocol import INVALID_PARAMS, PROTOCOL_VERSION, Request, Response, error
from .runtime import build_engine
from .secret_store import (
    SecretStorageUnavailable,
    SecretStore,
    UnavailableSecretStore,
    default_secret_store,
)
from .settings import (
    DesktopSettings,
    InMemorySettingsRepository,
    SettingsStore,
    default_data_directory,
    default_settings_repository,
    updated_settings,
)

HOST_VERSION = "0.2.0"
USER_ERROR = -32000
Handler = Callable[[dict[str, Any]], Any]


@dataclass
class _MemoryStores:
    tasks: TaskStore = field(default_factory=InMemoryTaskStore)
    approvals: ApprovalStore = field(default_factory=InMemoryApprovalStore)
    audit: AuditStore = field(default_factory=InMemoryAuditStore)


class Session:
    """Process-lifetime state; secrets and placeholder maps never leave it."""

    def __init__(
        self,
        *,
        gateway: PrivacyGateway | None = None,
        settings: SettingsStore | None = None,
        secrets: SecretStore | None = None,
        stores: StoreBundle | None = None,
    ) -> None:
        self.gateway = gateway or PrivacyGateway()
        self.settings = settings or InMemorySettingsRepository()
        self.secrets = secrets or UnavailableSecretStore()
        self.stores = stores or _MemoryStores()
        self._maps: dict[str, PlaceholderMap] = {}
        self._configured_engine: tuple[DesktopSettings, TaskEngine] | None = None
        self._task_engines: dict[str, TaskEngine] = {}

    @classmethod
    def production(cls) -> Session:
        directory = default_data_directory()
        directory.mkdir(parents=True, exist_ok=True)
        return cls(
            settings=default_settings_repository(directory),
            secrets=default_secret_store(directory),
            stores=SqliteStores(directory / "duckbot.sqlite3"),
        )

    def keep(self, mapping: PlaceholderMap) -> str:
        handle = new_id("red")
        self._maps[handle] = mapping
        return handle

    def get(self, handle: str) -> PlaceholderMap | None:
        return self._maps.get(handle)

    def forget(self, handle: str) -> bool:
        return self._maps.pop(handle, None) is not None

    @property
    def open_redactions(self) -> int:
        return len(self._maps)

    @property
    def audit(self) -> AuditLog:
        return AuditLog(self.stores.audit)

    def engine(self) -> TaskEngine:
        current = self.settings.load()
        if self._configured_engine is None or self._configured_engine[0] != current:
            self._configured_engine = (
                current,
                build_engine(current, stores=self.stores, secrets=self.secrets),
            )
        return self._configured_engine[1]

    def remember_engine(self, task_id: str, engine: TaskEngine) -> None:
        self._task_engines[task_id] = engine

    def engine_for(self, task_id: str) -> TaskEngine:
        engine = self._task_engines.get(task_id)
        if engine is None:
            raise ValueError("preview is no longer available; prepare the task again")
        return engine

    def forget_finished(self, task_id: str) -> None:
        engine = self._task_engines.get(task_id)
        if engine is not None and engine.get_task(task_id).state not in {
            TaskState.PLANNING,
            TaskState.AWAITING_APPROVAL,
            TaskState.RUNNING,
        }:
            self._task_engines.pop(task_id, None)

    def settings_changed(self) -> None:
        for task_id, engine in list(self._task_engines.items()):
            if engine.get_task(task_id).state in {TaskState.PLANNING, TaskState.AWAITING_APPROVAL}:
                engine.cancel(task_id)
            self.forget_finished(task_id)
        self._configured_engine = None


def _text(params: dict[str, Any], name: str = "text") -> str:
    value = params.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _optional_text(params: dict[str, Any], name: str) -> str | None:
    value = params.get(name)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _task(task: Any) -> dict[str, Any]:
    return {
        "id": task.id,
        "goal": task.goal,
        "state": task.state.value,
        "total_cost": task.total_cost.model_dump(mode="json"),
        "model_calls": task.model_calls,
        "human_interventions": task.human_interventions,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "failure_reason": task.failure_reason,
    }


def _preview(preview: TaskPreview) -> dict[str, Any]:
    return {
        "task_id": preview.task_id,
        "state": "blocked" if preview.policy_action is PolicyAction.BLOCK else preview.state.value,
        "destination": preview.destination,
        "destination_is_local": preview.destination_is_local,
        "outbound_text": preview.outbound_text,
        "sensitivity": preview.classification.effective_sensitivity.name,
        "redactions": [
            {
                "type": entity.entity_type,
                "start": entity.start,
                "end": entity.end,
                "token": entity.placeholder_token,
            }
            for entity in preview.classification.entities
        ],
        "policy_action": preview.policy_action.value if preview.policy_action else "local_only",
        "policy_justification": preview.policy_justification,
        "placeholder_tokens": list(preview.placeholder_tokens),
        "context_sources": list(preview.context_sources),
        "context_exclusions": [
            {"item_id": exclusion.item_id, "reason": exclusion.reason}
            for exclusion in preview.context_exclusions
        ],
        "estimated_context_tokens": preview.estimated_context_tokens,
        "estimated_cost": preview.estimated_cost.model_dump(mode="json"),
        "approval_required": preview.approval_required,
        "risk_class": preview.risk_class.value,
    }


def _approval(approval: Any) -> dict[str, Any]:
    return {
        "id": approval.id,
        "task_id": approval.task_id,
        "risk_class": approval.risk_class.value,
        "action_description": approval.action_description,
        "outcome": approval.outcome.value,
        "requested_at": approval.requested_at.isoformat(),
        "decided_by": approval.decided_by,
        "decision_reason": approval.decision_reason,
    }


def _outcome(outcome: TaskResult | ApprovalPending | TaskCancelled) -> dict[str, Any]:
    if isinstance(outcome, TaskResult):
        return {
            "kind": "completed",
            "task": _task(outcome.task),
            "preview": _preview(outcome.preview),
            "text": outcome.text,
            "cost": outcome.cost.model_dump(mode="json"),
            "cost_is_complete": outcome.cost_is_complete,
            "provider": outcome.model_call.provider,
            "model": outcome.model_call.model,
            "fallback_chain": outcome.model_call.fallback_chain,
        }
    if isinstance(outcome, ApprovalPending):
        return {
            "kind": "approval_required",
            "task": _task(outcome.task),
            "preview": _preview(outcome.preview),
            "approval": _approval(outcome.approval),
        }
    return {
        "kind": "cancelled",
        "task": _task(outcome.task),
        "preview": _preview(outcome.preview),
        "approval": _approval(outcome.approval),
    }


def _monthly_spend(session: Session, currency: str) -> Decimal:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    total = Decimal(0)
    for task in session.stores.tasks.list_all():
        if (
            task.created_at.year == now.year
            and task.created_at.month == now.month
            and task.total_cost.currency == currency
        ):
            total += Decimal(task.total_cost.amount)
    return total


def _record_file_read(
    session: Session,
    document: ConnectorDocument,
    *,
    actor: str,
    task_id: str | None,
) -> None:
    session.audit.record(
        actor=actor,
        action=AuditAction.EXTERNAL_ACTION,
        target=document.content.source,
        task_id=task_id,
        result="read",
        detail=f"read {document.size_bytes} bytes from the selected local folder",
    )


def build_handlers(session: Session) -> dict[str, Handler]:
    def health(_: dict[str, Any]) -> dict[str, Any]:
        current = session.settings.load()
        return {
            "ok": True,
            "protocol_version": PROTOCOL_VERSION,
            "host_version": HOST_VERSION,
            "schema_version": SCHEMA_VERSION,
            "open_redactions": session.open_redactions,
            "provider": current.provider,
        }

    def classify(params: dict[str, Any]) -> dict[str, Any]:
        classification, _ = session.gateway.classify(
            _text(params), content_id=str(params.get("content_id") or new_id("doc"))
        )
        return {
            "content_id": classification.content_id,
            "sensitivity": classification.sensitivity.name,
            "entities": [
                {
                    "type": entity.entity_type,
                    "start": entity.start,
                    "end": entity.end,
                    "confidence": entity.confidence,
                }
                for entity in classification.entities
            ],
        }

    def redact(params: dict[str, Any]) -> dict[str, Any]:
        result = session.gateway.redact(
            _text(params), content_id=str(params.get("content_id") or new_id("doc"))
        )
        return {
            "redaction_id": session.keep(result.placeholder_map),
            "redacted_text": result.redacted_text,
            "sensitivity": result.classification.sensitivity.name,
            "tokens": result.tokens,
        }

    def restore(params: dict[str, Any]) -> dict[str, Any]:
        handle = params.get("redaction_id")
        if not isinstance(handle, str):
            raise ValueError("redaction_id must be a string")
        mapping = session.get(handle)
        if mapping is None:
            raise ValueError("unknown redaction_id; the host may have restarted")
        return {"text": mapping.restore(_text(params))}

    def forget(params: dict[str, Any]) -> dict[str, Any]:
        handle = params.get("redaction_id")
        if not isinstance(handle, str):
            raise ValueError("redaction_id must be a string")
        return {"forgotten": session.forget(handle)}

    def task_prepare(params: dict[str, Any]) -> dict[str, Any]:
        current = session.settings.load()
        task_cost_limit = Decimal(current.per_task_budget_usd)
        if current.provider in {"openai", "anthropic"}:
            spent = _monthly_spend(session, current.price_currency.upper())
            remaining = Decimal(current.monthly_budget_usd) - spent
            if remaining <= 0:
                raise ValueError("monthly model budget has been reached")
            task_cost_limit = min(task_cost_limit, remaining)

        context: tuple[UntrustedContent, ...] = ()
        document: ConnectorDocument | None = None
        requester = str(params.get("requester") or "desktop-user")
        context_path = _optional_text(params, "context_path")
        if context_path is not None:
            if not current.connector_folder:
                raise ValueError("select a local connector folder in settings first")
            document = LocalFileConnector(Path(current.connector_folder)).read(
                context_path,
                actor=requester,
                encoding=str(params.get("context_encoding") or current.connector_encoding),
            )
            context = (document.content,)

        try:
            try:
                risk = RiskClass(str(params.get("risk_class") or RiskClass.READ.value))
            except ValueError as exc:
                raise ValueError("risk_class is not supported") from exc
            engine = session.engine()
            request = TaskRequest(
                instruction=_text(params, "instruction"),
                requester=requester,
                purpose=str(params.get("purpose") or "general"),
                risk_class=risk,
                action_description=_optional_text(params, "action_description"),
                budget=Budget(
                    max_tokens=int(current.max_context_tokens),
                    reserve_for_reply=int(current.reserve_reply_tokens),
                ),
                prefer=(
                    ModelTier.FRONTIER if current.provider in {"openai", "anthropic"} else None
                ),
                context=context,
                max_cost=Money(
                    amount=str(task_cost_limit),
                    currency=current.price_currency.upper(),
                ),
            )
            preview = engine.prepare(request)
        except Exception:
            if document is not None:
                _record_file_read(session, document, actor=requester, task_id=None)
            raise
        session.remember_engine(preview.task_id, engine)
        if document is not None:
            _record_file_read(
                session,
                document,
                actor=request.requester,
                task_id=preview.task_id,
            )
        return _preview(preview)

    def task_execute(params: dict[str, Any]) -> dict[str, Any]:
        task_id = _text(params, "task_id")
        try:
            return _outcome(session.engine_for(task_id).execute(task_id))
        finally:
            session.forget_finished(task_id)

    def task_cancel(params: dict[str, Any]) -> dict[str, Any]:
        task_id = _text(params, "task_id")
        try:
            return {"task": _task(session.engine_for(task_id).cancel(task_id))}
        finally:
            session.forget_finished(task_id)

    def approval_decide(params: dict[str, Any]) -> dict[str, Any]:
        approved = params.get("approved")
        if not isinstance(approved, bool):
            raise ValueError("approved must be true or false")
        approval_id = _text(params, "approval_id")
        task_id = _text(params, "task_id")
        engine = session.engine_for(task_id)
        if approval_id not in {item.id for item in engine.pending_approvals(task_id)}:
            raise ValueError("approval does not belong to this prepared task")
        try:
            return _outcome(
                engine.decide(
                    approval_id,
                    approved=approved,
                    decided_by=str(params.get("decided_by") or "desktop-user"),
                    reason=_optional_text(params, "reason"),
                )
            )
        finally:
            session.forget_finished(task_id)

    def tasks_list(_: dict[str, Any]) -> dict[str, Any]:
        tasks = sorted(
            session.stores.tasks.list_all(), key=lambda item: item.created_at, reverse=True
        )
        return {"tasks": [_task(item) for item in tasks]}

    def audit_list(params: dict[str, Any]) -> dict[str, Any]:
        task_id = _optional_text(params, "task_id")
        events = session.stores.audit.all_events()
        if task_id is not None:
            events = [event for event in events if event.task_id == task_id]
        return {
            "events": [event.model_dump(mode="json") for event in events],
            "verified": _audit_verified(session.audit),
        }

    def audit_verify(_: dict[str, Any]) -> dict[str, Any]:
        session.audit.verify()
        return {"verified": True, "count": session.stores.audit.count()}

    def settings_get(_: dict[str, Any]) -> dict[str, Any]:
        current = session.settings.load()
        result: dict[str, Any] = current.to_wire()
        result.update(
            {
                "secret_storage_available": session.secrets.available,
                "secret_storage_backend": session.secrets.backend,
                "has_api_key": session.secrets.has(current.provider),
            }
        )
        return result

    def settings_update(params: dict[str, Any]) -> dict[str, Any]:
        changes = params.get("settings", {})
        if not isinstance(changes, dict):
            raise ValueError("settings must be an object")
        updated = updated_settings(session.settings.load(), changes)
        api_key = params.get("api_key")
        delete_key = params.get("delete_api_key", False)
        if not isinstance(delete_key, bool):
            raise ValueError("delete_api_key must be true or false")
        if api_key is not None and delete_key:
            raise ValueError("cannot save and delete an API key together")
        if api_key is not None:
            if not isinstance(api_key, str) or not api_key:
                raise ValueError("API key must be a non-empty string")
            if updated.provider not in {"openai", "anthropic"}:
                raise ValueError("API keys are only used by hosted providers")
            if not session.secrets.available:
                raise SecretStorageUnavailable("secure API-key storage is unavailable")
        # Invalidate old in-memory clients before changing or removing their credential.
        session.settings_changed()
        change_secret = api_key is not None or delete_key
        previous_key = session.secrets.get(updated.provider) if change_secret else None
        if api_key is not None:
            session.secrets.set(updated.provider, api_key)
        elif delete_key:
            session.secrets.delete(updated.provider)
        try:
            session.settings.update(changes)
        except Exception:
            if change_secret:
                if previous_key is None:
                    session.secrets.delete(updated.provider)
                else:
                    session.secrets.set(updated.provider, previous_key)
            raise
        result: dict[str, Any] = updated.to_wire()
        result["has_api_key"] = session.secrets.has(updated.provider)
        return result

    def connector_list(_: dict[str, Any]) -> dict[str, Any]:
        current = session.settings.load()
        if not current.connector_folder:
            return {"files": []}
        return {"files": list(LocalFileConnector(Path(current.connector_folder)).list_files())}

    return {
        "health": health,
        "classify": classify,
        "redact": redact,
        "restore": restore,
        "forget": forget,
        "task_prepare": task_prepare,
        "task_execute": task_execute,
        "task_cancel": task_cancel,
        "approval_decide": approval_decide,
        "tasks_list": tasks_list,
        "audit_list": audit_list,
        "audit_verify": audit_verify,
        "settings_get": settings_get,
        "settings_update": settings_update,
        "connector_list": connector_list,
    }


def _audit_verified(audit: AuditLog) -> bool:
    try:
        audit.verify()
    except Exception:
        return False
    return True


def dispatch(handlers: dict[str, Handler], request: Request) -> Response:
    handler = handlers.get(request.method)
    if handler is None:
        from .protocol import METHOD_NOT_FOUND

        return error(METHOD_NOT_FOUND, f"no such method: {request.method}", request.id)
    try:
        return Response(id=request.id, result=handler(request.params))
    except ValueError as exc:
        return error(INVALID_PARAMS, str(exc), request.id)
    except (DuckbotError, GatewayError, SecretStorageUnavailable) as exc:
        return error(
            USER_ERROR,
            f"工作無法完成（{type(exc).__name__}）。請檢查設定後再試。 / "
            "Task could not complete; check settings and try again.",
            request.id,
        )
