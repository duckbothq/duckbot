"""Run the evaluation against a model.

    # a local model through Ollama, which needs no key
    python scripts_evaluate.py --ollama qwen2.5:7b

    # an OpenAI-compatible endpoint, hosted or self-hosted
    python scripts_evaluate.py --openai-compatible http://localhost:8080/v1 --model local-1

The dataset contains only invented values, which is what makes it safe to send anywhere.
Keep it that way.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from duckbot_gateway.adapters.http import (
    AnthropicClient,
    OllamaClient,
    OpenAICompatibleClient,
)

from duckbot_eval import EvaluationRunner, format_report, load_cases

DEFAULT_DATASET = Path(__file__).parent / "datasets" / "hk_local_model_v1.json"


def build_client(args: argparse.Namespace) -> tuple[object, str]:
    if args.ollama:
        return OllamaClient(
            model=args.ollama, base_url=args.base_url or "http://localhost:11434"
        ), (f"ollama/{args.ollama}")
    if args.openai_compatible:
        # The key comes from the environment, never from an argument: a key on the
        # command line lands in the shell history and in the process list.
        return OpenAICompatibleClient(
            base_url=args.openai_compatible,
            model=args.model,
            api_key=os.environ.get("DUCKBOT_EVAL_API_KEY"),
        ), f"openai-compatible/{args.model}"
    if args.anthropic:
        key = os.environ.get("DUCKBOT_EVAL_API_KEY")
        if not key:
            raise SystemExit("set DUCKBOT_EVAL_API_KEY")
        return AnthropicClient(api_key=key, model=args.model), f"anthropic/{args.model}"
    raise SystemExit("choose one of --ollama, --openai-compatible or --anthropic")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ollama", help="model name served by a local Ollama")
    parser.add_argument("--openai-compatible", help="base URL of a chat-completions endpoint")
    parser.add_argument("--anthropic", action="store_true")
    parser.add_argument("--model", default="", help="model name for the non-Ollama clients")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args(argv[1:])

    client, label = build_client(args)
    cases = load_cases(args.dataset)
    print(f"running {len(cases)} cases against {label}\n", flush=True)
    result = EvaluationRunner(client, model=label).run(cases)  # type: ignore[arg-type]
    print(format_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
