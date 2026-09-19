# duckbot-host

The Python process the desktop shell spawns. JSON-RPC over a pipe.

Workstream D of `ENGINEERING-HANDOVER.md`, first slice — together with
`duckbot-shell`, which is the window, and the `desktop` workflow, which builds them.

## Install and test

```bash
pip install -e ../duckbot-schemas -e ../duckbot-core -e ../duckbot-privacy \
            -e ../duckbot-memory -e .
pytest -q                                    # 37 tests
ruff check src tests && ruff format --check src tests
mypy --strict src/duckbot_host

# talk to it by hand
echo '{"jsonrpc":"2.0","id":1,"method":"health"}' | python -m duckbot_host
```

## Nothing listens on a port

The shell spawns this process and writes to its standard input. That is the whole
transport.

This is the decision worth defending. A local HTTP server, however carefully bound to
127.0.0.1, is reachable by every other process on the machine, appears in port scans,
collides with whatever else wanted that port, and has to be explained to a customer's IT
department. A pipe between a parent and its own child is reachable by neither. For a
product sold on the data staying on the machine, "nothing on this computer is listening"
is a sentence worth being able to say in a security questionnaire.

The framing is newline-delimited JSON — one request per line, one response per line.
Length-prefixed framing is more robust in principle; newline framing can be driven by a
human with a terminal, and JSON cannot contain a raw newline, so the failure it guards
against does not arise.

## Standard output belongs to the protocol

A stray `print` anywhere in the Python — ours, a dependency's, a deprecation warning —
writes a line the shell will try to parse as a response, and the connection is then
broken in a way that looks like a mysterious hang rather than like a print statement.

So `cli.main()` takes the real stdout away from the rest of the process before anything
else runs, and hands it only to the server loop. Everything else goes to stderr, where
the shell logs it. Two lines of precaution against a class of bug otherwise found at
three in the morning by somebody bisecting a dependency upgrade.

## The placeholder map does not cross the process boundary

`redact` returns the redacted text and a **handle**. The map between placeholders and
real values stays in this process, in memory, and is reachable only by giving the handle
back to `restore`.

The shell is a window. It does not need an identity card number to draw a window — so
`classify` returns offsets and entity types, never the values behind them, and a test
asserts that no original value appears anywhere in any response.

Handles die with the process. That is the correct lifetime for the most sensitive
artefact in the system, and `restore` with an unknown handle says so plainly rather than
returning text with the placeholders still in it.

## Errors never quote the document

An error message is written by us and names a type, never content. A traceback from deep
inside a parser can contain the document that provoked it, and a crash report is exactly
the thing a user forwards to a vendor.

## Packaging

`duckbot-host.spec` freezes this into a single executable with PyInstaller. Two things in
that file are load-bearing:

**`console=True` is deliberate.** On Windows a GUI-subsystem executable has no standard
input or output to inherit, and this process communicates over exactly those. The shell
spawns it with `CREATE_NO_WINDOW`, so no console is visible. The subsystem and the window
are different things, and confusing them produces a sidecar that starts and then answers
nothing.

**`cli.py` uses absolute imports.** A frozen executable runs its entry script as a
top-level module, so a relative import raises `ImportError: attempted relative import
with no known parent package` the moment the binary starts — while working perfectly
under `python -m duckbot_host`. This was found by running the frozen binary rather than
by trusting the spec, and a test now parses `cli.py` and fails if a relative import
appears.

PyInstaller is GPL-2.0-or-later with a bootloader exception, and the bootloader ships
inside the executable we distribute. See section 5.6 of
`duckbot_dependency_licence_register.md`: the exception covers embedding, and explicitly
does not cover modification, so the prebuilt bootloader must never be patched.
