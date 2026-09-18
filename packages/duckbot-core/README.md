# duckbot-core

The control plane: task records, the policy engine, approval gates and the audit log.
Everything else in the product depends on this, which is why it was built first.

Workstream A of `ENGINEERING-HANDOVER.md`.

## Install and test

```bash
pip install -e ../duckbot-schemas -e .
pytest -q          # 34 tests
ruff check src tests && ruff format --check src tests
mypy --strict src/duckbot_core
```

## Two structural guarantees

Both are enforced by types rather than by asking people to be careful, and both have a
test that fails loudly if someone relaxes them. If you find one inconvenient, that is
the guarantee working.

### Content cannot leave without a policy decision

The architecture rule is that the privacy gateway sits **on** the outbound path, not
beside it. A rule that lives only in documentation gets bypassed by the first person in
a hurry, so it lives in the type system instead.

`OutboundPermit` cannot be constructed from outside `policy.py`. Model adapters take a
permit, not raw content. There is therefore no route outward that skips `PolicyEngine`,
short of editing that file — which is a reviewable act rather than an accident.

`evaluate()` returns `(decision, permit)` where the permit is `None` for anything that
does not go outbound, so a caller who forgets to check gets a `None` rather than a way
through.

A `REDACT` decision that arrives with no placeholder tokens is refused: either the
content was not actually redacted, or the tokens were dropped on the way, and sending it
would mean sending the original.

### Retrieved content cannot silently become an instruction

Prompt injection is not a prompt-wording problem. `Instruction` is what a human asked
for; `UntrustedContent` is everything Duckbot read while doing it. They are not
interchangeable, and `UntrustedContent.__str__` is deliberately *not* its text — a stray
f-string is the commonest way retrieved content reaches a prompt, and this makes that
mistake visible in review instead of silent at runtime. Reading the text is spelled
`as_data()`, so a reviewer can see the caller is treating it as data.

Promotion to an instruction exists, because the case is real, and requires a human
approval id so the decision lands in the audit trail.

## Decisions you will run into

**Defaults are restrictive.** When no rule matches, sensitivity decides, and only
`PUBLIC` yields `ALLOW`. A policy engine that fails open is how a product like this ends
up in the news rather than in a tender.

**Financial and destructive can never be auto-approved.** `ApprovalGate` rejects a
configuration that tries, because a setting that can disable the control *is* the
control.

**Terminal task states are terminal.** A task that can be resurrected makes its own
audit trail ambiguous.

**Costs accumulate as decimal strings.** The question a customer asks is what last month
cost them, and answering it should not involve explaining floating point.

**The audit log sequences and seals itself.** Callers describe what happened; they do
not manage sequence numbers or hashes. An audit log whose integrity depends on every
caller remembering something will be broken by the first person in a hurry.

`AuditLog.export_text()` is what gets attached to a client security questionnaire. It
contains no sensitive values — only ids, placeholder token counts and plain-language
detail.

## Storage

`store.py` defines protocols; `sqlite_store.py` is the reference implementation, one
file, suitable for the single-user installation this product targets. Records are JSON
keyed by id, deliberately: the schemas are still settling, and a normalised table per
model would mean a migration for every field added during Phase 1. Normalise what needs
querying once the shapes stop moving.

The audit store has no update and no delete. Enforcing append-only in the interface and
then offering a delete in the implementation would be theatre.

## Deliberately not here

No classification (that is Workstream B), no model adapters (Workstream C), no HTTP, no
UI. The core evaluates, gates and records. It does not know what a model is.

The policy **rule language** is a working v0 — see the handover, Section 9. It covers
what Phase 1 needs and is meant to be replaced once the real entity categories are known
from the Hong Kong corpus rather than guessed now.
