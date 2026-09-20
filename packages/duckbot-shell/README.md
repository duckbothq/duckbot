# duckbot-shell

The thin Tauri desktop for Duckbot. Rust launches the bundled Python sidecar and forwards
an allowlisted set of JSON-RPC calls over the child process's pipes. Privacy, policy,
approval, connector, model, cost, and audit logic remain in tested Python code.

The v1 interface provides:

- one task screen with optional local-file context;
- a pre-send preview of destination, redactions, policy, outbound content, and cost;
- approve/refuse controls for risky work;
- final result, recent-task, and verified audit views; and
- provider, model, budget, connector, encoding, and secure API-key settings.

User-facing copy is Traditional Chinese first and English second. Dynamic values are
inserted with `textContent`; the UI does not render model or document text as HTML.

## Sidecar transport

Nothing binds a local HTTP port. One mutex covers each complete request/response
transaction, and response IDs are checked before a value is accepted. The startup
handshake requires protocol version 2. Sidecar stderr is discarded so an undrained pipe
cannot deadlock the application or become a document-content log.

The shell resolves `duckbot-host.exe` from its installed resource directory and starts it
with `CREATE_NO_WINDOW`. If the process exits, the error is shown rather than silently
restarting and losing in-memory placeholder maps or prepared approvals.

## Build and verification

The NSIS bundle is configured for per-user installation. The Windows workflow freezes
and smoke-tests the sidecar, places it in `src-tauri/resources`, then runs:

```powershell
npx --yes "@tauri-apps/cli@^2" build
```

Signing is conditional; a usable unsigned installer is still uploaded when certificate
secrets are absent. Locally, the dependency-free webview script can at least be parsed
with `node --check ui/main.js`. A full Rust/Tauri build requires the Rust and Windows
desktop toolchains.
