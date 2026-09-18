"""What a model endpoint is, and what it is allowed to see.

A descriptor is configuration, not code. Adding a provider should mean adding an entry,
not editing the router — that is what the handover means by "the same task runs against
different providers with no application code change".

The field that matters most is ``max_sensitivity``. It is the ceiling on what this
endpoint may receive, and it is a property of *where the content goes*, not of how good
the model is. A frontier model on someone else's servers is still someone else's
servers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from duckbot_schemas import ModelTier, SensitivityLevel


class Capability(StrEnum):
    """What a caller can require of a model.

    Kept small on purpose. Each value has to be something an operator can answer
    truthfully about their own deployment, because these are declared in configuration
    and nothing verifies them.
    """

    TEXT = "text"
    TOOL_USE = "tool_use"
    VISION = "vision"
    STRUCTURED_OUTPUT = "structured_output"
    TRADITIONAL_CHINESE = "traditional_chinese"
    """Usable Traditional Chinese output.

    A separate capability because it is the one our customers notice first and the one
    most likely to differ between a frontier model and a small local one. Nothing here
    can measure it; an operator declares it, and the evaluation set in Workstream E is
    what should eventually decide it.
    """


@dataclass(frozen=True)
class ModelDescriptor:
    """One model endpoint, as configured."""

    provider: str
    model: str
    tier: ModelTier
    context_window: int
    max_sensitivity: SensitivityLevel
    capabilities: frozenset[Capability] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.model.strip():
            raise ValueError("a descriptor needs a provider and a model")
        if self.context_window <= 0:
            raise ValueError("context window must be positive")
        if self.tier is not ModelTier.LOCAL and self.max_sensitivity is SensitivityLevel.LOCAL_ONLY:
            raise ValueError(
                f"{self.provider}/{self.model} is not a local model and cannot declare "
                "itself fit for LOCAL_ONLY content. LOCAL_ONLY means the content does not "
                "leave this machine; a hosted endpoint cannot satisfy that however it is "
                "configured."
            )

    @property
    def key(self) -> str:
        """Stable identifier used in logs, cost records and fallback chains."""
        return f"{self.provider}/{self.model}"

    def accepts(self, sensitivity: SensitivityLevel) -> bool:
        return sensitivity <= self.max_sensitivity

    def supports(self, required: frozenset[Capability]) -> bool:
        return required <= self.capabilities
