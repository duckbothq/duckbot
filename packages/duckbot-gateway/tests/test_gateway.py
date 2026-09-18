"""The gateway end to end, without a network.

The tests that earn their place here are the ones asserting what a provider *received*.
Everything else in this package is arrangement; whether the real value stayed on the
machine is the product.

Every name and identity number below is invented.
"""

from __future__ import annotations

import pytest
from duckbot_core import AuditLog, InMemoryAuditStore, PolicyEngine, Rule
from duckbot_schemas import (
    AuditAction,
    ModelTier,
    PlaceholderMap,
    PolicyAction,
    SensitivityLevel,
)

from duckbot_gateway import (
    AdapterFailure,
    Capability,
    EchoClient,
    FailingClient,
    GatewayError,
    LocalAdapter,
    ModelDescriptor,
    ModelGateway,
    ModelRegistry,
    PreparedContent,
    PriceTable,
    RecordingClient,
    RemoteAdapter,
    Requirement,
    UnknownPrice,
)
from helpers import classification

NAME = "陳嘉雯"
HKID = "A123456(3)"
REAL = f"請跟進客戶{NAME}，身份證 {HKID}。"


@pytest.fixture
def local_client() -> RecordingClient:
    return RecordingClient(EchoClient("local").chat)


@pytest.fixture
def cheap_client() -> RecordingClient:
    return RecordingClient(EchoClient("cheap").chat)


@pytest.fixture
def frontier_client() -> RecordingClient:
    return RecordingClient(EchoClient("frontier").chat)


@pytest.fixture
def registry(
    local_descriptor: ModelDescriptor,
    cheap_descriptor: ModelDescriptor,
    frontier_descriptor: ModelDescriptor,
    local_client: RecordingClient,
    cheap_client: RecordingClient,
    frontier_client: RecordingClient,
) -> ModelRegistry:
    registry = ModelRegistry()
    registry.register_local(LocalAdapter(local_descriptor, local_client))
    registry.register_remote(RemoteAdapter(cheap_descriptor, cheap_client))
    registry.register_remote(RemoteAdapter(frontier_descriptor, frontier_client))
    return registry


@pytest.fixture
def gateway(registry: ModelRegistry, prices: PriceTable) -> ModelGateway:
    return ModelGateway(registry, PolicyEngine(), prices)


def redacted_content() -> tuple[PreparedContent, PlaceholderMap]:
    """Content as the privacy gateway would hand it over."""
    mapping = PlaceholderMap()
    name_token = mapping.token_for(NAME, "PERSON_NAME")
    hkid_token = mapping.token_for(HKID, "HKID")
    outbound = REAL.replace(NAME, name_token).replace(HKID, hkid_token)
    content = PreparedContent(
        classification=classification(SensitivityLevel.ANONYMIZE),
        local_text=REAL,
        outbound_text=outbound,
        placeholder_tokens=(name_token, hkid_token),
        placeholder_map=mapping,
    )
    return content, mapping


class TestLocalOnlyContent:
    def test_it_goes_to_the_local_model_and_nowhere_else(
        self,
        gateway: ModelGateway,
        local_client: RecordingClient,
        cheap_client: RecordingClient,
        frontier_client: RecordingClient,
    ) -> None:
        content = PreparedContent.unredacted(REAL, classification(SensitivityLevel.LOCAL_ONLY))
        result = gateway.complete(
            content, Requirement(purpose="summarise", sensitivity=SensitivityLevel.LOCAL_ONLY)
        )
        assert result.descriptor.tier is ModelTier.LOCAL
        assert local_client.sent == [REAL]
        assert cheap_client.sent == []
        assert frontier_client.sent == []

    def test_nothing_went_outbound_so_there_is_no_decision(self, gateway: ModelGateway) -> None:
        content = PreparedContent.unredacted(REAL, classification(SensitivityLevel.LOCAL_ONLY))
        result = gateway.complete(
            content, Requirement(purpose="summarise", sensitivity=SensitivityLevel.LOCAL_ONLY)
        )
        assert result.decision is None
        assert not result.went_outbound

    def test_a_local_call_costs_nothing(self, gateway: ModelGateway) -> None:
        content = PreparedContent.unredacted(REAL, classification(SensitivityLevel.LOCAL_ONLY))
        result = gateway.complete(
            content, Requirement(purpose="summarise", sensitivity=SensitivityLevel.LOCAL_ONLY)
        )
        assert result.cost.as_float() == 0.0


