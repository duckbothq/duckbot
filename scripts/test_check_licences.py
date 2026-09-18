"""Tests for the licence gate itself.

A gate that never fails is indistinguishable from a gate that is broken. These cases
are the difference, and they run in CI alongside everything else.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from check_licences import _classify, _normalise  # noqa: E402


@pytest.mark.parametrize(
    "licence",
    [
        "AGPL-3.0",
        "AGPL-3.0-or-later",
        "GNU Affero General Public License v3",
        "SSPL-1.0",
        "Server Side Public License",
        "Business Source License 1.1",
        "BSL-1.1",
        "Elastic License 2.0",
        "MIT with Commons Clause",
        "PolyForm Noncommercial",
        "Non-Commercial Use Only",
        "Proprietary",
        "All Rights Reserved",
    ],
)
def test_denied_families_fail(licence: str) -> None:
    ok, _ = _classify(licence)
    assert ok is False, f"{licence} must not pass the gate"


@pytest.mark.parametrize("licence", ["LGPL-3.0", "GNU Lesser General Public License v3"])
def test_lgpl_requires_a_human_decision(licence: str) -> None:
    ok, reason = _classify(licence)
    assert ok is False
    assert "linking decision" in reason


@pytest.mark.parametrize(
    "licence", ["GPL-3.0", "GPL-2.0-only", "GNU General Public License v2"]
)
def test_gpl_fails(licence: str) -> None:
    ok, reason = _classify(licence)
    assert ok is False
    assert "GPL family" in reason


@pytest.mark.parametrize(
    "licence",
    [
        "MIT",
        "MIT License",
        "Apache-2.0",
        "Apache Software License",
        "BSD-3-Clause",
        "ISC",
        "Mozilla Public License 2.0 (MPL 2.0)",
        "Apache-2.0 OR BSD-2-Clause",
        "MIT OR Apache-2.0",
        "Python Software Foundation License",
    ],
)
def test_permissive_licences_pass(licence: str) -> None:
    ok, reason = _classify(licence)
    assert ok is True, f"{licence} should pass but was rejected: {reason}"


def test_unknown_licence_fails_closed() -> None:
    """Fail-closed is deliberate. A gate that waves through what it does not recognise
    is decorative, and the unrecognised case is exactly where a surprise lives."""
    ok, reason = _classify("Some Licence Nobody Has Heard Of")
    assert ok is False
    assert "unrecognised" in reason


def test_or_expression_needs_only_one_permissive_alternative() -> None:
    ok, reason = _classify("AGPL-3.0 OR MIT")
    # Denied families are checked first and win outright: we will not rely on being
    # offered a choice by a project whose headline licence is AGPL.
    assert ok is False, reason


def test_and_expression_requires_every_term() -> None:
    ok, _ = _classify("MIT AND AGPL-3.0")
    assert ok is False


def test_normalise_strips_trailing_parenthetical() -> None:
    assert _normalise("Mozilla Public License 2.0 (MPL 2.0)") == "mozilla public license 2.0"
