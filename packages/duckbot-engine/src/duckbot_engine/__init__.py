"""Duckbot task engine.

The engine is the composition boundary. Lower-level packages remain independently
usable and ``duckbot-core`` never imports this package.
"""

from .connectors import (
    DEFAULT_MAX_FILE_BYTES,
    SUPPORTED_ENCODINGS,
    SUPPORTED_TEXT_SUFFIXES,
    Connector,
    ConnectorDocument,
    LocalFileConnector,
)
from .engine import TaskEngine
from .models import (
    ApprovalPending,
    EngineOutcome,
    StoreBundle,
    TaskCancelled,
    TaskPreview,
    TaskRequest,
    TaskResult,
)

__all__ = [
    "DEFAULT_MAX_FILE_BYTES",
    "SUPPORTED_ENCODINGS",
    "SUPPORTED_TEXT_SUFFIXES",
    "ApprovalPending",
    "Connector",
    "ConnectorDocument",
    "EngineOutcome",
    "LocalFileConnector",
    "StoreBundle",
    "TaskCancelled",
    "TaskEngine",
    "TaskPreview",
    "TaskRequest",
    "TaskResult",
]
