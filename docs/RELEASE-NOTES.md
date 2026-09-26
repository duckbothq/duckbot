# Community developer preview — 26 September 2026

This is the first public source preview of Duckbot Community under Apache-2.0.
It is intended for developers and explicitly scoped pilot evaluations.

## Verified scope

- Local detection for implemented Hong Kong identifiers and context-marked personal names.
- Masked hosted-model requests, local placeholder restoration, pre-send preview,
  sensitivity policy, budget checks and human approval.
- Local task/audit records and a read-only selected-folder connector for `.txt`, `.md`,
  `.csv`, `.json` and `.log` files.
- Windows current-user DPAPI key encryption, recovery and deletion.

The runtime tree at commit `78c02c43965f98e246fc9176193e9625d68554d7` matches the tested
PR build at `2406018d000a92cc8852f0f08b4ed4a60c4de192`. Its 29 CI checks passed,
including actual Windows installation, sustained window/host startup, installed-host
privacy/task checks and DPAPI checks. Local verification included 504 Python tests
and eight desktop UI interaction tests. Publication documentation does not change that runtime.

[Windows validation run](https://github.com/duckbothq/duckbot/actions/runs/36231970931)

## Current limits

- The Windows installer produced by CI is unsigned. There is no signed public installer
  or stable binary release. Installation artifacts from Actions are development artifacts.
- Offline mode is an echo demonstration, not an AI model. Configure a supported provider
  or a separately running Ollama model for real model work. Acceptance against a customer's
  actual paid model account remains part of each pilot.
- Detection is incomplete and needs review. This is a controlled Duckbot request workflow,
  not interception of every app's traffic or a compliance certification.
- PDF/Word parsing, email, Microsoft 365, MCP, browser automation, automatic updating,
  central administration and Business modules are not shipped in this preview.
- macOS and Linux desktop installers are not part of this release. The Linux GTK
  dependency graph has an unresolved moderate `glib 0.18.5` advisory, GHSA-wrw7-89jp-8q8g;
  the Windows target dependency graph does not contain glib.

Report security concerns using [SECURITY.md](../SECURITY.md). Use
[getting started](GETTING_STARTED.md) to evaluate the source and
[EDITIONS.md](../EDITIONS.md) for the Community/Business boundary.
