"""The policy engine, and the permit that is the only way out.

The architecture rule is that the privacy gateway sits *on* the outbound path, not
beside it. A rule expressed only in documentation gets bypassed the first time someone
is in a hurry, so it is expressed here in types:

:class:`OutboundPermit` cannot be constructed from outside this module. Model adapters
accept a permit, not raw content. There is therefore no way to send anything outward
without having gone through :class:`PolicyEngine`, short of editing this file — which is
a reviewable act rather than an accident.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from duckbot_schemas import (
    ContentClassification,
    PolicyAction,
    PolicyDecision,
    SensitivityLevel,
)

from .errors import PolicyViolation

_PERMIT_KEY = object()
"""Module-private construction key. See :class:`OutboundPermit`."""


class OutboundPermit:
    """Proof that content was evaluated and may leave.

    Constructing one directly raises. The only producer is :meth:`PolicyEngine.evaluate`.
    """

    __slots__ = ("_decision", "_destination", "_payload", "_tokens")

    def __init__(
        self,
        key: object,
        *,
        decision: PolicyDecision,
        payload: str,
        destination: str,
        placeholder_tokens: Sequence[str] = (),
    ) -> None:
        if key is not _PERMIT_KEY:
            raise PolicyViolation(
                "an OutboundPermit cannot be constructed directly. Content leaves only "
                "through PolicyEngine.evaluate, which is what makes the privacy gateway "
                "impossible to bypass rather than merely inadvisable to bypass."
            )
        self._decision = decision
        self._payload = payload
        self._destination = destination
        self._tokens = tuple(placeholder_tokens)

    @property
    def decision(self) -> PolicyDecision:
        return self._decision

    @property
    def payload(self) -> str:
        """Exactly what will be transmitted. Already redacted, if redaction applied."""
        return self._payload

    @property
    def destination(self) -> str:
        return self._destination

    @property
    def placeholder_tokens(self) -> tuple[str, ...]:
        return self._tokens

    def __repr__(self) -> str:
        return (
            f"<OutboundPermit to {self._destination}, "
            f"{self._decision.action.value}, {len(self._tokens)} tokens>"
        )


@dataclass(frozen=True)
class Rule:
    """One policy rule.

    The rule *language* is deliberately undesigned — see the handover, Section 9. This is
    a working v0 that covers what Phase 1 needs, and it is meant to be replaced once the
    real categories are known from the Hong Kong corpus rather than guessed now.
    """

    id: str
    description: str
    action: PolicyAction
    min_sensitivity: SensitivityLevel = SensitivityLevel.PUBLIC
    max_sensitivity: SensitivityLevel = SensitivityLevel.LOCAL_ONLY
    entity_types: frozenset[str] = field(default_factory=frozenset)
    destinations: frozenset[str] = field(default_factory=frozenset)

    def matches(self, classification: ContentClassification, destination: str | None) -> bool:
        level = classification.effective_sensitivity
        if not (self.min_sensitivity <= level <= self.max_sensitivity):
            return False
        if self.destinations and (destination or "") not in self.destinations:
            return False
        if self.entity_types:
            present = {e.entity_type for e in classification.entities}
            if not (self.entity_types & present):
                return False
        return True


DEFAULT_ACTION_BY_LEVEL: dict[SensitivityLevel, PolicyAction] = {
    SensitivityLevel.PUBLIC: PolicyAction.ALLOW,
    SensitivityLevel.MINIMIZE: PolicyAction.REDACT,
    SensitivityLevel.ANONYMIZE: PolicyAction.REDACT,
    SensitivityLevel.DERIVE: PolicyAction.DERIVE,
    SensitivityLevel.LOCAL_ONLY: PolicyAction.LOCAL_ONLY,
}
"""What happens when no rule matches.

The defaults are restrictive on purpose. A policy engine whose fallback is "allow" is a
policy engine that fails open, and failing open is how a product like this ends up in the
news rather than in a tender.
"""

_JUSTIFICATIONS: dict[PolicyAction, str] = {
    PolicyAction.ALLOW: "No sensitive information was detected in this content.",
    PolicyAction.REDACT: "Sensitive values were replaced with placeholders before sending.",
    PolicyAction.DERIVE: "Only derived values are sent; the underlying data stays on this machine.",
    PolicyAction.LOCAL_ONLY: "This content is classified local-only and will not leave this machine.",
    PolicyAction.BLOCK: "This content is not permitted to be sent.",
}


class PolicyEngine:
    """Evaluates classified content against rules and issues permits."""

    def __init__(self, rules: Sequence[Rule] | None = None) -> None:
        self._rules: list[Rule] = list(rules or [])

    def add_rule(self, rule: Rule) -> None:
        self._rules.append(rule)

    @property
    def rules(self) -> tuple[Rule, ...]:
        return tuple(self._rules)

    def decide(
        self, classification: ContentClassification, destination: str | None
    ) -> PolicyDecision:
        """Return the decision without issuing a permit.

        Useful for the pre-send preview, which has to show the user what *would* happen
        before anything is committed to.
        """
        level = classification.effective_sensitivity
        matched: Rule | None = next(
            (r for r in self._rules if r.matches(classification, destination)), None
        )
        action = matched.action if matched else DEFAULT_ACTION_BY_LEVEL[level]

        outbound = action in (PolicyAction.ALLOW, PolicyAction.REDACT)
        kwargs: dict[str, Any] = {
            "classification_id": classification.id,
            "input_sensitivity": level,
            "action": action,
            "destination": destination if outbound else None,
            "matched_rule_id": matched.id if matched else None,
            "justification": _JUSTIFICATIONS[action],
        }
        if outbound and not destination:
            raise PolicyViolation(
                f"action {action.value} requires a destination but none was given"
            )
        return PolicyDecision(**kwargs)

    def evaluate(
        self,
        classification: ContentClassification,
        *,
        destination: str | None,
        redacted_payload: str,
        placeholder_tokens: Sequence[str] = (),
    ) -> tuple[PolicyDecision, OutboundPermit | None]:
        """Decide, and issue a permit if — and only if — the content may leave.

        Returns ``(decision, permit)``. The permit is ``None`` for anything that does not
        go outbound, so a caller that forgets to check gets a ``None`` rather than a way
        through.
        """
        decision = self.decide(classification, destination)

        if decision.action not in (PolicyAction.ALLOW, PolicyAction.REDACT):
            return decision, None

        assert decision.destination is not None  # guaranteed by PolicyDecision validation

        if decision.action is PolicyAction.REDACT and not placeholder_tokens:
            raise PolicyViolation(
                "a redact decision produced no placeholder tokens; either the content was "
                "not actually redacted or the tokens were not passed through. Sending it "
                "would mean sending the original."
            )

        permit = OutboundPermit(
            _PERMIT_KEY,
            decision=decision,
            payload=redacted_payload,
            destination=decision.destination,
            placeholder_tokens=placeholder_tokens,
        )
        return decision, permit
