"""The entry point, and the two things it fixes before anything else runs.

**Absolute imports.** A frozen executable runs its entry script as a top-level module, so
a relative import here — ``from .server import serve`` — raises ``ImportError: attempted
relative import with no known parent package`` the moment the binary starts, while
working perfectly under ``python -m duckbot_host``. The user sees a window that never
finishes loading.

**UTF-8 on the pipe, explicitly.** This is the more dangerous of the two, because it does
not crash.

Python binds standard input and output to the platform's preferred encoding. On Linux
that is UTF-8 and everything works. On Windows it is the ANSI code page — cp1252 on a
Western install, cp950 on a Traditional Chinese one — and then a single-byte codec
decodes our UTF-8 bytes into mojibake, the detectors run against that mojibake, and the
re-encoded output goes back out as the *same bytes*. The text on screen looks correct.
Nothing raises. And Chinese name detection has silently stopped working, while the
offsets reported for everything else are wrong because the mojibake is longer than the
text it came from.

Measured, on the same input: UTF-8 stdio finds PERSON_NAME at 2–5, HKID at 10–20; cp1252
stdio finds no PERSON_NAME at all and puts HKID at 28–38. For a product whose whole claim
is that it keeps Hong Kong personal data out of a prompt, that is the worst class of bug
there is — it fails open and says nothing.

So the streams are bound to UTF-8 here, from the raw byte buffers, regardless of what the
platform would have chosen. ``newline="\\n"`` also stops Windows translating the
line-delimited protocol's newlines to CRLF.
"""

from __future__ import annotations

import io
import sys
from typing import TextIO

from duckbot_host.handlers import Session
from duckbot_host.server import serve

ENCODING = "utf-8"


def _rebind(stream: TextIO, **kwargs: object) -> TextIO:
    """Re-bind a text stream to UTF-8, from its underlying bytes where possible.

    A stream with no byte buffer — a ``StringIO`` in a test, an embedded interpreter's
    stdio — is already text somebody else chose the encoding for, so it is returned
    untouched rather than forced. There is nothing to decode at that point.
    """
    buffer = getattr(stream, "buffer", None)
    if buffer is None:
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:  # pragma: no cover - platform dependent
            reconfigure(encoding=ENCODING, newline="\n")
        return stream
    return io.TextIOWrapper(buffer, encoding=ENCODING, errors="strict", newline="\n", **kwargs)  # type: ignore[arg-type]


def utf8_reader(stream: TextIO) -> TextIO:
    return _rebind(stream)


def utf8_writer(stream: TextIO) -> TextIO:
    return _rebind(stream, write_through=True)


def main() -> int:
    protocol_in = utf8_reader(sys.stdin)
    protocol_out = utf8_writer(sys.stdout)
    # Anything that prints from here on — ours, a dependency's, a warning — goes to
    # stderr, where the shell can log it without it corrupting the wire.
    sys.stdout = sys.stderr
    serve(protocol_in, protocol_out, session=Session())
    return 0
