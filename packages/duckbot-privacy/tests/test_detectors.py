"""The rule layer, including what it deliberately does not do.

Several tests below assert a *miss*. They are not describing a defect: they pin the
boundary between what rules can do and what the local model is for, so that somebody
widening a pattern has to decide to change the boundary rather than drift across it.

Every name, number and address in this file is invented.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from duckbot_privacy.detectors import (
    HK_SURNAMES,
    Detection,
    detect_all,
    detect_br_number,
    detect_email,
    detect_hkid,
    detect_money,
    detect_person_name,
    detect_phone,
    resolve_overlaps,
)


def types_found(detections: list[Detection]) -> set[str]:
    return {d.entity_type for d in detections}


def texts_of(detections: list[Detection], entity_type: str) -> list[str]:
    return [d.text for d in detections if d.entity_type == entity_type]


class TestHkid:
    def test_valid_hkid_is_detected(self) -> None:
        found = detect_hkid("身份證號碼 A123456(3)")
        assert texts_of(found, "HKID") == ["A123456(3)"]
        assert found[0].confidence >= 0.95

    def test_invalid_check_digit_is_not_detected(self) -> None:
        assert detect_hkid("參考 A123456(9)") == []


class TestPhone:
    @pytest.mark.parametrize(
        "text",
        [
            "電話 9876 5432",
            "電話 98765432",
            "電話 +852 2345 6789",
            "電話 852-3456-7890",
            "Tel: 6123-4567",
        ],
    )
    def test_hong_kong_numbers_are_detected(self, text: str) -> None:
        assert detect_phone(text), text

    def test_offsets_point_at_the_match(self) -> None:
        text = "請致電 9876 5432 聯絡"
        (d,) = detect_phone(text)
        assert text[d.start : d.end] == d.text

    @pytest.mark.parametrize("text", ["編號 1234 5678", "年份 1997 2047"])
    def test_numbers_that_cannot_be_hong_kong_numbers_are_skipped(self, text: str) -> None:
        """Local numbers begin 2, 3, 5, 6 or 9. Anything else is some other number."""
        assert detect_phone(text) == []


class TestEmail:
    def test_addresses_are_detected(self) -> None:
        found = detect_email("寄到 jane.wong+hr@example.com.hk 同 ops@example.net")
        assert texts_of(found, "EMAIL") == ["jane.wong+hr@example.com.hk", "ops@example.net"]

    def test_bare_domain_is_not_an_address(self) -> None:
        assert detect_email("網站 example.com.hk") == []


class TestBusinessRegistration:
    def test_br_number_with_branch_code_is_detected(self) -> None:
        found = detect_br_number("商業登記號碼 12345678-000")
        assert texts_of(found, "BR_NUMBER") == ["12345678-000"]

    def test_confidence_is_moderate_because_the_shape_is_common(self) -> None:
        (d,) = detect_br_number("BR 87654321 001")
        assert d.confidence < 0.9


class TestMoney:
    def test_amounts_are_detected(self) -> None:
        found = detect_money("報價 HK$128,500.00，訂金 $20,000")
        assert texts_of(found, "MONEY") == ["HK$128,500.00", "$20,000"]

    def test_salary_context_changes_the_entity_type(self) -> None:
        """A salary is materially more sensitive than a quotation total."""
        found = detect_money("月薪 HK$45,000")
        assert texts_of(found, "SALARY") == ["HK$45,000"]
        assert texts_of(found, "MONEY") == []

    def test_english_salary_context_also_counts(self) -> None:
        assert texts_of(detect_money("Monthly salary of HKD 52,000"), "SALARY")


class TestPersonName:
    def test_role_prefix_anchors_a_chinese_name(self) -> None:
        assert texts_of(detect_person_name("負責人陳嘉雯已確認"), "PERSON_NAME") == ["陳嘉雯"]

    def test_a_connector_between_role_and_name_is_tolerated(self) -> None:
        assert texts_of(detect_person_name("聯絡人為李國強"), "PERSON_NAME") == ["李國強"]

    def test_title_suffix_anchors_a_chinese_name(self) -> None:
        assert texts_of(detect_person_name("由黃雅詩經理跟進"), "PERSON_NAME") == ["黃雅詩"]

    def test_explicit_label_anchors_a_chinese_name(self) -> None:
        assert texts_of(detect_person_name("姓名：周家豪"), "PERSON_NAME") == ["周家豪"]

    def test_romanised_name_with_capitalised_surname(self) -> None:
        assert texts_of(detect_person_name("Please copy CHAN Ka Man."), "PERSON_NAME") == [
            "CHAN Ka Man"
        ]

    def test_an_unanchored_chinese_name_is_missed_on_purpose(self) -> None:
        """This is the local model's job, not the rule layer's.

        Widening the pattern to catch it would also match 張開, 陳述, 李子 and a great deal
        of other ordinary prose. See the module docstring in ``detectors.py``.
        """
        assert detect_person_name("就張明輝客戶的年度審計") == []

    def test_ordinary_prose_is_not_mistaken_for_a_name(self) -> None:
        assert detect_person_name("請張開檔案並陳述理由") == []

    @pytest.mark.parametrize("char", "高文方石白毛江史田常武易湯")
    def test_ambiguous_surname_characters_are_excluded(self, char: str) -> None:
        """Deliberate recall/precision trade. See the comment above ``HK_SURNAMES``."""
        assert char not in HK_SURNAMES


class TestOverlapResolution:
    def test_the_longer_span_wins(self) -> None:
        long_span = Detection("HKID", 0, 10, "A123456(3)", 0.99)
        fragment = Detection("BR_NUMBER", 1, 7, "123456", 0.7)
        assert resolve_overlaps([fragment, long_span]) == [long_span]

    def test_equal_length_is_settled_by_confidence(self) -> None:
        strong = Detection("EMAIL", 0, 5, "a@b.c", 0.98)
        weak = Detection("PERSON_NAME", 0, 5, "a@b.c", 0.55)
        assert resolve_overlaps([weak, strong]) == [strong]

    def test_results_come_back_in_document_order(self) -> None:
        a = Detection("PHONE", 20, 28, "98765432", 0.9)
        b = Detection("EMAIL", 0, 5, "a@b.c", 0.98)
        assert [d.start for d in resolve_overlaps([a, b])] == [0, 20]

    def test_non_overlapping_detections_are_all_kept(self) -> None:
        a = Detection("PHONE", 0, 8, "98765432", 0.9)
        b = Detection("EMAIL", 10, 15, "a@b.c", 0.98)
        assert len(resolve_overlaps([a, b])) == 2


class TestDetectAll:
    TEXT = (
        "客戶陳嘉雯，身份證 A123456(3)，電話 9876 5432，"
        "電郵 ka.man@example.com.hk，商業登記 12345678-000，月薪 HK$45,000。"
    )

    def test_every_entity_type_is_found(self) -> None:
        found = detect_all(self.TEXT)
        assert types_found(found) == {
            "PERSON_NAME",
            "HKID",
            "PHONE",
            "EMAIL",
            "BR_NUMBER",
            "SALARY",
        }

    def test_nothing_overlaps_in_the_result(self) -> None:
        found = detect_all(self.TEXT)
        for earlier, later in pairwise(found):
            assert earlier.end <= later.start

    def test_every_offset_matches_the_source_text(self) -> None:
        for d in detect_all(self.TEXT):
            assert self.TEXT[d.start : d.end] == d.text

    def test_the_detector_set_can_be_narrowed(self) -> None:
        found = detect_all(self.TEXT, [detect_hkid])
        assert types_found(found) == {"HKID"}

    def test_clean_text_produces_nothing(self) -> None:
        assert detect_all("本季度的營運開支較上季下降。") == []


class TestValuePropagation:
    """Once a value is identified, every occurrence of it goes.

    The bug this closes: a name is introduced as 客戶陳嘉雯 and then used bare for the rest
    of the document, so only the first occurrence carries an anchor and the rest leak out
    of the very document in which the name was already recognised.
    """

    def test_a_bare_repeat_of_an_anchored_name_is_caught(self) -> None:
        text = "客戶陳嘉雯已確認。請回覆陳嘉雯，並抄送陳嘉雯的上司。"
        found = [d for d in detect_all(text) if d.entity_type == "PERSON_NAME"]
        assert len(found) == 3
        assert {d.text for d in found} == {"陳嘉雯"}

    def test_a_repeated_structured_value_is_caught_once_per_occurrence(self) -> None:
        text = "電話 9876 5432，如未能接通請再致電 9876 5432。"
        assert len(detect_phone(text)) == len(
            [d for d in detect_all(text) if d.entity_type == "PHONE"]
        )

    def test_propagation_does_not_reach_across_documents(self) -> None:
        """Each call sees one document. A value learned elsewhere is not carried in."""
        assert detect_all("Serial number K470285 has no check digit.") == []

    def test_short_values_are_not_propagated(self) -> None:
        """A two-character name is also an ordinary word; propagating it redacts prose."""
        text = "客戶張開已確認。請張開附件並陳述理由。"
        found = [d for d in detect_all(text) if d.entity_type == "PERSON_NAME"]
        assert len(found) == 1, "only the anchored occurrence should be redacted"

    def test_nothing_new_is_invented(self) -> None:
        """Propagation re-uses a decision; it never widens a pattern."""
        text = "客戶陳嘉雯已確認。"
        assert len(detect_all(text)) == 1
