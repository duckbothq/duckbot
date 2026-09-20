#!/usr/bin/env python3
"""Fail the build if a dependency carries a licence Duckbot cannot ship.

Duckbot's core is Apache-2.0. A permissive licence cannot contain copyleft code, so an
AGPL component inside this tree is a licence violation that becomes visible to everyone
the moment the repository is public. This gate is the cheapest version of a problem that
is expensive at every later stage.

Policy lives in ``duckbot_dependency_licence_register.md``. Two rules matter here:

* The check covers the **resolved environment**, which includes transitive dependencies.
  A direct-only scan misses the case the register documents: a permissively licensed
  wrapper around a copyleft binary is still a copyleft dependency.
* An unrecognised licence **fails**. Fail-open would make this gate decorative, and a
  gate everyone has learned to ignore is worse than no gate at all.

Usage::

    python scripts/check_licences.py                       # check, exit 1 on violation
    python scripts/check_licences.py --write-notices FILE  # also emit THIRD_PARTY_LICENSES
    python scripts/check_licences.py --cargo-manifest packages/duckbot-shell/src-tauri/Cargo.toml
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

# Permissive, and safe inside an Apache-2.0 distribution.
ALLOWED = {
    "apache-2.0",
    "apache software license",
    "mit",
    "mit license",
    "bsd",
    "bsd-2-clause",
    "bsd-3-clause",
    "bsd license",
    "isc",
    "isc license",
    "python software foundation license",
    "psf-2.0",
    "mpl-2.0",  # file-level copyleft; acceptable while the file is unmodified
    "mozilla public license 2.0",
    "unlicense",
    "public domain",
    "cc0-1.0",
    "0bsd",
    "mit-0",
    "zlib",
    "unicode-3.0",
    "apache-2.0 with llvm-exception",
    "apache-2.0 or mit",
    "mit or apache-2.0",
}

# Substrings that are always a hard failure, whatever else the metadata says.
DENIED_PATTERNS = [
    r"\bagpl\b",
    r"affero",
    r"\bsspl\b",
    r"server side public license",
    r"business source",
    r"\bbsl\b",
    r"elastic license",
    r"commons clause",
    r"polyform",
    r"non-?commercial",
    r"proprietary",
    r"all rights reserved",
]

# GPL and LGPL are deliberately not in either list. GPL is a failure in this tree, and
# LGPL is a decision about linking that a human has to make — see the register, Section 2.
DECISION_REQUIRED_PATTERNS = [r"\blgpl\b", r"lesser general public"]
GPL_PATTERNS = [r"\bgpl", r"general public license"]

# Packages whose metadata is known to be wrong or absent, with the verified licence and
# the reason. Every entry is a deliberate, reviewable exception — not a way to silence
# the gate. Adding one requires checking the project's actual LICENSE file.
KNOWN_OVERRIDES: dict[str, str] = {
    # "example-package": "MIT  # metadata omits the field; LICENSE file checked 2026-09-18",
}

# Cargo packages with a reviewed choice from an OR expression. ``r-efi`` offers MIT,
# Apache-2.0, or LGPL-2.1-or-later; Duckbot takes the MIT alternative. Recording that
# choice avoids silently treating an LGPL static-linking question as resolved by a regex.
CARGO_KNOWN_OVERRIDES: dict[tuple[str, str], str] = {
    (
        "r-efi",
        "5.3.0",
    ): "MIT  # permissive alternative selected; crate metadata checked 2026-09-20",
    (
        "r-efi",
        "6.0.0",
    ): "MIT  # permissive alternative selected; crate metadata checked 2026-09-20",
}


@dataclass(frozen=True)
class Finding:
    name: str
    version: str
    licence: str
    reason: str


def _normalise(raw: str) -> str:
    """Lower-case, collapse whitespace, and drop a trailing parenthetical.

    Trove classifiers routinely read "Mozilla Public License 2.0 (MPL 2.0)", where the
    bracket restates the same licence. Keeping it would force an entry in ALLOWED for
    every cosmetic variant.
    """
    text = re.sub(r"\s+", " ", raw.strip().lower().rstrip("."))
    text = re.sub(r"\s+\([^)]*\)\s*$", "", text).strip()
    return text


def _strip_outer_parentheses(value: str) -> str:
    text = value.strip()
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        closes_at_end = False
        for index, character in enumerate(text):
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    closes_at_end = index == len(text) - 1
                    break
        if not closes_at_end:
            break
        text = text[1:-1].strip()
    return text


def _split_top_level(value: str, separator: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    index = 0
    while index < len(value):
        character = value[index]
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif depth == 0 and value.startswith(separator, index):
            parts.append(value[start:index].strip())
            index += len(separator)
            start = index
            continue
        index += 1
    parts.append(value[start:].strip())
    return parts


def _expression_is_allowed(value: str) -> bool:
    expression = _strip_outer_parentheses(value)
    if expression in ALLOWED:
        return True
    alternatives = _split_top_level(expression, " or ")
    if len(alternatives) > 1:
        return any(_expression_is_allowed(term) for term in alternatives)
    requirements = _split_top_level(expression, " and ")
    if len(requirements) > 1:
        return all(_expression_is_allowed(term) for term in requirements)
    return False


def _licence_for(dist: metadata.Distribution) -> str:
    """Best available licence string for a distribution.

    Checks, in order: a deliberate override, PEP 639 ``License-Expression``, the legacy
    ``License`` field, then the Trove classifiers.
    """
    name = dist.metadata["Name"] or "unknown"
    if name in KNOWN_OVERRIDES:
        return KNOWN_OVERRIDES[name].split("#")[0].strip()

    expression = dist.metadata.get("License-Expression")
    if expression:
        return str(expression)

    legacy = dist.metadata.get("License")
    if legacy and len(legacy) < 200 and "\n" not in legacy:
        return str(legacy)

    classifiers = [
        c
        for c in dist.metadata.get_all("Classifier") or []
        if c.startswith("License ::")
    ]
    if classifiers:
        return "; ".join(c.split(" :: ")[-1] for c in classifiers)

    if legacy:
        return "(full licence text in metadata)"
    return "UNKNOWN"


def _classify(licence: str) -> tuple[bool, str]:
    """Return ``(ok, reason)`` for one licence string."""
    norm = _normalise(licence)
    # Several established crates still publish legacy ``MIT/Apache-2.0`` metadata.
    # Cargo treats that as a choice, so normalise it to the equivalent SPDX-style OR.
    norm = re.sub(r"\s*/\s*", " or ", norm)
    norm = re.sub(r"\s*;\s*", " and ", norm)

    for pattern in DENIED_PATTERNS:
        if re.search(pattern, norm):
            # A dual licence such as "AGPL-3.0 OR MIT" does legally let us take the
            # permissive alternative. It still stops here rather than passing silently:
            # the choice is a decision someone should make and record, not one a regex
            # should make on their behalf.
            if " or " in norm and _expression_is_allowed(norm):
                return False, (
                    "dual-licensed with a denied family; the permissive alternative may "
                    "be usable, but record that choice in KNOWN_OVERRIDES rather than "
                    "relying on this gate to infer it"
                )
            return False, f"denied licence family (matched /{pattern}/)"

    for pattern in DECISION_REQUIRED_PATTERNS:
        if re.search(pattern, norm):
            return (
                False,
                "LGPL requires a human linking decision; see the register, Section 2",
            )

    if _expression_is_allowed(norm):
        return True, "allowed (licence or permissive SPDX expression)"

    for pattern in GPL_PATTERNS:
        if re.search(pattern, norm):
            return False, "GPL family is not compatible with an Apache-2.0 distribution"

    return (
        False,
        "unrecognised licence; add it to ALLOWED or KNOWN_OVERRIDES after checking",
    )


def scan() -> tuple[list[Finding], list[tuple[str, str, str]]]:
    failures: list[Finding] = []
    inventory: list[tuple[str, str, str]] = []

    for dist in sorted(
        metadata.distributions(), key=lambda d: (d.metadata["Name"] or "").lower()
    ):
        name = dist.metadata["Name"]
        if not name:
            continue
        version = dist.version or "?"
        licence = _licence_for(dist)
        inventory.append((name, version, licence))

        ok, reason = _classify(licence)
        if not ok:
            failures.append(Finding(name, version, licence, reason))

    return failures, inventory


def scan_cargo(manifest: Path) -> tuple[list[Finding], list[tuple[str, str, str]]]:
    """Scan every crate in the manifest's locked, resolved dependency graph."""
    try:
        completed = subprocess.run(
            [
                "cargo",
                "metadata",
                "--format-version",
                "1",
                "--locked",
                "--manifest-path",
                str(manifest.resolve()),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )
        payload: Any = json.loads(completed.stdout)
    except (
        OSError,
        subprocess.CalledProcessError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise RuntimeError("could not read locked Cargo dependency metadata") from exc

    packages = payload.get("packages") if isinstance(payload, dict) else None
    if not isinstance(packages, list):
        raise TypeError("Cargo metadata did not contain a package list")

    failures: list[Finding] = []
    inventory: list[tuple[str, str, str]] = []
    for package in sorted(
        packages,
        key=lambda item: (
            str(item.get("name", "")).casefold(),
            str(item.get("version", "")),
        ),
    ):
        if not isinstance(package, dict):
            raise TypeError("Cargo metadata contained an invalid package")
        name = str(package.get("name") or "unknown")
        version = str(package.get("version") or "?")
        raw_licence = CARGO_KNOWN_OVERRIDES.get((name, version)) or str(
            package.get("license") or "UNKNOWN"
        )
        licence = raw_licence.split("#")[0].strip()
        inventory.append((name, version, licence))
        ok, reason = _classify(licence)
        if not ok:
            failures.append(Finding(name, version, licence, f"Cargo crate: {reason}"))
    return failures, inventory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-notices", metavar="PATH")
    parser.add_argument("--cargo-manifest", type=Path)
    args = parser.parse_args()

    failures, inventory = scan()
    cargo_inventory: list[tuple[str, str, str]] = []
    if args.cargo_manifest:
        cargo_failures, cargo_inventory = scan_cargo(args.cargo_manifest)
        failures.extend(cargo_failures)

    if args.write_notices:
        with open(args.write_notices, "w", encoding="utf-8") as fh:
            fh.write("Third-party dependencies bundled with or required by Duckbot.\n")
            fh.write("Generated by scripts/check_licences.py. Do not edit by hand.\n\n")
            fh.write("Python distributions\n")
            fh.write("====================\n\n")
            fh.writelines(
                f"{name} {version}\n    {licence}\n\n"
                for name, version, licence in inventory
            )
            if cargo_inventory:
                fh.write("Rust crates (locked dependency graph)\n")
                fh.write("=====================================\n\n")
                fh.writelines(
                    f"{name} {version}\n    {licence}\n\n"
                    for name, version, licence in cargo_inventory
                )
        print(
            f"wrote {args.write_notices} "
            f"({len(inventory)} Python distributions, {len(cargo_inventory)} Rust crates)"
        )

    print(f"checked {len(inventory)} distributions in the resolved environment")
    if args.cargo_manifest:
        print(f"checked {len(cargo_inventory)} crates in the locked Cargo graph")

    if failures:
        print("\nLICENCE GATE FAILED\n", file=sys.stderr)
        for f in failures:
            print(f"  {f.name} {f.version}", file=sys.stderr)
            print(f"      licence: {f.licence}", file=sys.stderr)
            print(f"      reason:  {f.reason}\n", file=sys.stderr)
        print(
            "Duckbot's core is Apache-2.0 and cannot contain copyleft code.\n"
            "Either replace the dependency, isolate it as a separately installed\n"
            "plugin in its own process, or — if the licence is fine and the metadata\n"
            "is simply wrong — add a reviewed entry to KNOWN_OVERRIDES with the date\n"
            "the project's LICENSE file was checked.\n"
            "See duckbot_dependency_licence_register.md.",
            file=sys.stderr,
        )
        return 1

    print("licence gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
