# Duckbot

**使用任何 AI，資料由你保管。 / Use any AI. Keep your data.**

**Community developer preview · Apache-2.0 · Windows-first**

This repository contains the open-source Community edition. It is an early developer
preview, not a production-ready release. The tested Windows installer is unsigned;
a signed public installer is not available yet. See [getting started](docs/GETTING_STARTED.md)
and [preview release notes](docs/RELEASE-NOTES.md) for the verified scope and limitations.

Community has no software licence fee or commercial-use restriction beyond the
Apache-2.0 terms. iGears offers separately scoped deployment and support services.
Future Duckbot Business management modules will have a separate commercial licence;
they are planned, are not included here, and do not change this repository's licence.
See [editions and services](EDITIONS.md).

Duckbot is a Windows-first privacy gateway for Hong Kong SMEs. It detects sensitive
values in Traditional Chinese business material, replaces them before a hosted model is
called, restores placeholders locally, and records a tamper-evident task/audit history.

The v1 flow includes a Tauri desktop, local Python sidecar, task engine, pre-send
preview, approval gates, model routing/fallback, secure Windows DPAPI key storage, and a
read-only scoped local-file connector. Community Edition has no mandatory iGears-hosted
service, telemetry, licence server, relay, or hosted proxy.

## Development

Each `packages/duckbot-*` directory is an independently testable Python package, except
`duckbot-shell`, which is the thin Tauri desktop. Install schemas and core first, then
privacy, gateway, memory, engine, eval, and host. The authoritative CI definitions are
under `.github/workflows`.

Run a source-sidecar privacy smoke test on Windows:

```powershell
$env:PYTHONPATH = (Get-ChildItem packages/*/src).FullName -join ';'
python packages/duckbot-host/scripts_smoke.py python -m duckbot_host
python packages/duckbot-host/scripts_product_smoke.py python -m duckbot_host
```

The Windows workflow freezes `duckbot-host.exe`, copies it into the Tauri resources,
builds an NSIS per-user installer, and still produces an unsigned artifact when signing
credentials are unavailable.

The offline provider is a demonstration echo. Select Ollama for a real local model,
or configure a hosted provider, its current model prices, budget and API key. A source
test pass does not certify a Windows installer or a live model account. Check the
desktop workflow result for the exact commit before distributing its artifact.

Changes to the instruction, risk, source file or approval description discard the
current preview. Saving settings or deleting a provider key also cancels any prepared
tasks, so running again requires a fresh preview. Cancellation does not interrupt a
model request that has already started.

## Safety boundaries

- Hosted adapters accept an `OutboundPermit`, never arbitrary raw text.
- Placeholder maps stay in the Python process and are never serialized.
- Retrieved files are `UntrustedContent`, not instructions.
- Financial and destructive actions always require explicit approval.
- API keys are DPAPI-protected for the current Windows user and never returned to the UI.

Licensed under [Apache-2.0](LICENSE). Contributions use DCO sign-off; see
[CONTRIBUTING.md](CONTRIBUTING.md). Report vulnerabilities privately as described in
[SECURITY.md](SECURITY.md).
