# duckbot-gateway

One frontier model, one low-cost model and one local model behind a single interface,
chosen by sensitivity first and cost second, with a price attached to every call.

Workstream C of `ENGINEERING-HANDOVER.md`, first half. Local memory and the context
compiler are the second half and are not in this package yet.

## Install and test

```bash
pip install -e ../duckbot-schemas -e ../duckbot-core -e .
pytest -q                                    # 76 tests, none of which open a socket
ruff check src tests && ruff format --check src tests
mypy --strict src/duckbot_gateway
```

## The one rule

**Sensitivity is a constraint. Cost is a preference.**

A cheaper model that may not receive the content is not a candidate at all, and no
saving makes it one. Everything else here — tier ordering, price ordering, the fallback
chain — operates only on models that are already allowed. `prefer=ModelTier.FRONTIER`
reorders the eligible models; it never adds one.

Two independent mechanisms enforce this, which is deliberate:

* the **router** filters on each model's declared `max_sensitivity`, and
* the **policy engine** is asked again, per destination, at the moment of sending.

Either alone would be enough on a good day. Both together mean a mistake in one is
caught by the other.

## What goes where

```
caller ──► PreparedContent (already classified and redacted, by duckbot-privacy)
             │
             ▼
        ModelRouter ──► eligible models, cheapest and most private first
             │
             ├─ local model  ──► LocalAdapter.complete(text)      no permit: nothing leaves
             │
             └─ hosted model ──► PolicyEngine.evaluate(destination=…)
                                   │
                                   └─► OutboundPermit ──► RemoteAdapter.complete(permit)
```

`LocalModelAdapter` takes a `str`. `RemoteModelAdapter` takes an `OutboundPermit` and has
no overload that accepts a string. A caller cannot send content to a provider by
forgetting a step; they would have to construct a permit, and that is impossible outside
`duckbot_core.policy`.

The permit also names its destination, so it cannot be reused against a different
provider. The destination is part of what was decided, not a label on the decision.

## The gateway does not detect anything

It takes content that has already been classified and redacted, as `PreparedContent`:

```python
result = privacy.redact(text, content_id="doc-1")
content = PreparedContent(
    classification=result.classification,
    local_text=text,  # the real thing — local models only
    outbound_text=result.redacted_text,  # what may leave
    placeholder_tokens=tuple(result.tokens),
    placeholder_map=result.placeholder_map,
)
answer = gateway.complete(
    content, Requirement(purpose="drafting", sensitivity=result.classification.sensitivity)
)
```

`duckbot-privacy` is not a dependency of this package. Keeping it out means the model
layer cannot quietly become the place where privacy decisions are made, and either
package can be replaced without the other.

`local_text` and `outbound_text` are separate fields rather than one field and a flag, so
that sending the wrong one is a visible mistake rather than a forgotten branch.

## Cost

Checked **before** the call. A model with no configured price raises `UnknownPrice`
before anything is sent, because discovering it afterwards would mean either throwing
away a completed answer or writing a zero into the cost record.

There is no way to switch that off. If a model really is free — a free tier, a trial, an
experiment — give it an explicit zero price with a source saying so. The file then
records that somebody decided, rather than that nobody looked.

**This package ships no prices.** `config/prices.example.json` has the shape and no
figures. Provider pricing changes without notice, and a number baked in here by whoever
wrote it would be quoted to a customer a year later by someone who assumed it was
maintained. Every entry carries the page it came from and the date a person checked it,
and `PriceTable.stale()` lists the ones nobody has confirmed recently.

Arithmetic is `Decimal` throughout, to eight decimal places, and mixed currencies are
refused rather than converted — a conversion needs a rate and a date, and picking one
quietly would make the total look authoritative while being arbitrary.

One honest gap: a provider that reports no token usage prices at zero. A zero that means
"free" and a zero that means "we were not told" are the same number and different facts,
so `Completion.usage_reported` and `GatewayResult.cost_is_complete` carry the difference.
Anything that sums costs should keep that flag and describe the result as a floor when it
is false. Persisting it alongside `ModelCall` is a schema question for whoever builds
reporting.

## Failure, and what is not a failure

A **provider failure** moves to the next model in the chain, and `ModelCall.fallback_chain`
records what was tried first — "it worked" and "it worked first time" are different
operational facts.

A **policy refusal** is not a provider failure:

* `BLOCK` stops everything. Nothing else is tried, because a block is a decision about
  the content, and trying a different provider is the exact opposite of the right
  response.
* `LOCAL_ONLY` or `DERIVE` against a hosted model skips that model and falls through to a
  local one. Again: the answer to "too sensitive for that provider" is never "send it to
  another provider".

Clients do not retry. The fallback chain is the retry mechanism, and a client that
silently retried would make a provider look healthier than it is in the cost report.

## The HTTP clients are not yet verified against live endpoints

`adapters/http.py` implements the Anthropic Messages API, an OpenAI-compatible Chat
Completions endpoint (which covers the low-cost hosted providers and a self-hosted
llama.cpp or vLLM server), and Ollama. They are written from the published request and
response shapes and **have not been run against a real service**, because nobody on the
project has an account key yet.

The tests mock the transport, which proves the clients match what the author believed the
providers do — no more than that. Running each one once against the real endpoint, with a
throwaway key and a one-word prompt, is the first task for whoever gets a key. It takes
ten minutes and it is the only thing that turns this from plausible into known.

Two details in that file are not stylistic:

**No HTTP dependency.** Transport is a protocol with a standard-library implementation.
Adding `requests` or `httpx` buys convenience and costs a licence review, a supply-chain
surface and a pinned version in every deployment.

**Error bodies are never logged.** Providers routinely quote the request back in an error
response, and the request is the thing this product exists to keep private. A failure
records the status code and the provider's error *type*. A test asserts that an identity
number in an error body does not reach the exception message, and that an API key never
appears in one either.

## Configuring the ceilings

`ModelDescriptor.max_sensitivity` is a statement about where the bytes go, not about how
good the model is. A descriptor that is not `ModelTier.LOCAL` cannot declare itself fit
for `LOCAL_ONLY` content; construction raises.

The suggested starting point, which is what the tests use:

| tier | max_sensitivity | effect |
|---|---|---|
| local | `LOCAL_ONLY` | everything may reach it |
| low cost (hosted) | `ANONYMIZE` | redacted content may go; `DERIVE` and above stay here |
| frontier (hosted) | `ANONYMIZE` | same |

A customer can tighten this. They should not have to.
