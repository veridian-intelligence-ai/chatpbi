"""
Runtime validation script for DAX generation (G.1).

Tests the full flow:
  1. Load FabricClient (from F.1+F.3)
  2. Load system prompt and tool definition (from G.1)
  3. Send a Portuguese question to Claude with the tool defined
  4. Claude generates DAX and calls execute_dax tool
  5. Script executes the DAX via FabricClient
  6. Returns result to Claude
  7. Claude formats response in PT
  8. Script prints the full transcript

Usage:
    python scripts/validate_dax_generation.py "Quanto foi gasto com a cota em 2025?"

If no question argument, uses a default test question.

Exits 0 on success, 1 on failure.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

load_dotenv(_PROJECT_ROOT / ".env")

from api.adapters.fabric import (  # noqa: E402
    FabricAPIError,
    FabricAuthenticator,
    FabricAuthError,
    FabricClient,
    FabricConfigError,
)
from api.prompts_fabric import (  # noqa: E402
    EXECUTE_DAX_TOOL,
    PROMPT_VERSION,
    build_date_context_message,
    build_system_prompt_blocks,
    get_max_retries,
)

_DEFAULT_QUESTION = "Quais os 5 deputados que mais gastaram em 2025?"


def _print_header() -> None:
    bar = "=" * 70
    print(bar)
    print("DAX generation validation (modelo ativo)")
    print(bar)


def _build_anthropic_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment")
    return anthropic.Anthropic(api_key=api_key)


def _build_fabric_client() -> FabricClient:
    authenticator = FabricAuthenticator()
    return FabricClient(authenticator)


def _execute_dax_safely(client: FabricClient, dataset_id: str, dax: str) -> dict:
    """Run DAX and return a JSON-serializable dict for tool_result."""
    try:
        result = client.execute_query(dataset_id, dax)
        return {
            "ok": True,
            "row_count": result.row_count,
            "columns": result.columns,
            "rows": result.rows[:50],  # cap to first 50 rows to avoid context bloat
            "latency_ms": result.metadata.get("latency_ms"),
        }
    except (FabricAPIError, FabricAuthError, FabricConfigError) as exc:
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "context": getattr(exc, "context", {}),
        }


def main() -> int:
    _print_header()

    question = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_QUESTION
    print(f"  Pergunta: {question}")
    print()

    dataset_id = os.getenv("FABRIC_DEFAULT_DATASET_ID", "").strip()
    if not dataset_id:
        print("❌ FABRIC_DEFAULT_DATASET_ID not set")
        return 1

    try:
        anthropic_client = _build_anthropic_client()
        fabric_client = _build_fabric_client()
    except Exception as exc:
        print(f"❌ Setup error: {exc}")
        return 1

    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    system_blocks = build_system_prompt_blocks()

    messages = [
        build_date_context_message(),
        {"role": "user", "content": question},
    ]
    max_iterations = get_max_retries() + 2  # initial + 2 retries + 1 final response

    total_chars = sum(len(b["text"]) for b in system_blocks)
    print(f"→ System prompt length: ~{total_chars // 4} tokens (approx, cached)")
    print(f"→ Prompt version: {PROMPT_VERSION}")
    print(f"→ Model: {model}")
    print(f"→ Max iterations: {max_iterations}")
    print()

    for iteration in range(max_iterations):
        print(f"--- Iteration {iteration + 1} ---")
        start = time.monotonic()
        response = anthropic_client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_blocks,
            tools=[EXECUTE_DAX_TOOL],
            messages=messages,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        print(f"  Claude response ({elapsed}ms, stop_reason={response.stop_reason})")
        usage = response.usage
        cache_write = getattr(usage, "cache_creation_input_tokens", 0)
        cache_read = getattr(usage, "cache_read_input_tokens", 0)
        print(
            f"  Tokens: input={usage.input_tokens}, output={usage.output_tokens}, "
            f"cache_write={cache_write}, cache_read={cache_read}"
        )

        if response.stop_reason == "end_turn":
            text_blocks = [b.text for b in response.content if b.type == "text"]
            final = "\n".join(text_blocks).strip()
            print()
            print("=" * 70)
            print("RESPOSTA FINAL AO UTILIZADOR:")
            print("=" * 70)
            print(final)
            print()
            return 0

        if response.stop_reason == "tool_use":
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b.text for b in response.content if b.type == "text"]

            if text_blocks:
                print(f"  Pre-tool text: {text_blocks[0][:200]}")

            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tu in tool_uses:
                dax = tu.input.get("query", "")
                explanation = tu.input.get("explanation_pt", "")
                print("  Tool call: execute_dax")
                print(f"    explanation_pt: {explanation}")
                print(f"    query: {dax[:200]}{'...' if len(dax) > 200 else ''}")

                result = _execute_dax_safely(fabric_client, dataset_id, dax)
                if result["ok"]:
                    print(
                        f"    ✅ {result['row_count']} rows in "
                        f"{result['latency_ms']}ms"
                    )
                else:
                    print(
                        f"    ❌ {result['error_type']}: "
                        f"{result['error_message'][:200]}"
                    )

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": str(result),
                    }
                )

            messages.append({"role": "user", "content": tool_results})
            continue

        print(f"❌ Unexpected stop_reason: {response.stop_reason}")
        return 1

    print(f"❌ Max iterations reached ({max_iterations})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
