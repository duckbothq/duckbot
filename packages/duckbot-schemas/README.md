# duckbot-schemas

The contracts every other Duckbot module is built against. Defined in Phase 0,
deliberately before any feature code, so that later modules cannot become tightly
coupled by accident.

Implementation plan v2, Sections 7 and 16, item 5.

## Install and test

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]" || pip install -e . pytest
PYTHONPATH=src pytest -q
```

31 tests. They are contract tests, not coverage: each guards a decision that would be
expensive to discover was wrong in month four.

## The seven schemas

| Module | Records |
|---|---|
| `task` | a goal from request to outcome, with steps and cost totals |
| `classification` | what was found in a piece of content, and how sensitive it is |
| `policy` | what the policy engine decided, and the sentence the user is shown |
| `model_request` | one model call: provider, tokens, cost, and what it was allowed to see |
| `memory` | one durable local memory, its scope and its retention |
| `approval` | a request for a human to approve an action, and the answer |
| `audit` | one immutable, hash-chained line in the log |

Plus `placeholders`, which is not a schema — see below.

## Two rules, enforced by tests rather than by comment

### 1. Real sensitive values never reach a persisted or outbound record

`PlaceholderMap` holds the mapping between real values and their tokens. It is
deliberately **not** a pydantic model and has no `model_dump`, so it cannot be
serialised into an audit record or an outbound payload by accident — there is nothing
to serialise it with.

This is structural rather than procedural. Documentation asking people not to make a
mistake is weaker than a type that makes the mistake awkward.

Three tests guard it: `PlaceholderMap` is not a `BaseModel`; its `repr` withholds
values; no exported model declares a field typed to hold it. `DetectedEntity` records
offsets and a token, never the value. `AuditEvent` has no `value`, `content`, `payload`
or `text` field, and a test asserts it never grows one — an audit export that could leak
the data the product exists to protect would be the product arguing against itself.

### 2. Every persisted record carries `schema_version`

`SCHEMA_VERSION` in `common.py` is package-wide.

**Not breaking:** adding an optional field with a default.
**Breaking:** removing a field, renaming one, narrowing a type, or changing the meaning
of an existing value. Breaking changes bump the version **and** ship a migration in the
same pull request. Not the next one.

## Decisions worth knowing about before you build on this

**`extra="forbid"` everywhere.** An unexpected field is a bug or a version skew.
Silently accepting it is how data ends up somewhere it was never meant to be.

**Timezone-aware datetimes only.** Naive datetimes raise. An audit log with ambiguous
timestamps is not an audit log.

**Money is a decimal string, not a float.** Totals accumulate; float drift in a figure
a customer will question is not worth the convenience.

**Financial and destructive actions always require approval.** `ALWAYS_REQUIRES_APPROVAL`
is a frozenset in `common.py` and there is deliberately no configuration option to
disable it. That option can be considered when there is operational evidence, not before.

**Decisions must be attributable.** A classification override, an approval, and a policy
override each require a person and a reason. An unattributable approval is worse than no
gate: it produces a record implying oversight that did not happen.

**The audit chain is tamper-evident, not tamper-proof.** Nothing on a single machine is
tamper-proof against someone with write access. `verify_chain` detects modification,
removal and unsealed entries, which is what an auditor, a client security questionnaire
or an incident review actually needs.

**`justification` and `action_description` are user-facing text.** They are shown on the
pre-send screen and the approval prompt, in the user's own language. They are not debug
strings. An approval prompt nobody understands is a rubber stamp.

## What is deliberately absent

No persistence, no ORM, no transport, no policy engine. This package defines shapes and
invariants only. Storage belongs to whatever the core chooses; keeping it out means the
contracts survive that choice changing.

## Licence

Apache-2.0, matching the Duckbot core. Contributions require a DCO sign-off
(`git commit -s`).
