# duckbot-memory

Local memory and the context compiler: what Duckbot remembers, how long it keeps it, how
it finds it again, and what it is allowed to put in a prompt.

Workstream C of `ENGINEERING-HANDOVER.md`, second half.

## Install and test

```bash
pip install -e ../duckbot-schemas -e ../duckbot-core -e .
pytest -q                                    # 84 tests
ruff check src tests && ruff format --check src tests
mypy --strict src/duckbot_memory
```

No third-party dependency beyond the other Duckbot packages and pydantic. No embedding
model, no search engine, no segmentation library.

## Why this is the file that matters commercially

Every memory added to a prompt costs tokens, and tokens are the bill. Every memory added
also widens what leaves the machine, and that is the privacy exposure. Both get smaller
by the same act — sending less — which is why the compiler is where the product's two
economics meet.

## The compiler's three rules

**A memory above the destination's ceiling never goes in.** Not truncated, not
summarised, not "probably fine because it is only a name". The compiler is told what the
destination may receive and filters on that before relevance is considered. Pinning does
not override it: "mandatory" is the caller's judgement about usefulness, and the ceiling
is not a matter of judgement.

**Every exclusion is reported.** A caller receiving a context block cannot see what is
missing from it. A compiler that quietly drops the most relevant memory because it was
too sensitive leaves that caller acting on a partial answer while believing it complete.
Exclusions come back with reasons — `sensitivity: LOCAL_ONLY exceeds the destination's
ANONYMIZE ceiling`, or `budget: needs 18 tokens, 4 left`.

**Retrieved memory is untrusted content.** A memory built from an email is a document
somebody else wrote, and text inside it that reads like an instruction is not one.
`CompiledContext.as_untrusted()` returns `duckbot_core.UntrustedContent`, so the type
system keeps saying so downstream. The framing line at the top of the block is defence in
depth, not the protection — the guarantee is the type, not the sentence.

```python
compiled = compiler.compile(
    "年度審計",
    budget=Budget(max_tokens=4000, reserve_for_reply=800),
    destination_ceiling=SensitivityLevel.ANONYMIZE,
)
compiled.text              # the block, or "" when nothing fit or qualified
compiled.excluded          # what was left out, and why
compiled.max_sensitivity   # the most sensitive thing actually included
compiled.as_untrusted()    # typed for the prompt-injection boundary
```

`destination_ceiling` is the same number the gateway's router filters on. Passing a
hosted model's ceiling here and then sending the result to that model is the intended
composition.

## Retrieval is lexical, and says so

BM25 over a tokeniser, not embeddings. It finds memories that share terms with the
query. It will **not** find 「租約」 when you ask about "tenancy agreement", and it will not
find a paraphrase. A test asserts that miss, so that if something semantic is ever added,
this README has to change with it.

That is a deliberate first step. The alternatives were to add an embedding model as a
dependency before anyone has measured whether retrieval quality is the bottleneck, or to
ship something that calls itself semantic and is not. The `Embedder` seam is in place so
that replacing it later does not mean rewriting the compiler — and it already carries the
rule that matters: a non-local embedder is refused a `LOCAL_ONLY` memory *before* the
call that would transmit the text, not by a validator afterwards.

### Chinese

A whitespace tokeniser handed 「客戶陳嘉雯的年度審計報告」 produces one enormous token that
matches nothing. That is not a small degradation; it is search silently not working for
most of our customers' documents.

So: **character bigrams for CJK, words for everything else.** 「年度審計」 becomes 年度, 度審,
審計, and a query for 審計 matches. No dictionary, no model, no download.

The costs are stated rather than hidden. Bigrams occasionally match across a word
boundary — 「香港大學生」 yields 港大 — which a proper segmenter would fix later. And 〇 is
included as a CJK character by name rather than by taking its Unicode block, because its
block also holds 、and 。, which must not become tokens.

## Retention is enforced, not recorded

A retention field nothing acts on is a compliance claim the product cannot back. If a
memory says thirty days, `RetentionSweeper` deletes it on the thirty-first.

**Age is measured from creation, never from last use.** Refreshing the clock on access
would turn "kept for 30 days" into "kept for 30 days after you stop touching it" — a
different and much weaker promise than the one the customer was given. `last_used_at`
exists for ranking, not retention.

**Session memory and indefinite memory both have no deadline and mean opposite things**,
so they are handled by different methods rather than one method and a flag: `sweep()` for
the clock, `end_session()` for the session, and `forget(ids)` for somebody asking to be
erased. An erasure request appears in the code as its own act rather than as a special
case of housekeeping.

`sweep(dry_run=True)` answers "what would this remove" without requiring anyone to find
out by losing it.

Note the contrast with `duckbot_core`'s audit log, which is append-only and offers no
delete on purpose. Memory is the opposite and **must** be deletable. Offering retention
policies without a delete would be the same theatre in the other direction.

## Token counts are estimates and are labelled as such

Nothing here tokenises the way a model does; a real count needs the model's own
tokeniser, which is a dependency and a download per provider. So `TokenCounter.is_estimate`
is true, `CompiledContext.tokens_are_estimated` carries it outward, and the same
discipline applies as `usage_reported` in the gateway: a guess and a measurement must not
look alike once written down.

The estimate leans high on purpose. Over-counting fits fewer memories and costs a little
quality; under-counting overflows the context window and costs the whole request.

Chinese is counted at roughly one token per character against one per four for Latin
text. That ratio is not a detail for a Hong Kong product — the same document in
Traditional Chinese costs several times more tokens than in English, which lands directly
on the bill and is a large part of why the local tier exists.
