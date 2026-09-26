# Getting started with the Community source preview

Read the [release notes](RELEASE-NOTES.md) first. This guide is for developers;
organisations seeking a supported pilot can [contact iGears](https://duckbot.hk/contact/).

## Run a local source smoke check on Windows

Use Python 3.12 or 3.13 in a virtual environment from the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e packages/duckbot-schemas -e packages/duckbot-core
python -m pip install -e packages/duckbot-privacy -e packages/duckbot-gateway -e packages/duckbot-memory -e packages/duckbot-engine -e packages/duckbot-eval -e packages/duckbot-host
$env:PYTHONPATH = (Get-ChildItem packages/*/src).FullName -join ';'
python packages/duckbot-host/scripts_smoke.py python -m duckbot_host
python packages/duckbot-host/scripts_product_smoke.py python -m duckbot_host
```

These checks exercise the local host with synthetic material. They do not demonstrate
that a paid provider account is configured or that a model response is accurate.

For desktop build prerequisites and exact build steps, follow
[`desktop.yml`](../.github/workflows/desktop.yml), which is the maintained build recipe.
The shell is under `packages/duckbot-shell`; the Python host must be packaged into its
Tauri resources. Do not treat a successful source smoke check as installer acceptance.

## Evaluate a real workflow

1. Begin with non-sensitive sample material in a selected folder. The current file
   connector reads text, Markdown, CSV, JSON and log files only.
2. Use the offline echo mode to understand preview, approvals and local records.
3. For real AI, configure a supported hosted API endpoint, model, API key and current
   pricing/budget, or a separately installed and running Ollama model. Model fees are
   independent of Duckbot; browser subscriptions are not reused as API credentials.
4. Review the destination and proposed masking before approving a request. Editing the
   instructions, files, risk or settings discards the previous preview and approval.
5. Check restored results and records against your sample. Set explicit acceptance
   criteria with the responsible person before introducing real business data.

Keep keys and customer documents out of Git, issue reports and screenshots. No iGears
account or mandatory relay is required by Community.
