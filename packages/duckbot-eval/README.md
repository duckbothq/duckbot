# duckbot-eval

Is a small local model good enough at the jobs Duckbot gives a local model?

**This package is the instrument, not the reading.** No model has been run through it
yet. It produces a number the moment somebody points it at Ollama, and until then it
measures nothing.

## Install and run

```bash
pip install -e ../duckbot-schemas -e ../duckbot-core -e ../duckbot-privacy \
            -e ../duckbot-gateway -e .
pytest -q                                    # 65 tests, none of which open a socket

# the first real measurement — needs no key
python scripts_evaluate.py --ollama qwen2.5:7b
```

## Why not a benchmark

A general benchmark would tell us something true and irrelevant, and we would make a
product decision on it anyway. The architecture gives a local model exactly three jobs,
so those are the three tasks:

**Classification** — how sensitive is this content. The errors are asymmetric in a way
accuracy hides: calling sensitive content harmless sends it to a hosted provider, while
calling harmless content sensitive only costs a little usefulness. Graded separately.

**Chinese name extraction** — the one thing `duckbot-privacy` says in its own docstring
is the model's job. It already has a baseline: 90.9% recall on the corpus, and a named
miss (`就張明輝客戶的年度審計`) that is in this dataset as a case. A local model that cannot
beat the rules on the thing the rules admit they are bad at is not earning its place.

**Derived rewriting** — the `DERIVE` policy action. The task where a plausible answer is
the worst outcome, because a fluent rewrite that still names the client has defeated the
whole purpose while looking like success.

## The two checks nobody else runs

**Traditional Chinese.** A small multilingual model will often answer a Cantonese prompt
in Simplified. For a Hong Kong customer that output is not slightly worse, it is
unusable — and no general benchmark measures it. The detector is built for precision over
recall: it holds only characters whose Simplified form is not also valid Traditional, so
后, 里, 只, 干, 台 and 面 are all deliberately excluded. Reporting "this model writes
Simplified" when it does not would be a wrong verdict on a real decision.

**Leakage.** The privacy detector from `duckbot-privacy` is run over the model's own
output, so an identifier the model introduced or reformatted is caught — not only the
values the case listed.

Monetary amounts are deliberately **not** treated as identifiers. In a derived rewrite
the figure usually *is* the meaning ("the quotation was about forty-eight thousand"), and
failing a rewrite for keeping it would penalise it for doing its job.

## Every rate carries its interval

A number without its precision is worse than no number, because it gets quoted. So a
five-case task reports like this:

```
classify
  all checks passed   60% (3/5, 95% CI 23%–88%)
  not_under_classified    60% (3/5, 95% CI 23%–88%)  [decision]

The widest interval here spans 65% on 4 cases. Reaching ±5 points at that rate needs
about 289 cases per task. Read these figures as a direction, not a measurement.
```

Nobody can put "60%" in a slide without the rest of the line coming with it. The Wilson
interval is used rather than the normal approximation because the normal one is wrong
exactly where evaluation sets live — small n and rates near 0 or 1, where it produces
bounds below zero or above one.

**The current dataset has fifteen cases, five per task.** That is enough to see a model
that is obviously unsuitable and not enough to separate two that are close. Growing it is
the highest-value contribution to this package, and the report tells you how far short it
is every time it runs.

## What it deliberately does not do

**It does not go through `ModelGateway`.** The gateway routes by sensitivity and refuses
what may not leave; an evaluation needs to send the same case to whichever model it is
measuring, including sending sensitive-looking content to a hosted model to find out how
that model classifies it. Those are opposite requirements, and bending the gateway to
allow it would weaken the thing the gateway exists for.

Which is why **every value in the dataset is invented**, and why that is not negotiable.
This is the one component in the system that sends content wherever it is told.

**It does not grade with a model.** Model-graded rubrics would handle paraphrase, and
would also mean grading a model with a model — often the same one. The cost of string
matching is that a legitimate paraphrase can fail `retains_meaning`: if a model writes
「稽核」 where the case expects 「審計」, it is marked wrong. A failing `retains_meaning`
should be read before it is believed. `no_forbidden_values` and `traditional_chinese`
have no such weakness and are the checks to trust.

**It parses leniently.** "I think this is LOCAL_ONLY because…" scores as LOCAL_ONLY. We
are asking whether the model can do the job, not whether it follows output formatting —
an application can always parse. That leniency flatters the model, which is why it is
written down rather than hidden in a regular expression.

## Prompts are part of the measurement

They live in `tasks.py`, they are identical for every model compared, and
`PROMPT_VERSION` is recorded in every result. A model that fails with one prompt and
succeeds with another has not changed; the measurement has. Changing a prompt invalidates
comparison with results recorded before the change, and the version number is what stops
two incomparable runs ending up in the same table.
