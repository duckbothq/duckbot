"""Construct the Python task engine from validated desktop settings."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from duckbot_engine import StoreBundle, TaskEngine
from duckbot_gateway import (
    AnthropicClient,
    Capability,
    ChatClient,
    EchoClient,
    LocalAdapter,
    ModelDescriptor,
    ModelPrice,
    ModelRegistry,
    OllamaClient,
    OpenAICompatibleClient,
    PriceTable,
    RemoteAdapter,
)
from duckbot_memory import ContextCompiler, LexicalIndex
from duckbot_schemas import ModelTier, SensitivityLevel

from .secret_store import SecretStore
from .settings import DesktopSettings

_TEXT_CHINESE = frozenset({Capability.TEXT, Capability.TRADITIONAL_CHINESE})


def build_engine(
    settings: DesktopSettings,
    *,
    stores: StoreBundle,
    secrets: SecretStore,
) -> TaskEngine:
    """Build one configured engine without exposing credentials to its callers."""
    registry = ModelRegistry()
    prices = PriceTable()

    if settings.provider == "offline":
        descriptor = ModelDescriptor(
            provider="duckbot-offline",
            model="privacy-demo",
            tier=ModelTier.LOCAL,
            context_window=int(settings.max_context_tokens),
            max_sensitivity=SensitivityLevel.LOCAL_ONLY,
            capabilities=_TEXT_CHINESE,
        )
        registry.register_local(
            LocalAdapter(descriptor, EchoClient("本機離線示範 / Local offline demo"))
        )
    elif settings.provider == "ollama":
        descriptor = ModelDescriptor(
            provider="ollama",
            model=settings.local_model,
            tier=ModelTier.LOCAL,
            context_window=int(settings.max_context_tokens),
            max_sensitivity=SensitivityLevel.LOCAL_ONLY,
            capabilities=_TEXT_CHINESE,
        )
        registry.register_local(
            LocalAdapter(
                descriptor,
                OllamaClient(model=settings.local_model, base_url=settings.local_endpoint),
            )
        )
    else:
        key = secrets.get(settings.provider)
        if not key:
            raise ValueError("selected hosted provider has no API key in secure storage")
        descriptor = ModelDescriptor(
            provider=settings.provider,
            model=settings.provider_model,
            tier=ModelTier.FRONTIER,
            context_window=int(settings.max_context_tokens),
            max_sensitivity=SensitivityLevel.ANONYMIZE,
            capabilities=_TEXT_CHINESE,
        )
        client: ChatClient
        if settings.provider == "openai":
            client = OpenAICompatibleClient(
                base_url=settings.hosted_endpoint or "https://api.openai.com/v1",
                model=settings.provider_model,
                api_key=key,
            )
        else:
            client = AnthropicClient(
                api_key=key,
                model=settings.provider_model,
                base_url=settings.hosted_endpoint or "https://api.anthropic.com",
            )
        registry.register_remote(RemoteAdapter(descriptor, client))
        prices.add(
            ModelPrice(
                provider=descriptor.provider,
                model=descriptor.model,
                input_per_mtok=Decimal(settings.input_per_mtok),
                output_per_mtok=Decimal(settings.output_per_mtok),
                currency=settings.price_currency.upper(),
                source=settings.price_source,
                checked_on=date.fromisoformat(settings.price_checked_on),
            )
        )

    return TaskEngine(
        compiler=ContextCompiler(LexicalIndex()),
        registry=registry,
        prices=prices,
        stores=stores,
    )
