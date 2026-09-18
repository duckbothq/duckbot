# Duckbot

**Use any AI. Keep your data.**

Duckbot is an open-source AI runtime that runs on your own machine. Bring your own models — cloud or local. Sensitive data is detected and removed before anything leaves, and everything that does leave is logged.

Built in Hong Kong by [iGears Technology Limited](https://duckbot.hk).

> **Status: early development.** There is no public release yet. Watch this repository or see [duckbot.org](https://duckbot.org) for release news.

## What it does

- **Routes requests** to the AI model you choose — frontier cloud, low-cost cloud, or a local model on your own hardware.
- **Removes sensitive data** before anything is sent, and restores the real values locally in the response. The mapping between real values and placeholders never leaves your machine.
- **Keeps memory and context local**, so conversations do not have to be rebuilt in someone else's service.
- **Logs every outbound payload and approval decision**, so you can answer the question "what left this building, and who approved it?"

## What it is not

- **Not a model.** Duckbot is the runtime and governance layer around the AI providers you already use.
- **Not better at reasoning than frontier models.** It routes work so you can choose the trade-off between capability, cost, and privacy.
- **Not a replacement for Microsoft 365 Copilot** inside Word and Outlook. It complements the tools you already have.
- **Not a compliance product.** Duckbot supports your controls and records your activity. Legal responsibility remains yours.
- **Local models are weaker than frontier models.** For drafting, translating, summarising, extracting and classifying they are usually enough. For hard reasoning they are not, and Duckbot's answer is to send that work to a stronger model with the sensitive parts removed.

## Install

Not yet available. Signed installers and release notes will be published here when the first release is ready.

## Licence and trademark

Licensed under the [Apache License 2.0](LICENSE). You may inspect, modify, fork and deploy the code freely.

The **Duckbot** name and logo are not licensed with the code. See [TRADEMARK.md](TRADEMARK.md).

## Support

Community support is via [Discussions](https://github.com/duckbothq/duckbot/discussions). Commercial deployment and support are available from iGears — see [SUPPORT.md](SUPPORT.md).
