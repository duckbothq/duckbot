# Duckbot

**使用任何 AI，資料由你保管。 / Use any AI. Keep your data.**

Duckbot is a Windows-first privacy gateway for Hong Kong SMEs. It detects sensitive
values in Traditional Chinese business material, replaces them before a hosted model is
called, restores placeholders locally, and records a tamper-evident task/audit history.

The v1 flow includes a Tauri desktop, local Python sidecar, task engine, pre-send
preview, approval gates, model routing/fallback, secure Windows DPAPI key storage, and a
read-only scoped local-file connector. Community Edition has no mandatory iGears-hosted
service, telemetry, licence server, relay, or hosted proxy.

## Development

Each `duckbot-*` directory is an independently testable Python package, except
`duckbot-shell`, which is the thin Tauri desktop. Install schemas and core first, then
privacy, gateway, memory, engine, eval, and host. The authoritative CI definitions are
under `ci-files/.github/workflows` for integration into the public repository layout.

Run a source-sidecar privacy smoke test on Windows:

```powershell
$env:PYTHONPATH = "duckbot-schemas/src;duckbot-core/src;duckbot-privacy/src;duckbot-gateway/src;duckbot-memory/src;duckbot-engine/src;duckbot-host/src"
python duckbot-host/scripts_smoke.py python -m duckbot_host
```

The Windows workflow freezes `duckbot-host.exe`, copies it into the Tauri resources,
builds an NSIS per-user installer, and still produces an unsigned artifact when signing
credentials are unavailable.

## Safety boundaries

- Hosted adapters accept an `OutboundPermit`, never arbitrary raw text.
- Placeholder maps stay in the Python process and are never serialized.
- Retrieved files are `UntrustedContent`, not instructions.
- Financial and destructive actions always require explicit approval.
- API keys are DPAPI-protected for the current Windows user and never returned to the UI.

Licensed under [Apache-2.0](LICENSE). Contributions use DCO sign-off; see
[CONTRIBUTING.md](CONTRIBUTING.md). Report vulnerabilities privately as described in
[SECURITY.md](SECURITY.md).
