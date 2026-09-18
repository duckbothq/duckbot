"""The privacy gateway: classify, redact, restore.

This is the part a customer actually buys. The three operations have to be exactly
inverse of one another, and the mapping between real values and placeholders must never
leave the machine — which is why it is held in a
:class:`~duckbot_schemas.PlaceholderMap` that cannot be serialised.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from duckbot_schemas import (
    ContentClassification,
    DetectedEntity,
    DetectionMethod,
    PlaceholderMap,
    SensitivityLevel,
)

from .detectors import ALL_DETECTORS, Detection, Detector, detect_all

SENSITIVITY_BY_ENTITY: dict[str, SensitivityLevel] = {
    "HKID": SensitivityLevel.LOCAL_ONLY,
    "SALARY": SensitivityLevel.ANONYMIZE,
    "PERSON_NAME": SensitivityLevel.ANONYMIZE,
    "PHONE": SensitivityLevel.ANONYMIZE,
    "EMAIL": SensitivityLevel.ANONYMIZE,
    "BR_NUMBER": SensitivityLevel.MINIMIZE,
    "MONEY": SensitivityLevel.MINIMIZE,
}
"""How sensitive a document becomes because of what is in it.

HKID is LOCAL_ONLY rather than ANONYMIZE deliberately. An identity card number is the
single value that most clearly identifies a person in Hong Kong, and the default posture
for it should be that it does not leave the machine at all, not that it leaves in a
disguised form. A customer can relax that with a policy rule; they should not have to
tighten it.

This mapping is a v0 and belongs in configuration once the corpus tells us the real
categories — see the handover, Section 9.
"""


@dataclass(frozen=True)
class RedactionResult:
    """What came out of the gateway.

    ``placeholder_map`` is deliberately part of this object and deliberately not
    serialisable. It goes to the restorer and nowhere else.
    """

    classification: ContentClassification
    redacted_text: str
    placeholder_map: PlaceholderMap
    detections: tuple[Detection, ...]

    @property
    def tokens(self) -> list[str]:
        return list(self.placeholder_map.tokens())


class PrivacyGateway:
    def __init__(self, detectors: Sequence[Detector] = ALL_DETECTORS) -> None:
        self._detectors = detectors

    def classify(
        self, text: str, *, content_id: str
    ) -> tuple[ContentClassification, list[Detection]]:
        """Detect entities and derive an overall sensitivity.

        The document takes the sensitivity of its most sensitive component. A document is
        not less sensitive because most of it is harmless.
        """
        detections = detect_all(text, self._detectors)
        level = SensitivityLevel.PUBLIC
        for d in detections:
            level = max(level, SENSITIVITY_BY_ENTITY.get(d.entity_type, SensitivityLevel.MINIMIZE))

        entities = [
            DetectedEntity(
                entity_type=d.entity_type,
                start=d.start,
                end=d.end,
                confidence=d.confidence,
                method=DetectionMethod.RULE,
            )
            for d in detections
        ]
        classification = ContentClassification(
            content_id=content_id, sensitivity=level, entities=entities
        )
        return classification, detections

    def redact(self, text: str, *, content_id: str) -> RedactionResult:
        """Replace detected values with stable placeholders."""
        classification, detections = self.classify(text, content_id=content_id)
        mapping = PlaceholderMap()

        # Replace from the end so earlier offsets stay valid.
        out = text
        annotated: list[DetectedEntity] = list(classification.entities)
        for index in range(len(detections) - 1, -1, -1):
            d = detections[index]
            token = mapping.token_for(d.text, d.entity_type)
            out = out[: d.start] + token + out[d.end :]
            annotated[index] = annotated[index].model_copy(update={"placeholder_token": token})

        classification = classification.model_copy(update={"entities": annotated})
        return RedactionResult(
            classification=classification,
            redacted_text=out,
            placeholder_map=mapping,
            detections=tuple(detections),
        )

    @staticmethod
    def restore(text: str, mapping: PlaceholderMap) -> str:
        """Put the real values back. Local, always."""
        return mapping.restore(text)
