# Contributing to Duckbot

Thanks for considering a contribution.

> **Note:** Duckbot is in early development and the architecture is still moving. Before starting significant work, please open a Discussion so we can tell you whether it fits and whether someone is already on it. We would rather say so early than decline a finished pull request.

## Before you start

- **Bugs:** open an Issue with steps to reproduce.
- **Features:** open a Discussion first, not an Issue.
- **Questions:** [Discussions](https://github.com/duckbothq/duckbot/discussions), not Issues.

## Developer Certificate of Origin

All commits must be signed off. By signing off you certify that you wrote the contribution or have the right to submit it under the project's licence — see the [Developer Certificate of Origin](https://developercertificate.org/).

Add the sign-off automatically:

```bash
git commit -s -m "your message"
```

which appends:

```text
Signed-off-by: Your Name <your.email@example.com>
```

Pull requests without sign-off on every commit cannot be merged. There is no separate contributor licence agreement to sign.

## Licensing of contributions

Contributions are accepted under the [Apache License 2.0](LICENSE), the same licence as the project.

**Dependencies matter here.** Duckbot's core is Apache-2.0 and cannot link to AGPL, SSPL, BSL, or other copyleft or source-available components. If your contribution adds a dependency, state its licence and exact version in the pull request. Where such a component is genuinely the best option, it belongs behind an adapter interface as a separately installed plugin, not in the core.

## Pull requests

- One logical change per pull request.
- Include tests for behaviour you change.
- Changes to detection or redaction logic must not regress the privacy evaluation suite. Recall matters more than precision: an over-redaction annoys the user, a missed identifier defeats the purpose of the product.
- Update the documentation in the same pull request.
- Describe what you changed and why. "Why" is the part reviewers cannot reconstruct.

## Code of conduct

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
