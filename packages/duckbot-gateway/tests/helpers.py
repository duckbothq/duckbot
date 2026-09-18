"""Small builders shared by the tests."""

from __future__ import annotations

from duckbot_schemas import (
    ContentClassification,
    DetectedEntity,
    DetectionMethod,
    SensitivityLevel,
)


def classification(
    level: SensitivityLevel, *, content_id: str = "c1", entity_type: str = "PERSON_NAME"
) -> ContentClassification:
    """A classification at a given level, with one entity unless it is PUBLIC."""
    entities = (
        []
        if level is SensitivityLevel.PUBLIC
        else [
            DetectedEntity(
                entity_type=entity_type,
                start=0,
                end=3,
                confidence=0.9,
                method=DetectionMethod.RULE,
                placeholder_token="[PERSON_NAME_aaaaaa]",
            )
        ]
    )
    return ContentClassification(content_id=content_id, sensitivity=level, entities=entities)
