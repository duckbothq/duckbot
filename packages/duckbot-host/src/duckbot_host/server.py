"""The loop.

One subtlety is load-bearing enough to be the reason this file is separate: **standard
output belongs to the protocol and to nothing else.** A stray ``print`` anywhere in the
Python — in our code, in a dependency, in a deprecation warning — writes a line the shell
will try to parse as a response, and the connection is then broken in a way that looks
like a mysterious hang rather than like a print statement.

So the server is handed the stream it writes to, and :mod:`duckbot_host.__main__`
takes the real stdout away from the rest of the process before anything else runs. That
is a two-line precaution against a class of bug that is otherwise found at three in the
morning by somebody bisecting a dependency upgrade.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, TextIO

from .handlers import Session, build_handlers, dispatch
from .protocol import INTERNAL_ERROR, Request, Response, error, parse


def handle_line(handlers: dict[str, Any], line: str) -> Response | None:
    """One line in, at most one line out. Blank lines are ignored, not errors."""
    if not line.strip():
        return None
    parsed = parse(line)
    if isinstance(parsed, Response):
        return parsed
    if parsed.id is None:
        # A request with no id is a notification: act on it, answer nothing.
        dispatch(handlers, parsed)
        return None
    return dispatch(handlers, parsed)


def serve(lines: Iterable[str], out: TextIO, *, session: Session | None = None) -> None:
    """Read requests, write responses, until the input ends.

    The shell closing the pipe is how this process is asked to stop, which means there is
    no shutdown method to get wrong and no way for the host to outlive the window that
    started it.
    """
    handlers = build_handlers(session or Session())
    for line in lines:
        try:
            response = handle_line(handlers, line)
        except Exception as exc:
            # The type name, never the exception text: a traceback from deep inside a
            # parser can contain the document that provoked it.
            response = error(INTERNAL_ERROR, f"unhandled {type(exc).__name__}")
        if response is not None:
            out.write(response.to_json() + "\n")
            out.flush()


def serve_request(request: Request, *, session: Session | None = None) -> Response:
    """One request, for tests and for embedding the host in another process."""
    return dispatch(build_handlers(session or Session()), request)
