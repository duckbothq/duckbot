"""Model adapters: the permit boundary, the wire formats, and offline stand-ins."""

from .base import (
    ChatClient,
    Completion,
    LocalAdapter,
    LocalModelAdapter,
    RemoteAdapter,
    RemoteModelAdapter,
)
from .http import (
    AnthropicClient,
    HttpResponse,
    HttpTransport,
    OllamaClient,
    OpenAICompatibleClient,
    UrllibTransport,
)
from .memory import EchoClient, FailingClient, RecordingClient, ScriptedClient

__all__ = [
    "AnthropicClient",
    "ChatClient",
    "Completion",
    "EchoClient",
    "FailingClient",
    "HttpResponse",
    "HttpTransport",
    "LocalAdapter",
    "LocalModelAdapter",
    "OllamaClient",
    "OpenAICompatibleClient",
    "RecordingClient",
    "RemoteAdapter",
    "RemoteModelAdapter",
    "ScriptedClient",
    "UrllibTransport",
]
