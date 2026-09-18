# Security Policy

## Reporting a vulnerability

**Do not open a public issue or discussion for a security vulnerability.**

Report it privately through GitHub's [private vulnerability reporting](https://github.com/duckbothq/duckbot/security/advisories/new), or by email to **info@igears.net** with "Duckbot security" in the subject line.

Please include what you found, how to reproduce it, and what an attacker could do with it.

## What to expect

- Acknowledgement of your report within 5 working days.
- An assessment and a plan, or an explanation of why we do not consider it a vulnerability, within 15 working days.
- Credit in the advisory when the fix is published, unless you prefer otherwise.

We will not take legal action against anyone who reports a vulnerability in good faith, follows this policy, and does not access or modify data belonging to other people.

## Scope and expectations

Duckbot holds credentials, reads business documents, and performs actions on the user's behalf. We are particularly interested in reports covering:

- Bypassing the privacy gateway so that content reaches a model provider without classification or redaction
- Exposure of the placeholder mapping, which must never leave the machine
- Bypassing or escaping an approval gate, particularly for financial or destructive actions
- **Prompt injection** — content in a document, email or web page that causes Duckbot to take an action the user did not request. Retrieved content is data, never instruction, and any case where that boundary breaks is a vulnerability, not a quirk.
- Credential handling, logging, or audit log tampering

## Security by openness

Duckbot's detection rules are published, which means an adversary can see what they catch. This is a deliberate trade-off: open review makes the rules better. No part of the security model may depend on those rules being secret, and reports pointing out where it does are welcome.

## Supported versions

During pre-release development, only the latest commit on `main` is supported.
