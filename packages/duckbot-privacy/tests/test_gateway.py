"""Classify, redact, restore — and the structural guarantees around them.

The tests that matter most here are the negative ones: that the redacted text contains
none of the original values, and that the placeholder map cannot be serialised. Those
are the promises the product is sold on.

Every value in this file is invented.
"""

from __future__ import annotations

import json

import pytest
from duckbot_schemas import DetectionMethod, PlaceholderMap, SensitivityLevel
from pydantic import BaseModel

from duckbot_privacy import PrivacyGateway
from duckbot_privacy.gateway import SENSITIVITY_BY_ENTITY

HKID = "A123456(3)"
PHONE = "9876 5432"
EMAIL = "ka.man@example.com.hk"

DOCUMENT = (
    f"客戶陳嘉雯，身份證 {HKID}，電話 {PHONE}，電郵 {EMAIL}。"
    f"請於下週前回覆陳嘉雯，同一電話 {PHONE}。"
)


@pytest.fixture
def gateway() -> PrivacyGateway:
    return PrivacyGateway()


class TestClassify:
    def test_entities_are_reported(self, gateway: PrivacyGateway) -> None:
        classification, detections = gateway.classify(DOCUMENT, content_id="doc-1")
        assert {e.entity_type for e in classification.entities} >= {"HKID", "PHONE", "EMAIL"}
        assert len(classification.entities) == len(detections)

    def test_the_document_takes_its_most_sensitive_component(self, gateway: PrivacyGateway) -> None:
        classification, _ = gateway.classify(DOCUMENT, content_id="doc-1")
        assert classification.sensitivity is SensitivityLevel.LOCAL_ONLY

    def test_an_hkid_alone_is_local_only(self, gateway: PrivacyGateway) -> None:
        """Not ANONYMIZE. An identity card number should default to staying put."""
        classification, _ = gateway.classify(f"身份證 {HKID}", content_id="doc-2")
        assert classification.sensitivity is SensitivityLevel.LOCAL_ONLY
        assert SENSITIVITY_BY_ENTITY["HKID"] is SensitivityLevel.LOCAL_ONLY

    def test_clean_content_is_public(self, gateway: PrivacyGateway) -> None:
        classification, _ = gateway.classify("本季度營運開支下降。", content_id="doc-3")
        assert classification.sensitivity is SensitivityLevel.PUBLIC
        assert classification.entities == []

    def test_detections_are_marked_as_rule_based(self, gateway: PrivacyGateway) -> None:
        classification, _ = gateway.classify(DOCUMENT, content_id="doc-1")
        assert all(e.method is DetectionMethod.RULE for e in classification.entities)

    def test_offsets_address_the_original_text(self, gateway: PrivacyGateway) -> None:
        classification, _ = gateway.classify(DOCUMENT, content_id="doc-1")
        for entity in classification.entities:
            assert DOCUMENT[entity.start : entity.end]


class TestRedact:
    def test_no_original_value_survives(self, gateway: PrivacyGateway) -> None:
        """The one assertion the whole package exists for."""
        result = gateway.redact(DOCUMENT, content_id="doc-1")
        for value in (HKID, PHONE, EMAIL, "陳嘉雯"):
            assert value not in result.redacted_text

    def test_surrounding_text_is_untouched(self, gateway: PrivacyGateway) -> None:
        result = gateway.redact(DOCUMENT, content_id="doc-1")
        assert "請於下週前回覆" in result.redacted_text

    def test_a_repeated_value_gets_the_same_token(self, gateway: PrivacyGateway) -> None:
        """Otherwise the model loses track of who is who."""
        result = gateway.redact(DOCUMENT, content_id="doc-1")
        phone_tokens = {
            e.placeholder_token for e in result.classification.entities if e.entity_type == "PHONE"
        }
        assert len(phone_tokens) == 1

    def test_tokens_name_their_entity_type(self, gateway: PrivacyGateway) -> None:
        result = gateway.redact(f"身份證 {HKID}", content_id="doc-2")
        (token,) = result.tokens
        assert token.startswith("[HKID_")

    def test_every_entity_carries_its_token(self, gateway: PrivacyGateway) -> None:
        result = gateway.redact(DOCUMENT, content_id="doc-1")
        assert result.classification.entities
        for entity in result.classification.entities:
            assert entity.placeholder_token
            assert entity.placeholder_token in result.redacted_text

    def test_clean_content_is_returned_unchanged(self, gateway: PrivacyGateway) -> None:
        text = "本季度營運開支下降。"
        result = gateway.redact(text, content_id="doc-3")
        assert result.redacted_text == text
        assert len(result.placeholder_map) == 0


class TestRestore:
    def test_the_round_trip_is_exact(self, gateway: PrivacyGateway) -> None:
        result = gateway.redact(DOCUMENT, content_id="doc-1")
        assert gateway.restore(result.redacted_text, result.placeholder_map) == DOCUMENT

    def test_a_model_reply_is_restored_in_place(self, gateway: PrivacyGateway) -> None:
        """The realistic case: the tokens come back inside text we never sent."""
        result = gateway.redact(DOCUMENT, content_id="doc-1")
        (phone_token,) = {
            e.placeholder_token for e in result.classification.entities if e.entity_type == "PHONE"
        }
        assert phone_token is not None
        reply = f"建議先致電 {phone_token} 確認。"
        assert gateway.restore(reply, result.placeholder_map) == f"建議先致電 {PHONE} 確認。"

    def test_an_unknown_token_is_left_alone(self, gateway: PrivacyGateway) -> None:
        result = gateway.redact(DOCUMENT, content_id="doc-1")
        assert gateway.restore("[HKID_zzzzzz]", result.placeholder_map) == "[HKID_zzzzzz]"


class TestThePlaceholderMapCannotLeak:
    """These assert the type-level guarantee, not a convention."""

    def test_it_is_not_a_pydantic_model(self) -> None:
        assert not issubclass(PlaceholderMap, BaseModel)
        assert not hasattr(PlaceholderMap, "model_dump")

    def test_it_cannot_be_json_encoded(self, gateway: PrivacyGateway) -> None:
        result = gateway.redact(DOCUMENT, content_id="doc-1")
        with pytest.raises(TypeError):
            json.dumps(result.placeholder_map)  # type: ignore[arg-type]

    def test_its_repr_withholds_the_values(self, gateway: PrivacyGateway) -> None:
        result = gateway.redact(DOCUMENT, content_id="doc-1")
        for rendering in (repr(result.placeholder_map), str(result.placeholder_map)):
            assert HKID not in rendering
            assert PHONE not in rendering

    def test_the_classification_carries_no_raw_values(self, gateway: PrivacyGateway) -> None:
        """A classification is safe to log. That is what makes the audit trail possible."""
        result = gateway.redact(DOCUMENT, content_id="doc-1")
        dumped = result.classification.model_dump_json()
        for value in (HKID, PHONE, EMAIL, "陳嘉雯"):
            assert value not in dumped
