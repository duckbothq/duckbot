# Notes for whoever picks this up

This package was written during Phase 0 planning, in the documents folder rather than in
a repository working copy, because the machine it was written from cannot push to
GitHub. It needs moving.

## Where it should live

`duckbothq/duckbot`, as `packages/duckbot-schemas/` or at the repository root if the
core turns out to be a single Python package. That layout decision is yours; it was not
made here, because it depends on how the core is structured and that is a Phase 1
question.

To move it:

```bash
# from a clone of duckbothq/duckbot
cp -r "C:/new-project/duckbot/duckbot-schemas" packages/duckbot-schemas
git add packages/duckbot-schemas
git commit -s -m "Add Phase 0 schema contracts"
```

The `-s` matters: the project requires DCO sign-off on every commit, and the first
commits should not be the exception.

## What was verified

Written and tested on Python 3.10.12 with pydantic 2.13.5. 31 tests pass.

**Python floor is 3.12**, set deliberately. The package was authored and tested on 3.10
because that is what the authoring machine had, and the code is compatible with it — but
a product starting development now has no reason to carry an older runtime for its whole
life. `requires-python` only gates installation, so the suite still runs on 3.10 if you
need it to; CI is where the supported versions are actually decided, so make the matrix
match this floor.

## What this package is not

It is not the core, and it should not grow into it. If a pull request adds persistence,
HTTP, or policy evaluation logic here, that is the signal that the contracts and the
implementation are merging — which is exactly what defining them in Phase 0 was meant to
prevent.

## Things left open on purpose

- **Entity type vocabulary.** `DetectedEntity.entity_type` is a free string with examples
  in the docstring. It should become a controlled vocabulary once the Hong Kong test
  corpus exists and the real categories are known, rather than being guessed now.
- **Memory retention enforcement.** `RetentionPolicy` records the intent; nothing deletes
  anything yet. Whoever builds memory owns making it true, and under the PDPO the
  difference between a stated retention policy and an enforced one matters.
- **Policy rule identifiers.** `matched_rule_id` is a string; the rule format itself is a
  Phase 1 design question.
