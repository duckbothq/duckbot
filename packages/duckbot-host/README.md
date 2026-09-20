# duckbot-host

The local Python sidecar used by the Duckbot desktop. It exposes protocol version 2 as
newline-delimited JSON-RPC over the child process's standard input and output; it never
opens a listening port.

The host owns the product runtime that must not move into the webview or Rust shell:

- privacy classification, redaction, and local placeholder restoration;
- task preparation, exact pre-send previews, execution, and approval decisions;
- model/provider construction and cost/budget enforcement;
- persistent task and tamper-evident audit stores;
- scoped, read-only local-file access; and
- non-secret settings plus Windows DPAPI-protected provider credentials.

Production data is stored below `%LOCALAPPDATA%\Duckbot`. API keys are encrypted for the
current Windows user and are never returned by JSON-RPC. On a platform without DPAPI,
secret storage fails closed rather than writing plaintext.

## Install and verify

Install the sibling packages first, including `duckbot-gateway` and `duckbot-engine`,
then run:

```powershell
pytest -q
ruff check src tests
ruff format --check src tests
mypy --strict src/duckbot_host

# Traditional Chinese privacy path through a source sidecar
python scripts_smoke.py python -m duckbot_host

# Full prepare -> preview -> execute -> task/audit path
python scripts_product_smoke.py python -m duckbot_host
```

The methods used by the v1 desktop are `health`, `task_prepare`, `task_execute`,
`approval_decide`, `tasks_list`, `audit_list`, `audit_verify`, `settings_get`,
`settings_update`, and `connector_list`. The earlier `classify`, `redact`, `restore`, and
`forget` methods remain available for the narrow privacy flow.

## Security boundaries

Standard output belongs exclusively to the protocol. The CLI binds it explicitly as
UTF-8, and errors are authored so they never quote document content, provider response
bodies, or keys. Placeholder maps and prepared task payloads live only in this process;
the desktop receives a redacted preview and the final answer after local restoration.

`duckbot-host.spec` freezes the sidecar with PyInstaller. `console=True` is required so
the executable has usable pipes; the Tauri launcher applies `CREATE_NO_WINDOW`, so no
terminal is shown. The installer workflow runs both smoke tests against the frozen
executable before it builds the desktop installer.
