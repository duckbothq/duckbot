"""Routing: sensitivity is a constraint, cost is a preference.

The first test in this file is the one that matters. If it ever fails, the product has
stopped being the thing it is sold as.
"""

from __future__ import annotations

import pytest
from duckbot_schemas import ModelTier, SensitivityLevel

from duckbot_gateway import (
    Capability,
    EchoClient,
    LocalAdapter,
    ModelDescriptor,
    ModelRegistry,
    ModelRouter,
    NoEligibleModel,
    PriceTable,
    RemoteAdapter,
    Requirement,
)

TEXT = frozenset({Capability.TEXT})


@pytest.fixture
def registry(
    local_descriptor: ModelDescriptor,
    cheap_descriptor: ModelDescriptor,
    frontier_descriptor: ModelDescriptor,
) -> ModelRegistry:
    registry = ModelRegistry()
    registry.register_local(LocalAdapter(local_descriptor, EchoClient("local")))
    registry.register_remote(RemoteAdapter(cheap_descriptor, EchoClient("cheap")))
    registry.register_remote(RemoteAdapter(frontier_descriptor, EchoClient("frontier")))
    return registry


@pytest.fixture
def router(registry: ModelRegistry, prices: PriceTable) -> ModelRouter:
    return ModelRouter(registry, prices)


class TestSensitivityIsAConstraint:
    def test_local_only_content_reaches_only_the_local_model(self, router: ModelRouter) -> None:
        chain = router.route(
            Requirement(purpose="summarise", sensitivity=SensitivityLevel.LOCAL_ONLY)
        )
        assert [d.tier for d in chain] == [ModelTier.LOCAL]

    def test_no_preference_can_override_it(self, router: ModelRouter) -> None:
        """Asking for a frontier model does not make one eligible for local-only content."""
        chain = router.route(
            Requirement(
                purpose="summarise",
                sensitivity=SensitivityLevel.LOCAL_ONLY,
                prefer=ModelTier.FRONTIER,
            )
        )
        assert [d.key for d in chain] == ["ollama/small-local"]

    def test_derive_content_also_stays_local_with_these_ceilings(self, router: ModelRouter) -> None:
        chain = router.route(purpose_at(SensitivityLevel.DERIVE))
        assert all(d.tier is ModelTier.LOCAL for d in chain)


def purpose_at(level: SensitivityLevel, **kwargs: object) -> Requirement:
    return Requirement(purpose="summarise", sensitivity=level, **kwargs)  # type: ignore[arg-type]


class TestOrdering:
    def test_cheapest_and_most_private_first(self, router: ModelRouter) -> None:
        chain = router.route(purpose_at(SensitivityLevel.ANONYMIZE))
        assert [d.tier for d in chain] == [
            ModelTier.LOCAL,
            ModelTier.LOW_COST,
            ModelTier.FRONTIER,
        ]

    def test_a_preference_moves_a_tier_to_the_front_without_removing_the_rest(
        self, router: ModelRouter
    ) -> None:
        """The others stay in the chain, because a preference is not a restriction."""
        chain = router.route(purpose_at(SensitivityLevel.ANONYMIZE, prefer=ModelTier.FRONTIER))
        assert chain[0].tier is ModelTier.FRONTIER
        assert len(chain) == 3

    def test_an_unpriced_model_sorts_last_among_its_tier(
        self, registry: ModelRegistry, prices: PriceTable
    ) -> None:
        """Choosing it first would hide missing configuration behind a working call."""
        unpriced = ModelDescriptor(
            provider="example-cheap",
            model="mystery-1",
            tier=ModelTier.LOW_COST,
            context_window=32_000,
            max_sensitivity=SensitivityLevel.ANONYMIZE,
            capabilities=TEXT,
        )
        registry.register_remote(RemoteAdapter(unpriced, EchoClient()))
        chain = ModelRouter(registry, prices).route(purpose_at(SensitivityLevel.ANONYMIZE))
        low_cost = [d.key for d in chain if d.tier is ModelTier.LOW_COST]
        assert low_cost == ["example-cheap/fast-1", "example-cheap/mystery-1"]

    def test_token_estimates_are_used_when_given(
        self, registry: ModelRegistry, prices: PriceTable
    ) -> None:
        """Output-heavy work can reorder models whose input prices suggest otherwise."""
        router = ModelRouter(registry, prices)
        chain = router.eligible(
            Requirement(
                purpose="drafting",
                sensitivity=SensitivityLevel.ANONYMIZE,
                estimated_tokens_in=100,
                estimated_tokens_out=10_000,
            )
        )[0]
        assert [d.tier for d in chain][:2] == [ModelTier.LOCAL, ModelTier.LOW_COST]


class TestFiltering:
    def test_capabilities_are_required_not_preferred(self, router: ModelRouter) -> None:
        chain = router.route(
            purpose_at(SensitivityLevel.ANONYMIZE, capabilities=frozenset({Capability.VISION}))
        )
        assert [d.key for d in chain] == ["example-frontier/big-1"]

    def test_context_window_filters(self, router: ModelRouter) -> None:
        chain = router.route(purpose_at(SensitivityLevel.ANONYMIZE, min_context_window=100_000))
        assert [d.key for d in chain] == ["example-frontier/big-1"]

    def test_rejections_carry_a_reason(self, router: ModelRouter) -> None:
        _, rejected = router.eligible(purpose_at(SensitivityLevel.LOCAL_ONLY))
        reasons = {r.key: r.reason for r in rejected}
        assert "may receive up to ANONYMIZE" in reasons["example-cheap/fast-1"]


class TestRefusal:
    def test_the_error_names_the_constraint(self, router: ModelRouter) -> None:
        """ "No model available" with no reason is an unanswerable support ticket."""
        with pytest.raises(NoEligibleModel) as excinfo:
            router.route(
                purpose_at(
                    SensitivityLevel.ANONYMIZE,
                    capabilities=frozenset({Capability.STRUCTURED_OUTPUT}),
                )
            )
        message = str(excinfo.value)
        assert "lacks structured_output" in message
        assert "example-frontier/big-1" in message

    def test_an_empty_registry_says_what_to_add(self) -> None:
        with pytest.raises(NoEligibleModel, match="Register at least one local adapter"):
            ModelRouter(ModelRegistry()).route(purpose_at(SensitivityLevel.PUBLIC))


class TestRegistration:
    def test_a_local_model_cannot_be_registered_as_remote(
        self, local_descriptor: ModelDescriptor
    ) -> None:
        registry = ModelRegistry()
        with pytest.raises(ValueError, match="would be a lie about where the content went"):
            registry.register_remote(LocalAdapter(local_descriptor, EchoClient()))  # type: ignore[arg-type]

    def test_a_requirement_must_say_what_it_is_for(self) -> None:
        with pytest.raises(ValueError, match="what the call is for"):
            Requirement(purpose="  ", sensitivity=SensitivityLevel.PUBLIC)
