"""Duckbot model gateway — routing, adapters and per-call cost accounting.

Workstream C of the engineering handover. One frontier model, one low-cost model and one
local model behind a single interface, chosen by sensitivity first and cost second, with
a cost figure attached to every call.
"""

from .adapters import (
    AnthropicClient,
    ChatClient,
    Completion,
    EchoClient,
    FailingClient,
    HttpResponse,
    HttpTransport,
    LocalAdapter,
    LocalModelAdapter,
    OllamaClient,
    OpenAICompatibleClient,
    RecordingClient,
    RemoteAdapter,
    RemoteModelAdapter,
    ScriptedClient,
    UrllibTransport,
)
from .descriptors import Capability, ModelDescriptor
from .errors import (
    AdapterFailure,
    GatewayError,
    NoEligibleModel,
    SensitivityCeilingExceeded,
    UnknownPrice,
)
from .gateway import Attempt, GatewayResult, ModelGateway, PreparedContent
from .pricing import ModelPrice, PriceTable, add_money
from .routing import ModelRegistry, ModelRouter, Rejection, Requirement

__all__ = [
    "AdapterFailure",
    "AnthropicClient",
    "Attempt",
    "Capability",
    "ChatClient",
    "Completion",
    "EchoClient",
    "FailingClient",
    "GatewayError",
    "GatewayResult",
    "HttpResponse",
    "HttpTransport",
    "LocalAdapter",
    "LocalModelAdapter",
    "ModelDescriptor",
    "ModelGateway",
    "ModelPrice",
    "ModelRegistry",
    "ModelRouter",
    "NoEligibleModel",
    "OllamaClient",
    "OpenAICompatibleClient",
    "PreparedContent",
    "PriceTable",
    "RecordingClient",
    "Rejection",
    "RemoteAdapter",
    "RemoteModelAdapter",
    "Requirement",
    "ScriptedClient",
    "SensitivityCeilingExceeded",
    "UnknownPrice",
    "UrllibTransport",
    "add_money",
]
