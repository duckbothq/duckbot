# duckbot-shell

The desktop window. A Tauri application that spawns the Python sidecar and talks to it
down a pipe.

## Status: written, not verified

**Nobody has run this.** It cannot be built or run from the environment it was written
in — a Linux container with no Windows toolchain — and unlike every other package in this
repository it has not been executed before being committed. The Windows build workflow is
what proves it, and the first run of that workflow is where problems will surface.

Treat the Rust below as a careful draft, not as working software. The Python half it
talks to *is* verified, including as a frozen executable, so a failure here is a failure
in the shell or in the packaging, not in the thing it calls.

## Two decisions, both reversible at a cost

### Tauri rather than Electron

Tauri produces an installer in the region of ten megabytes against Electron's hundred and
fifty, because it uses the operating system's own webview instead of shipping a browser.
For a product whose pitch is "it runs on the machine you already have", that difference
is visible to the customer on the download page.

The cost is a third language. The repository is Python and TypeScript; Tauri adds Rust.
The Rust here is deliberately as small as a process launcher can be — spawn, write lines,
read lines — so that the team's exposure is a file, not a discipline.

On Windows the webview is WebView2, which ships with Windows 11 and has been distributed
to Windows 10 through Windows Update. The installer can include the bootstrapper for the
machines that somehow lack it.

If the team would rather not carry Rust, Electron is a legitimate choice and the Python
side does not change at all: the sidecar protocol is a pipe, and any language can spawn a
process.

### Standard input and output rather than a local HTTP port

The shell talks to the sidecar over the child process's own pipes. Nothing binds a port.

This is the decision worth defending. A local HTTP server, however carefully bound to
127.0.0.1, is reachable by every other process on the machine, appears in port scans,
collides with whatever else wanted that port, and has to be explained to a customer's IT
department. A pipe between a parent and its own child is reachable by neither.

For a product sold on the data staying on the machine, "nothing on this computer is
listening" is a sentence worth being able to say in a security questionnaire.

## What the first slice does

Opens a window, starts the sidecar, calls `health`, and offers a text box that calls
`redact` and shows the redacted text. That is the smallest thing that proves the whole
chain — window, process spawn, protocol, privacy layer — end to end.

The placeholder map never leaves the sidecar. The shell receives a handle and can ask for
a restoration; it never holds the real values.
