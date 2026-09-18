"""The model gateway: one way in, whichever model answers.

What this is for, in the words of the handover: *the same task runs against different
providers with no application code change, and cost per task is a number you can show
someone.* A caller says what the content is and what the call is for. Everything else —
which model, whether a permit is needed, what it cost, what to try when it fails — is
decided here.

Three things are deliberate and worth reading before changing them.

**The gateway does not detect anything.** It takes content that has already been
classified and redacted. Keeping the privacy package out of this one's dependencies
means the model layer cannot quietly become the place where privacy decisions are made,
and it means either package can be replaced without the other.

**Cost is checked before the call, not after.** A model with no configured price raises
before any money is spent. Discovering it afterwards would mean either throwing away a
completed answer or writing a zero into the cost record, and the second is how a bill
arrives as a surprise. There is no opt-out; an explicit zero price is how you say a call
is free.

**A policy refusal is not a provider failure.** If policy says the content may not go to
a provider, the gateway moves on to a local model — it does not try a different
provider, because "too sensitive for that one" is never an argument for sending it
somewhere else. If policy blocks the content outright, nothing is tried at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import TypedDict

from duckbot_core import AuditLog, OutboundPermit, PolicyEngine
from duckbot_schemas import (
    AuditAction,
    ContentClassification,
    ModelCall,
    ModelTier,
    Money,
    PlaceholderMap,
    PolicyAction,
    PolicyDecision,
    SensitivityLevel,
)

from .adapters.base import Completion
from .descriptors import ModelDescriptor
from .errors import AdapterFailure, GatewayError, UnknownPrice
from .pricing import PriceTable, add_money
from .routing import ModelRegistry, ModelRouter, Requirement


@dataclass(frozen=True)
class PreparedContent:
    """Content that has already been through classification and redaction.

    ``local_text`` is the real thing and is only ever given to a model running on this
    machine. ``outbound_text`` is what may leave, and for a redacting decision it is the
    version with placeholders in it. They are separate fields rather than one field and
    a flag, so that sending the wrong one is a visible mistake rather than a forgotten
    branch.
    """

    classification: ContentClassification
    local_text: str
    outbound_text: str
    placeholder_tokens: tuple[str, ...] = ()
    placeholder_map: PlaceholderMap | None = None
    """Held only to restore the reply. Never serialised, never sent. See the schema."""

    @classmethod
    def unredacted(cls, text: str, classification: ContentClassification) -> PreparedContent:
        """For content that needed no redaction. Both texts are the same thing."""
        return cls(classification=classification, local_text=text, outbound_text=text)


class _CallFields(TypedDict):
    """The fields every ``ModelCall`` carries, whatever the outcome.

    A ``TypedDict`` rather than a plain dict so that unpacking it into ``ModelCall``
    stays type-checked. A ``dict[str, object]`` would compile and would let a renamed
    schema field through silently.
    """

    task_id: str | None
    policy_decision_id: str | None
    provider: str
    model: str
    tier: ModelTier
    purpose: str
    max_sensitivity_permitted: SensitivityLevel
    fallback_chain: list[str]


@dataclass(frozen=True)
class Attempt:
    """One try against one model."""

    descriptor: ModelDescriptor
    call: ModelCall
    decision: PolicyDecision | None
    completion: Completion | None = None
    skipped_reason: str | None = None


@dataclass(frozen=True)
class GatewayResult:
    """What the caller gets back."""

    text: str
    """The reply, with placeholders restored where a map was supplied."""

    raw_text: str
    """The reply exactly as the model produced it, placeholders and all."""

    descriptor: ModelDescriptor
    call: ModelCall
    decision: PolicyDecision | None
    """``None`` when a local model answered, because nothing left the machine."""

    attempts: tuple[Attempt, ...] = field(default_factory=tuple)

    @property
    def cost(self) -> Money:
        """The cost of this result, including the failed attempts that preceded it."""
        return add_money(*[a.call.cost for a in self.attempts])

    @property
    def went_outbound(self) -> bool:
        return self.decision is not None

    @property
    def cost_is_complete(self) -> bool:
        """False when the provider reported no token usage, so the cost is a floor.

        A zero cost because a call was free and a zero cost because nobody told us how
        many tokens it used are the same number and different facts. Reporting that sums
        these has to say which it has.
        """
        return all(a.completion.usage_reported for a in self.attempts if a.completion)


class ModelGateway:
    """Routes a request, sends it the only way it is allowed to go, and prices it."""

    def __init__(
        self,
        registry: ModelRegistry,
        policy: PolicyEngine,
        prices: PriceTable | None = None,
        *,
        audit: AuditLog | None = None,
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._prices = prices or PriceTable()
        self._router = ModelRouter(registry, self._prices)
        self._audit = audit

    @property
    def router(self) -> ModelRouter:
        return self._router

    def complete(
        self,
        content: PreparedContent,
        requirement: Requirement,
        *,
        task_id: str | None = None,
        actor: str = "duckbot",
    ) -> GatewayResult:
        """Answer the request with the first eligible model that works."""
        chain = self._router.route(requirement)
        attempts: list[Attempt] = []
        tried: list[str] = []

        for descriptor in chain:
            if self._registry.is_local(descriptor.key):
                outcome = self._try_local(descriptor, content, requirement, tried, task_id)
            else:
                outcome = self._try_remote(descriptor, content, requirement, tried, task_id, actor)

            attempts.append(outcome)
            if outcome.skipped_reason is None:
                tried.append(descriptor.key)
            if outcome.call.succeeded:
                return self._finish(descriptor, outcome, content, attempts, actor, task_id)

        raise AdapterFailure(
            "every eligible model failed or was refused: "
            + "; ".join(f"{a.descriptor.key}: {a.skipped_reason or a.call.error}" for a in attempts)
        )

    # ------------------------------------------------------------------ local

    def _try_local(
        self,
        descriptor: ModelDescriptor,
        content: PreparedContent,
        requirement: Requirement,
        tried: list[str],
        task_id: str | None,
    ) -> Attempt:
        adapter = self._registry.local(descriptor.key)
        if adapter is None:  # pragma: no cover - registry inconsistency
            raise GatewayError(f"{descriptor.key} is not registered as a local adapter")

        started = perf_counter()
        try:
            completion = adapter.complete(content.local_text, purpose=requirement.purpose)
        except AdapterFailure as exc:
            return Attempt(
                descriptor,
                self._failed_call(descriptor, requirement, tried, task_id, str(exc), started),
                None,
            )
        return Attempt(
            descriptor,
            self._succeeded_call(descriptor, requirement, tried, task_id, completion, None),
            None,
            completion=completion,
        )

    # ----------------------------------------------------------------- remote

    def _try_remote(
        self,
        descriptor: ModelDescriptor,
        content: PreparedContent,
        requirement: Requirement,
        tried: list[str],
        task_id: str | None,
        actor: str,
    ) -> Attempt:
        adapter = self._registry.remote(descriptor.key)
        if adapter is None:  # pragma: no cover - registry inconsistency
            raise GatewayError(f"{descriptor.key} is not registered as a remote adapter")

        self._assert_priced(descriptor)

        decision, permit = self._policy.evaluate(
            content.classification,
            destination=descriptor.key,
            redacted_payload=content.outbound_text,
            placeholder_tokens=content.placeholder_tokens,
        )
        if self._audit is not None:
            self._audit.record(
                actor=actor,
                action=AuditAction.POLICY_EVALUATED,
                classification_id=content.classification.id,
                policy_decision_id=decision.id,
                task_id=task_id,
                sensitivity=decision.input_sensitivity,
                policy_action=decision.action,
                destination=descriptor.key,
            )

        if permit is None:
            if decision.action is PolicyAction.BLOCK:
                raise GatewayError(
                    f"policy blocked this content: {decision.justification} "
                    "Nothing else was tried, because a block is a decision about the "
                    "content and not about the provider."
                )
            return Attempt(
                descriptor,
                self._skipped_call(descriptor, requirement, tried, task_id, decision),
                decision,
                skipped_reason=(
                    f"policy returned {decision.action.value}; this content does not go "
                    "to a hosted provider"
                ),
            )

        started = perf_counter()
        try:
            completion = adapter.complete(permit, purpose=requirement.purpose)
        except AdapterFailure as exc:
            return Attempt(
                descriptor,
                self._failed_call(
                    descriptor, requirement, tried, task_id, str(exc), started, decision
                ),
                decision,
            )

        self._record_send(actor, descriptor, content, decision, permit, task_id)
        return Attempt(
            descriptor,
            self._succeeded_call(descriptor, requirement, tried, task_id, completion, decision),
            decision,
            completion=completion,
        )

    # ------------------------------------------------------------- bookkeeping

    def _assert_priced(self, descriptor: ModelDescriptor) -> None:
        """Refuse to spend money blind, before spending it.

        There is deliberately no way to switch this off. An opt-out would have to record
        *something* as the cost of a call it could not price, and a zero is
        indistinguishable from a free call once it is in the report. If a model really
        should cost nothing — a free tier, an experiment, a provider being trialled —
        give it an explicit zero price with a source saying so. The file then records
        that somebody decided, rather than that nobody looked.
        """
        if self._prices.get(descriptor.key) is None:
            raise UnknownPrice(
                f"no price is configured for {descriptor.key}, so this call would be made "
                "without knowing what it costs. Add it to the price file — an explicit "
                "zero with a source is a valid answer; silence is not."
            )

    def _call_kwargs(
        self,
        descriptor: ModelDescriptor,
        requirement: Requirement,
        tried: list[str],
        task_id: str | None,
        decision: PolicyDecision | None,
    ) -> _CallFields:
        return {
            "task_id": task_id,
            "policy_decision_id": decision.id if decision else None,
            "provider": descriptor.provider,
            "model": descriptor.model,
            "tier": descriptor.tier,
            "purpose": requirement.purpose,
            "max_sensitivity_permitted": descriptor.max_sensitivity,
            "fallback_chain": list(tried),
        }

    def _succeeded_call(
        self,
        descriptor: ModelDescriptor,
        requirement: Requirement,
        tried: list[str],
        task_id: str | None,
        completion: Completion,
        decision: PolicyDecision | None,
    ) -> ModelCall:
        cost = self._prices.cost(
            descriptor, tokens_in=completion.tokens_in, tokens_out=completion.tokens_out
        )
        return ModelCall(
            **self._call_kwargs(descriptor, requirement, tried, task_id, decision),
            tokens_in=completion.tokens_in,
            tokens_out=completion.tokens_out,
            cost=cost,
            latency_ms=completion.latency_ms,
            succeeded=True,
        )

    def _failed_call(
        self,
        descriptor: ModelDescriptor,
        requirement: Requirement,
        tried: list[str],
        task_id: str | None,
        error: str,
        started: float,
        decision: PolicyDecision | None = None,
    ) -> ModelCall:
        """A failed call still costs time, and sometimes tokens we cannot see.

        Cost is recorded as zero because the provider reported no usage, which is not the
        same as the call having been free. The latency is real and is what makes a
        chronically failing provider visible in a cost report.
        """
        return ModelCall(
            **self._call_kwargs(descriptor, requirement, tried, task_id, decision),
            latency_ms=int((perf_counter() - started) * 1000),
            succeeded=False,
            error=error,
        )

    def _skipped_call(
        self,
        descriptor: ModelDescriptor,
        requirement: Requirement,
        tried: list[str],
        task_id: str | None,
        decision: PolicyDecision,
    ) -> ModelCall:
        return ModelCall(
            **self._call_kwargs(descriptor, requirement, tried, task_id, decision),
            succeeded=False,
            error=f"not attempted: policy action {decision.action.value}",
        )

    def _record_send(
        self,
        actor: str,
        descriptor: ModelDescriptor,
        content: PreparedContent,
        decision: PolicyDecision,
        permit: OutboundPermit,
        task_id: str | None,
    ) -> None:
        if self._audit is None:
            return
        self._audit.record(
            actor=actor,
            action=AuditAction.SENT_TO_MODEL,
            target=descriptor.key,
            task_id=task_id,
            classification_id=content.classification.id,
            policy_decision_id=decision.id,
            sensitivity=decision.input_sensitivity,
            policy_action=decision.action,
            destination=descriptor.key,
            placeholder_tokens=list(permit.placeholder_tokens),
        )

    def _finish(
        self,
        descriptor: ModelDescriptor,
        outcome: Attempt,
        content: PreparedContent,
        attempts: list[Attempt],
        actor: str,
        task_id: str | None,
    ) -> GatewayResult:
        if outcome.completion is None:  # pragma: no cover - defensive
            raise GatewayError("a successful attempt must carry the completion it produced")
        raw = outcome.completion.text
        restored = raw
        if outcome.decision is not None and content.placeholder_map is not None:
            restored = content.placeholder_map.restore(raw)
            if self._audit is not None and restored != raw:
                self._audit.record(
                    actor=actor,
                    action=AuditAction.RESPONSE_RESTORED,
                    target=descriptor.key,
                    task_id=task_id,
                    classification_id=content.classification.id,
                    model_call_id=outcome.call.id,
                )
        return GatewayResult(
            text=restored,
            raw_text=raw,
            descriptor=descriptor,
            call=outcome.call,
            decision=outcome.decision,
            attempts=tuple(attempts),
        )
