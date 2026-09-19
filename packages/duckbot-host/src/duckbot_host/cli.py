"""The entry point, with absolute imports, for a reason worth writing down.

A frozen executable runs its entry script as a top-level module, not as part of a
package, so a relative import here — ``from .server import serve`` — raises
``ImportError: attempted relative import with no known parent package`` the moment the
binary starts. Under ``python -m duckbot_host`` the same line works perfectly, so the
failure appears only in the packaged build.

That failure mode is worse than it sounds: the shell spawns the sidecar, the sidecar dies
immediately, and what the user sees is a window that never finishes loading. The cause is
one import statement in a file nobody was looking at.

So the real entry point lives here with absolute imports, and ``__main__.py`` is a shim.
"""

from __future__ import annotations

import sys

from duckbot_host.handlers import Session
from duckbot_host.server import serve


def main() -> int:
    protocol_out = sys.stdout
    # Anything that prints from here on — ours, a dependency's, a warning — goes to
    # stderr, where the shell can log it without it corrupting the wire.
    sys.stdout = sys.stderr
    serve(sys.stdin, protocol_out, session=Session())
    return 0
