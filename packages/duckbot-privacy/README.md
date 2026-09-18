# duckbot-privacy

The privacy gateway: detect, redact, restore. This is the package the product is sold
on, and the only one with a number attached to it.

Workstream B of `ENGINEERING-HANDOVER.md`.

## Install and test

```bash
pip install -e ../duckbot-schemas -e .
pytest -q                                    # 125 tests
ruff check src tests && ruff format --check src tests
mypy --strict src/duckbot_privacy
python scripts_measure.py corpus/hk_business_v1.json
```

## The number

Measured against `corpus/hk_business_v1.json`, ten Hong Kong business documents in
Traditional Chinese and English:

| entity | expected | recall | precision |
|---|---|---|---|
| HKID | 5 | 100.0% | 100.0% |
| PHONE | 7 | 100.0% | 100.0% |
| EMAIL | 7 | 100.0% | 100.0% |
| BR_NUMBER | 3 | 100.0% | 100.0% |
| MONEY | 4 | 100.0% | 100.0% |
| SALARY | 2 | 100.0% | 100.0% |
| PERSON_NAME | 11 | 90.9% | 100.0% |
| **overall** | **38** | **97.4%** | **100.0%** |

Run `scripts_measure.py` after any change to detection and put the before and after in
the pull request. "Improved detection" without two numbers is an opinion.

Ten documents is a small corpus and this figure should be read as a floor that CI
defends, not as a claim about arbitrary customer documents. Growing the corpus is the
highest-value contribution anyone can make to this package, and the next batch should be
documents whose shapes are not represented yet — scanned letters, mixed Chinese and
English in one sentence, tables, forms.

## What the rules do and do not do

Stated plainly, because a detector nobody trusts gets switched off:

**Reliable.** HKID, phone numbers, email addresses, business registration numbers,
monetary amounts. These have structure, and structure is what rules are for. HKIDs are
validated against the check digit, so a reference number shaped like one is not reported.

**Partial.** Personal names. Chinese names are anchored on context — a role word before
(`客戶陳嘉雯`), a title after (`黃雅詩經理`), or an explicit label (`姓名：周家豪`). Without an
anchor, "surname plus one or two characters" also matches 張開, 陳述 and 李子, so the
pattern is deliberately not widened. Names are the local model's job in Workstream C;
these rules are the floor.

The one miss in the corpus is exactly this case: `就張明輝客戶的年度審計` has neither a role
prefix nor a title suffix. It is left in the report rather than engineered around.

**Not attempted.** Addresses. Hong Kong addresses are too varied for rules to reach
useful recall, and a detector with poor recall on an entity type is worse than none,
because it produces false confidence.

## Recall over precision, and why

An over-redaction annoys the user. A missed HKID destroys the reason the product exists.
Where the two conflict, recall wins — but precision is measured and reported too, because
a detector that redacts everything scores perfect recall and is useless. Two corpus
documents exist only to catch over-redaction: `no-sensitive-data` and
`near-miss-identifiers`, which is full of identifier-shaped strings that are not
identifiers. Both must produce zero detections, and a test says so.

## Value propagation

A name is introduced once with a role word and then used bare for the rest of the
document. Only the anchored occurrence matches, so the value leaks out of the very
document in which it was already recognised.

`propagate_known_values` closes this: once any detector has committed to a value, every
other literal occurrence of that value in the same document is redacted too. No pattern
is widened and nothing new is judged sensitive, so precision is unaffected — the decision
is simply applied consistently.

Values shorter than three characters are excluded, because a two-character Chinese name
is also an ordinary word. That is a deliberate hole, and the local model's job to close.

## Sensitivity mapping

`SENSITIVITY_BY_ENTITY` gives HKID `LOCAL_ONLY` rather than `ANONYMIZE`. An identity card
number is the single value that most clearly identifies a person in Hong Kong, and the
default posture should be that it does not leave the machine at all, not that it leaves
in a disguised form. A customer can relax that with a policy rule; they should not have
to tighten it.

A document takes the sensitivity of its most sensitive component. It is not less
sensitive because most of it is harmless.

The mapping is a v0 and belongs in configuration once a larger corpus tells us the real
categories.

## The placeholder map never leaves the machine

`PlaceholderMap` is not a pydantic model, has no `model_dump`, and cannot be JSON
encoded. Its `repr` withholds the values. A `ContentClassification` records *where*
something was found and *what token replaced it*, never the value — which is what makes
it safe to write to the audit log.

Tests assert all of this. If someone makes the map serialisable, they fail.

## Adding to the corpus

Write the document with inline markers and let the loader compute offsets:

```
新同事[[PERSON_NAME:陳嘉雯]]將於下月報到，身份證號碼[[HKID:Z683365(A)]]。
```

Hand-maintained offset tables rot within a week, and a corpus nobody will extend is a
corpus that stops being true.

**Every value in the corpus is invented.** No real person, company, client or address
appears in it, and none may. If a real document is ever used as the basis for a test
case, replace the identifying values before committing — and replace them with values
that are internally valid, because a marked HKID with a wrong check digit makes the
corpus lie about the detector. A test checks that.