class TestRedactedContentGoingOut:
    def test_the_provider_never_sees_the_real_values(
        self, gateway: ModelGateway, frontier_client: RecordingClient
    ) -> None:
        """The assertion the product is sold on, made against what the provider received."""
        content, _ = redacted_content()
        gateway.complete(
            content,
            Requirement(
                purpose="drafting",
                sensitivity=SensitivityLevel.ANONYMIZE,
                prefer=ModelTier.FRONTIER,
            ),
        )
        (sent,) = frontier_client.sent
        assert NAME not in sent
        assert HKID not in sent
        assert "請跟進客戶" in sent

    def test_the_reply_comes_back_with_the_values_restored(self, gateway: ModelGateway) -> None:
        content, _ = redacted_content()
        result = gateway.complete(
            content,
            Requirement(
                purpose="drafting",
                sensitivity=SensitivityLevel.ANONYMIZE,
                prefer=ModelTier.FRONTIER,
            ),
        )
        assert NAME in result.text
        assert HKID in result.text
        assert NAME not in result.raw_text, "the raw reply must still be the redacted one"

    def test_the_decision_is_recorded_against_the_call(self, gateway: ModelGateway) -> None:
        content, _ = redacted_content()
        result = gateway.complete(
            content,
            Requirement(
                purpose="drafting",
                sensitivity=SensitivityLevel.ANONYMIZE,
                prefer=ModelTier.FRONTIER,
            ),
        )
        assert result.decision is not None
        assert result.decision.action is PolicyAction.REDACT
        assert result.call.policy_decision_id == result.decision.id
        assert result.call.max_sensitivity_permitted is SensitivityLevel.ANONYMIZE


class TestCostAccounting:
    def test_a_successful_call_is_priced_from_the_table(self, gateway: ModelGateway) -> None:
        content, _ = redacted_content()
        result = gateway.complete(
            content,
            Requirement(
                purpose="drafting",
                sensitivity=SensitivityLevel.ANONYMIZE,
                prefer=ModelTier.FRONTIER,
            ),
        )
        assert result.call.tokens_in > 0
        assert result.cost.as_float() > 0

    def test_an_unpriced_model_is_refused_before_the_call_is_made(
        self,
        registry: ModelRegistry,
        cheap_client: RecordingClient,
        cheap_descriptor: ModelDescriptor,
    ) -> None:
        """No money is spent, and nothing is sent, while the configuration is incomplete."""
        gateway = ModelGateway(registry, PolicyEngine(), PriceTable())
        content, _ = redacted_content()
        with pytest.raises(UnknownPrice, match="explicit zero with a source is a valid answer"):
            gateway.complete(
                content,
                Requirement(
                    purpose="drafting",
                    sensitivity=SensitivityLevel.ANONYMIZE,
                    prefer=ModelTier.LOW_COST,
                    capabilities=frozenset({Capability.TEXT}),
                    min_context_window=20_000,
                ),
            )
        assert cheap_client.sent == []
        assert cheap_descriptor.tier is ModelTier.LOW_COST


class TestFallback:
    @pytest.fixture
    def failing_cheap(
        self,
        registry: ModelRegistry,
        cheap_descriptor: ModelDescriptor,
    ) -> FailingClient:
        client = FailingClient("503 from provider")
        registry.register_remote(RemoteAdapter(cheap_descriptor, client))
        return client

    def test_the_next_model_is_tried(
        self,
        registry: ModelRegistry,
        prices: PriceTable,
        failing_cheap: FailingClient,
        frontier_client: RecordingClient,
    ) -> None:
        gateway = ModelGateway(registry, PolicyEngine(), prices)
        content, _ = redacted_content()
        result = gateway.complete(
            content,
            Requirement(
                purpose="drafting",
                sensitivity=SensitivityLevel.ANONYMIZE,
                min_context_window=20_000,
            ),
        )
        assert result.descriptor.tier is ModelTier.FRONTIER
        assert len(failing_cheap.calls) == 1
        assert len(frontier_client.sent) == 1

    def test_what_was_tried_first_is_recorded(
        self, registry: ModelRegistry, prices: PriceTable, failing_cheap: FailingClient
    ) -> None:
        """ "It worked" and "it worked first time" are different operational facts."""
        gateway = ModelGateway(registry, PolicyEngine(), prices)
        content, _ = redacted_content()
        result = gateway.complete(
            content,
            Requirement(
                purpose="drafting",
                sensitivity=SensitivityLevel.ANONYMIZE,
                min_context_window=20_000,
            ),
        )
        assert result.call.fallback_chain == ["example-cheap/fast-1"]
        assert [a.call.succeeded for a in result.attempts] == [False, True]

    def test_a_failed_attempt_records_why(
        self, registry: ModelRegistry, prices: PriceTable, failing_cheap: FailingClient
    ) -> None:
        gateway = ModelGateway(registry, PolicyEngine(), prices)
        content, _ = redacted_content()
        result = gateway.complete(
            content,
            Requirement(
                purpose="drafting",
                sensitivity=SensitivityLevel.ANONYMIZE,
                min_context_window=20_000,
            ),
        )
        failed = result.attempts[0].call
        assert failed.error is not None
        assert "503" in failed.error

    def test_when_everything_fails_the_error_lists_each_provider(
        self, prices: PriceTable, cheap_descriptor: ModelDescriptor
    ) -> None:
        registry = ModelRegistry()
        registry.register_remote(RemoteAdapter(cheap_descriptor, FailingClient("timeout")))
        gateway = ModelGateway(registry, PolicyEngine(), prices)
        content, _ = redacted_content()
        with pytest.raises(AdapterFailure, match="example-cheap/fast-1: timeout"):
            gateway.complete(
                content,
                Requirement(purpose="drafting", sensitivity=SensitivityLevel.ANONYMIZE),
            )


