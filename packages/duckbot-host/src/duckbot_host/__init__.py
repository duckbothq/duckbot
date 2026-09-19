"""Duckbot host process.

The Python that the desktop shell spawns and talks to over a pipe. Nothing listens on a
port; see :mod:`duckbot_host.protocol`.
"""

from .cli import main
from .handlers import HOST_VERSION, Session, build_handlers, dispatch
from .protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    PROTOCOL_VERSION,
    Request,
    Response,
    error,
    parse,
)
from .server import handle_line, serve, serve_request

__all__ = [
    "HOST_VERSION",
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "METHOD_NOT_FOUND",
    "PARSE_ERROR",
    "PROTOCOL_VERSION",
    "Request",
    "Response",
    "Session",
    "build_handlers",
    "dispatch",
    "error",
    "handle_line",
    "main",
    "parse",
    "serve",
    "serve_request",
]
