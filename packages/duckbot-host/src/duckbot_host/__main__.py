"""``python -m duckbot_host``.

A shim. The real entry point is :mod:`duckbot_host.cli`, which uses absolute imports so
that the same code works when PyInstaller runs it as a top-level script.
"""

from __future__ import annotations

from duckbot_host.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