class TestPolicyRefusals:
    def test_a_block_stops_everything(
        self,
        registry: ModelRegistry,
        prices: PriceTable,
        cheap_client: RecordingClient,
        frontier_client: RecordingClient,
    ) -> None:
        """A block is a decision about the content, so trying elsewhere is exactly wrong."""
        policy = PolicyEngine(
            [
                Rule(
                    id="no-hkid-outbound",
                    description="content containing an identity number does not leave",
                    action=PolicyAction.BLOCK,
                    entity_types=frozenset({"PERSON_NAME"}),
                )
            ]
        )
        gateway = ModelGateway(registry, policy, prices)
        content, _ = redacted_content()
        with pytest.raises(GatewayError, match="policy blocked this content"):
            gateway.complete(
                content,
                Requirement(
                    purpose="drafting",
                    sensitivity=SensitivityLevel.ANONYMIZE,
                    prefer=ModelTier.FRONTIER,
                ),
            )
        assert cheap_client.sent == []
        assert frontier_client.sent == []

    def test_a_local_only_rule_falls_through_to_the_local_model(
        self,
        registry: ModelRegistry,
        prices: PriceTable,
        local_client: RecordingClient,
        frontier_client: RecordingClient,
    ) -> None:
        """Not a provider failure: the answer is to stop sending it, not to send it elsewhere."""
        policy = PolicyEngine(
            [
                Rule(
                    id="names-stay-here",
                    description="anything with a person's name is handled locally",
                    action=PolicyAction.LOCAL_ONLY,
                    entity_types=frozenset({"PERSON_NAME"}),
                )
            ]
        )
        gateway = ModelGateway(registry, policy, prices)
        content, _ = redacted_content()
        result = gateway.complete(
            content,
            Requirement(
                purpose="drafting",
                sensitivity=SensitivityLevel.ANONYMIZE,
                prefer=ModelTier.FRONTIER,
            ),
        )
        assert result.descriptor.tier is ModelTier.LOCAL
        assert frontier_client.sent == []
        assert local_client.sent == [REAL]
        assert result.attempts[0].skipped_reason is not None


class TestAudit:
    def test_the_outbound_path_is_logged(self, registry: ModelRegistry, prices: PriceTable) -> None:
        store = InMemoryAuditStore()
        log = AuditLog(store)
        gateway = ModelGateway(registry, PolicyEngine(), prices, audit=log)
        content, _ = redacted_content()
        gateway.complete(
            content,
            Requirement(
                purpose="drafting",
                sensitivity=SensitivityLevel.ANONYMIZE,
                prefer=ModelTier.FRONTIER,
            ),
        )
        actions = [e.action for e in store.all_events()]
        assert AuditAction.POLICY_EVALUATED in actions
        assert AuditAction.SENT_TO_MODEL in actions
        assert AuditAction.RESPONSE_RESTORED in actions
        log.verify()

    def test_the_log_carries_tokens_and_not_values(
        self, registry: ModelRegistry, prices: PriceTable
    ) -> None:
        store = InMemoryAuditStore()
        gateway = ModelGateway(registry, PolicyEngine(), prices, audit=AuditLog(store))
        content, _ = redacted_content()
        gateway.complete(
            content,
            Requirement(
                purpose="drafting",
                sensitivity=SensitivityLevel.ANONYMIZE,
                prefer=ModelTier.FRONTIER,
            ),
        )
        dumped = "".join(e.model_dump_json() for e in store.all_events())
        assert NAME not in dumped
        assert HKID not in dumped
        assert "PERSON_NAME_" in dumped

    def test_a_purely_local_call_logs_no_send(
        self, registry: ModelRegistry, prices: PriceTable
    ) -> None:
        store = InMemoryAuditStore()
        gateway = ModelGateway(registry, PolicyEngine(), prices, audit=AuditLog(store))
        gateway.complete(
            PreparedContent.unredacted(REAL, classification(SensitivityLevel.LOCAL_ONLY)),
            Requirement(purpose="summarise", sensitivity=SensitivityLevel.LOCAL_ONLY),
        )
        assert [e.action for e in store.all_events()] == []
