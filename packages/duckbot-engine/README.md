# duckbot-engine

The small composition layer that runs one Duckbot task. It connects local context,
classification and redaction, destination policy, the model fallback chain, local
placeholder restoration, task/cost records, the audit chain, and approval gates.

The engine deliberately is not a general workflow framework. Its public flow is:

```python
preview = engine.prepare(request)       # no model call
outcome = engine.execute(preview.task_id)
```

`engine.run(request)` is the convenience form when a separate pre-send screen is not
needed. A risky request returns `ApprovalPending`; `engine.decide(...)` records the
human decision and resumes the exact prepared task when approved.

Retrieved or file content enters as `TaskRequest.context`, a tuple of
`duckbot_core.UntrustedContent`. The engine reads it only through `as_data()`, frames it
as reference data, and classifies/redacts the combined model input. Source labels are
local metadata and are never interpolated into the model prompt.

`PlaceholderMap` stays inside the engine's in-process prepared-task cache. It is never
placed in a preview, task record, approval, audit event, or model payload.

`LocalFileConnector` is the v1 connector boundary. It accepts only relative paths below
one selected directory, rejects symlink/junction escapes, reads a small allowlist of text
formats with an explicit encoding, and returns `UntrustedContent`. It is read-only; each
successful access can be written to the same audit chain used by the task engine.

For persistence, pass a `duckbot_core.SqliteStores` instance as `stores=`. The engine
uses its task, approval and audit protocols while prepared payloads and placeholder maps
remain memory-only. Individual protocol implementations can instead be passed as
`task_store=`, `approval_store=` and `audit_store=`.

## Verify

```bash
pytest -q
ruff check src tests && ruff format --check src tests
mypy --strict src/duckbot_engine
```
