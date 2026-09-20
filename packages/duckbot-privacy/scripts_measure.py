"""Print the recall report for a corpus file.

    python scripts_measure.py corpus/hk_business_v1.json

This number is the product. Run it whenever detection changes, and put the result in the
pull request — "improved detection" without a before and after is an opinion.
"""

from __future__ import annotations

import sys
from pathlib import Path

from duckbot_privacy.corpus import load_documents
from duckbot_privacy.recall import score


def _configure_stdout() -> None:
    """Keep Traditional Chinese reports independent of the Windows code page."""
    sys.stdout.reconfigure(encoding="utf-8", errors="strict", newline="\n")


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path("corpus/hk_business_v1.json")
    documents = load_documents(path)
    result = score(documents)
    print(f"corpus: {path}  ({len(documents)} documents)\n")
    print(result.format_report())
    return 0


if __name__ == "__main__":
    _configure_stdout()
    raise SystemExit(main(sys.argv))
