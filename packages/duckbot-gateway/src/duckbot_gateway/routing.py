"""Choosing a model.

One rule governs everything in this file: **sensitivity is a constraint and cost is a
preference.** A cheaper model that may not receive the content is not a candidate at
all, and no amount of saving makes it one. Everything else here — tier order, price
ordering, the fallback chain — operates only on the models that are already allowed.

The second rule is that a refusal must be explainable. ``NoEligibleModel`` names the
constraint that eliminated the candidates, because "no model available" with no reason
is an unanswerable support ticket at four in the afternoon.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from duckbot_schemas import ModelTier, SensitivityLevel

from .adapters.base import LocalModelAdapter, RemoteModelAdapter
from .descriptors import Capability, ModelDescriptor
from .errors import NoEligibleModel
from .pricing import TOKENS_PER_UNIT, PriceTable

_TIER_ORDER: dict[ModelTier, int] = {
    ModelTier.LOCAL: 0,
    ModelTier.LOW_COST: 1,
    ModelTier.FRONTIER: 2,
}
"""Cheapest and most private first.

Local is preferred not because it is best but because it costs nothing and sends
nothing. A caller who needs more says so with ``prefer``.
"""


@dataclass(frozen=True)
class Requirement:
    """What this particular call needs.

    ``sensitivity`` is the classification of the content, not a wish. It comes from the
    privacy gateway and it decides which models are eligible.
    """

    purpose: str
    sensitivity: SensitivityLevel
    capabilities: frozenset[Capability] = field(default_factory=frozenset)
    min_context_window: int = 0
    prefer: ModelTier | None = None
    """Ask for a tier when quality matters. Never overrides the sensitivity constraint."""

    estimated_tokens_in: int = 0
    estimated_tokens_out: int = 0
    """Used only to order candidates by price. Zero means order by input price alone."""

    def __post_init__(self) -> None:
        if not self.purpose.strip():
            raise ValueError("a requirement must say what the call is for")


@dataclass(frozen=True)
class Rejection:
    """Why one model was not eligible. Kept so the error message can be specific."""

    key: str
    reason: str


class ModelRegistry:
    """Every model this installation can use.

    Local and remote adapters are registered separately. That is what lets the router
    hand a string to one and a permit to the other without a runtime type test, and it
    catches a mis-declared descriptor at registration rather than at send time.
    """

    def __init__(self) -> None:
        self._local: dict[str, LocalModelAdapter] = {}
        self._remote: dict[str, RemoteModelAdapter] = {}

    def register_local(self, adapter: LocalModelAdapter) -> None:
        descriptor = adapter.descriptor
        if descriptor.tier is not ModelTier.LOCAL:
            raise ValueError(f"{descriptor.key} is not tier local")
        self._local[descriptor.key] = adapter

    def register_remote(self, adapter: RemoteModelAdapter) -> None:
        descriptor = adapter.descriptor
        if descriptor.tier is ModelTier.LOCAL:
            raise ValueError(
                f"{descriptor.key} is tier local and must be registered with "
                "register_local; a local model does not need a permit and asking for one "
                "would be a lie about where the content went"
            )
        self._remote[descriptor.key] = adapter

    @property
    def descriptors(self) -> list[ModelDescriptor]:
        return [
            *(a.descriptor for a in self._local.values()),
            *(a.descriptor for a in self._remote.values()),
        ]

    def local(self, key: str) -> LocalModelAdapter | None:
        return self._local.get(key)

    def remote(self, key: str) -> RemoteModelAdapter | None:
        return self._remote.get(key)

    def is_local(self, key: str) -> bool:
        return key in self._local


class ModelRouter:
    """Orders the eligible models for a requirement."""

    def __init__(self, registry: ModelRegistry, prices: PriceTable | None = None) -> None:
        self._registry = registry
        self._prices = prices or PriceTable()

    def _estimated_cost(self, descriptor: ModelDescriptor, requirement: Requirement) -> Decimal:
        """A sort key, not a quotation.

        Unknown prices sort last. A model nobody has priced should not be chosen ahead of
        one that has been, and ordering it first would hide the missing configuration
        behind a working call.
        """
        if descriptor.tier is ModelTier.LOCAL:
            return Decimal(0)
        price = self._prices.get(descriptor.key)
        if price is None:
            return Decimal("Infinity")
        if requirement.estimated_tokens_in or requirement.estimated_tokens_out:
            return (
                Decimal(requirement.estimated_tokens_in) * price.input_per_mtok
                + Decimal(requirement.estimated_tokens_out) * price.output_per_mtok
            ) / TOKENS_PER_UNIT
        return price.input_per_mtok

    def eligible(self, requirement: Requirement) -> tuple[list[ModelDescriptor], list[Rejection]]:
        """Return the allowed models in preference order, and why the others are not."""
        allowed: list[ModelDescriptor] = []
        rejected: list[Rejection] = []

        for descriptor in self._registry.descriptors:
            if not descriptor.accepts(requirement.sensitivity):
                rejected.append(
                    Rejection(
                        descriptor.key,
                        f"may receive up to {descriptor.max_sensitivity.name}, content is "
                        f"{requirement.sensitivity.name}",
                    )
                )
                continue
            if not descriptor.supports(requirement.capabilities):
                missing = sorted(
                    c.value for c in requirement.capabilities - descriptor.capabilities
                )
                rejected.append(Rejection(descriptor.key, f"lacks {', '.join(missing)}"))
                continue
            if descriptor.context_window < requirement.min_context_window:
                rejected.append(
                    Rejection(
                        descriptor.key,
                        f"context window {descriptor.context_window} < "
                        f"{requirement.min_context_window}",
                    )
                )
                continue
            allowed.append(descriptor)

        def sort_key(d: ModelDescriptor) -> tuple[int, int, Decimal, str]:
            preferred = 0 if requirement.prefer is not None and d.tier is requirement.prefer else 1
            return (preferred, _TIER_ORDER[d.tier], self._estimated_cost(d, requirement), d.key)

        allowed.sort(key=sort_key)
        return allowed, rejected

    def route(self, requirement: Requirement) -> list[ModelDescriptor]:
        """The fallback chain: first choice first, then what to try if it fails."""
        allowed, rejected = self.eligible(requirement)
        if allowed:
            return allowed

        if not rejected:
            raise NoEligibleModel(
                "no models are registered. Register at least one local adapter so that "
                "LOCAL_ONLY content has somewhere to go."
            )
        detail = "; ".join(f"{r.key}: {r.reason}" for r in rejected)
        raise NoEligibleModel(
            f"no model can handle {requirement.purpose} at "
            f"{requirement.sensitivity.name} — {detail}"
        )
