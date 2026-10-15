"""
DAX conversation orchestrator for the app's Power BI pipeline.

Encapsulates the full multi-iteration loop between Claude (DAX generation)
and Microsoft Fabric (DAX execution). Used by /chat/v2 and /chat/voice
in the FastAPI app.

Reuses the system prompt + tool definition from `api.prompts_fabric` (G.2),
so prompt caching, the active semantic model's rules and context, and the DAX
few-shot examples are inherited automatically.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import anthropic

from api.adapters.fabric import (
    FabricAPIError,
    FabricAuthError,
    FabricClient,
    FabricConfigError,
)
from api.prompts_fabric import (
    EXECUTE_DAX_TOOL,
    PROMPT_VERSION,
    build_date_context_message,
    build_system_prompt_blocks,
    get_max_retries,
)

# Hard cap on iterations: initial + N retries + final response.
# get_max_retries() returns 2, so default cap is 4.
_MAX_ITERATIONS = get_max_retries() + 2

# Cap rows in tool_result to avoid context bloat.
_MAX_ROWS_IN_TOOL_RESULT = 50

# Output-token ceiling for a SINGLE Anthropic call. A reply cut off at this
# ceiling is resumed transparently (see _create_turn), so this caps each API
# call, not the final answer: the answer may span 1 + _MAX_CONTINUATIONS calls.
# It must comfortably fit a whole tool_use turn: those carry several DAX
# queries, production logs show them reaching ~5k output tokens, and a turn cut
# inside a tool_use is only partly salvageable (see _create_turn). Text replies
# are resumed instead, so the cap bounds each call, not the answer. Keep
# ANTHROPIC_TIMEOUT_SECONDS in main.py above cap / ~85 tokens per second.
DEFAULT_MAX_TOKENS = 12_000

# Non-streaming requests are refused when max_tokens implies more than 10
# minutes of generation (3600 * max_tokens / 128000 > 600, i.e. > 21333). The
# SDK only checks this when the client uses the default timeout — main.py sets
# an explicit one — so clamp here to keep an env override off that ceiling.
_MAX_NONSTREAMING_TOKENS = 21_000

# How many extra calls may be chained to finish a reply cut off by max_tokens.
_MAX_CONTINUATIONS = 4

_SUGGESTIONS_MARKER = "[next_step_suggestions]"

# A table constructor `{ ... }` used directly as the top-level EVALUATE
# expression returns anonymous columns ([Value1], [Value2], ...), which then
# surface as raw labels in KPI cards/visuals. Project rule: name columns
# explicitly with ROW("Nome", expr) / SELECTCOLUMNS / SUMMARIZECOLUMNS. This
# pattern only matches `{` immediately after the EVALUATE keyword, so
# `... IN { ... }` filters and `{}` nested inside other functions are left
# untouched (no false positives).
_EVALUATE_TABLE_CONSTRUCTOR_RE = re.compile(r"\bEVALUATE\b\s*\{", re.IGNORECASE)


def validate_dax_query(dax: str) -> Optional[str]:
    """
    Structural pre-Fabric guard for generated DAX.

    Returns an instructive error message (PT) when the query uses a forbidden
    pattern, or None when it is acceptable. The message is fed back to Claude
    via the tool_result so the existing retry loop can self-correct.

    Currently enforces a single rule: a table constructor `{ ... }` must not be
    the top-level EVALUATE expression (it produces anonymous Value1/Value2
    columns). ROW / SELECTCOLUMNS / SUMMARIZECOLUMNS and `IN { ... }` filters
    are all accepted.
    """
    if _EVALUATE_TABLE_CONSTRUCTOR_RE.search(dax):
        return (
            "DAX rejeitado: o EVALUATE usa um table constructor `{ ... }`, que "
            "devolve colunas anónimas (Value1, Value2) e gera labels crus nos "
            "visuais. Substitui por ROW(\"Nome\", expr) com nomes de coluna "
            "explícitos — ex: EVALUATE ROW(\"Gasto 2025\", "
            "CALCULATE([Total gasto], ...)). Para vários valores, usa ROW com vários "
            "pares \"Nome\", expr (ou SELECTCOLUMNS/SUMMARIZECOLUMNS com nomes). "
            "Filtros com IN { ... } são válidos e não precisam de mudança."
        )
    return None


def _extract_suggestions(text: str) -> Tuple[str, List[str]]:
    """
    Extract the [next_step_suggestions] block from the answer text.

    Returns (cleaned_answer, suggestions_list).

    The marker block looks like:

        [next_step_suggestions]
        - first suggestion
        - second suggestion
        - third suggestion

    Bullets may use "-", "*", or "•". The marker block is stripped from
    the returned cleaned_answer. If no marker is found, returns (text, []).
    """
    if _SUGGESTIONS_MARKER not in text:
        return text.strip(), []

    parts = text.split(_SUGGESTIONS_MARKER, 1)
    cleaned_answer = parts[0].rstrip()
    suggestions_block = parts[1] if len(parts) > 1 else ""

    suggestions: List[str] = []
    for line in suggestions_block.splitlines():
        stripped = line.strip()
        match = re.match(r"^[-*•]\s+(.+)$", stripped)
        if match:
            suggestion = match.group(1).strip().rstrip(".;,")
            if suggestion:
                suggestions.append(suggestion)
        if len(suggestions) >= 3:
            break

    # Strip any trailing markdown fences that Claude may have wrapped around the block
    cleaned_answer = re.sub(r"\n*```\s*$", "", cleaned_answer)
    cleaned_answer = cleaned_answer.rstrip()

    return cleaned_answer, suggestions


def _usage_int(usage: Any, name: str) -> int:
    """Read an integer counter off an Anthropic usage object, defaulting to 0."""
    value = getattr(usage, name, 0)
    return value if isinstance(value, int) else 0


@dataclass
class IterationLog:
    """One iteration of the Claude→Fabric loop, for observability."""

    iteration: int
    latency_ms: int
    stop_reason: str
    input_tokens: int
    output_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int
    dax_executed: Optional[str] = None
    dax_explanation: Optional[str] = None
    dax_ok: Optional[bool] = None
    dax_error: Optional[str] = None
    dax_row_count: Optional[int] = None
    # Sum of the DAX latencies of this iteration: Claude may emit several
    # execute_dax calls in a single turn.
    dax_latency_ms: Optional[int] = None
    dax_call_count: int = 0
    pre_tool_text: Optional[str] = None
    # Extra Anthropic calls chained to finish a reply truncated at max_tokens.
    continuations: int = 0
    # True when this turn hit max_tokens, whether or not it was salvaged.
    truncated: bool = False


@dataclass
class _TurnOutcome:
    """One complete assistant turn, after any max_tokens continuation."""

    # Effective stop reason for the caller to branch on: a turn cut inside a
    # tool_use is reported as "tool_use" when complete tool calls survive.
    stop_reason: str
    # Usable content blocks — the incomplete trailing block is dropped.
    content: List[Any]
    # Text from the resumed calls, which `content` does not repeat.
    text_prefix: str
    usage: Dict[str, int]
    continuations: int
    elapsed_ms: int
    truncated: bool


@dataclass
class OrchestratorResult:
    """Structured result of a full conversation turn."""

    answer: str
    visual_hint: Optional[Dict[str, Any]] = None
    next_step_suggestions: List[str] = field(default_factory=list)
    dax_query: Optional[str] = None
    dax_rows: Optional[List[Dict[str, Any]]] = None
    dax_columns: Optional[List[str]] = None
    iterations: List[IterationLog] = field(default_factory=list)
    total_latency_ms: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    prompt_version: str = PROMPT_VERSION
    error: Optional[str] = None
    error_type: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        """Convert to a JSON-serializable dict for API responses."""
        return {
            "answer": self.answer,
            "visual_hint": self.visual_hint,
            "next_step_suggestions": self.next_step_suggestions,
            "dax_query": self.dax_query,
            "dax_rows": self.dax_rows,
            "dax_columns": self.dax_columns,
            "iterations": [vars(it) for it in self.iterations],
            "total_latency_ms": self.total_latency_ms,
            "total_cache_read_tokens": self.total_cache_read_tokens,
            "total_cache_write_tokens": self.total_cache_write_tokens,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "prompt_version": self.prompt_version,
            "error": self.error,
            "error_type": self.error_type,
        }


class DAXConversationOrchestrator:
    """
    Orchestrates the Claude ↔ Fabric loop for a single conversation turn.

    Usage:
        orchestrator = DAXConversationOrchestrator(
            anthropic_client=anthropic_client,
            fabric_client=fabric_client,
            dataset_id=dataset_id,
            model="claude-sonnet-5-5",
        )
        result = orchestrator.run(
            user_message="Quanto foi gasto com a cota em 2025?",
            conversation_history=[],  # list of {role, content} dicts
        )
        print(result.answer)

    The orchestrator is intentionally STATELESS — it does not persist
    history. The caller (FastAPI handler) is responsible for fetching
    history from conversation_store and passing it in.
    """

    def __init__(
        self,
        anthropic_client: anthropic.Anthropic,
        fabric_client: FabricClient,
        dataset_id: str,
        model: str = "claude-sonnet-5-5",
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        if not dataset_id or not dataset_id.strip():
            raise ValueError("dataset_id is required")
        self._anthropic = anthropic_client
        self._fabric = fabric_client
        self._dataset_id = dataset_id.strip()
        self._model = model
        if max_tokens > _MAX_NONSTREAMING_TOKENS:
            print(
                f"[orchestrator] max_tokens={max_tokens} exceeds the non-streaming "
                f"ceiling — clamping to {_MAX_NONSTREAMING_TOKENS}"
            )
            max_tokens = _MAX_NONSTREAMING_TOKENS
        self._max_tokens = max_tokens

    def _create_turn(
        self,
        system_blocks: List[Dict[str, Any]],
        messages: List[Dict[str, Any]],
    ) -> _TurnOutcome:
        """
        Produce one complete assistant turn, handling max_tokens truncation.

        A text reply cut off at max_tokens is resumed by replaying the text
        produced so far as an assistant prefill, chaining up to
        _MAX_CONTINUATIONS extra calls, so the caller sees one logical turn.
        The system blocks are unchanged across the chain, so prompt caching
        still applies.

        A turn cut off while emitting tool calls cannot be resumed that way:
        the block being generated carries incomplete JSON input and must never
        be executed. It is dropped, and the tool calls that did complete are
        handed back as a normal "tool_use" turn — Claude sees their results and
        re-emits whatever was lost on the next iteration. Only when nothing
        survives is the turn reported as "max_tokens" for the caller to report.
        """
        prefix = ""
        continuations = 0
        elapsed_ms = 0
        totals = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_write_tokens": 0,
            "cache_read_tokens": 0,
        }

        def outcome(stop_reason: str, content: List[Any], truncated: bool) -> _TurnOutcome:
            return _TurnOutcome(
                stop_reason=stop_reason,
                content=content,
                text_prefix=prefix,
                usage=totals,
                continuations=continuations,
                elapsed_ms=elapsed_ms,
                truncated=truncated,
            )

        while True:
            call_messages = list(messages)
            if prefix:
                call_messages.append({"role": "assistant", "content": prefix})

            start = time.monotonic()
            response = self._anthropic.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_blocks,
                tools=[EXECUTE_DAX_TOOL],
                messages=call_messages,
            )
            elapsed_ms += int((time.monotonic() - start) * 1000)

            usage = response.usage
            totals["input_tokens"] += _usage_int(usage, "input_tokens")
            totals["output_tokens"] += _usage_int(usage, "output_tokens")
            totals["cache_write_tokens"] += _usage_int(
                usage, "cache_creation_input_tokens"
            )
            totals["cache_read_tokens"] += _usage_int(usage, "cache_read_input_tokens")

            blocks = list(response.content or [])
            if response.stop_reason != "max_tokens":
                return outcome(response.stop_reason or "unknown", blocks, truncated=False)

            # Text-only: replay what was written and let Claude carry on.
            if blocks and all(b.type == "text" for b in blocks):
                if continuations >= _MAX_CONTINUATIONS:
                    return outcome("max_tokens", blocks, truncated=True)
                prefix = (prefix + "".join(b.text for b in blocks)).rstrip()
                continuations += 1
                print(
                    f"[anthropic] max_tokens atingido — a continuar a resposta "
                    f"({continuations}/{_MAX_CONTINUATIONS})"
                )
                continue

            # Tool calls in flight: the trailing block is the one that was being
            # generated when the cut happened, so a tool_use there is incomplete
            # and gets dropped. Whatever completed before it is still valid.
            salvaged = blocks[:-1] if blocks and blocks[-1].type == "tool_use" else blocks
            n_salvaged = sum(1 for b in salvaged if b.type == "tool_use")
            if n_salvaged:
                print(
                    f"[anthropic] max_tokens dentro de tool_use — a executar as "
                    f"{n_salvaged} queries completas e a descartar a incompleta"
                )
                return outcome("tool_use", salvaged, truncated=True)

            return outcome("max_tokens", blocks, truncated=True)

    def run(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        extra_system_blocks: Optional[List[Dict[str, Any]]] = None,
    ) -> OrchestratorResult:
        """
        Run a full conversation turn.

        Args:
            user_message: the user's question in Portuguese.
            conversation_history: prior {role, content} messages
                (excluding the new user_message). May be empty.
            extra_system_blocks: optional additional system blocks
                (e.g. voice formatting rules). NOT cached.

        Returns:
            OrchestratorResult with answer, optional visual_hint,
            DAX trace, iteration logs, and cache stats.
        """
        if not user_message or not user_message.strip():
            return OrchestratorResult(
                answer="Pergunta vazia.",
                error="empty_user_message",
                error_type="ValueError",
            )

        system_blocks = build_system_prompt_blocks()
        if extra_system_blocks:
            system_blocks = system_blocks + list(extra_system_blocks)

        # Build messages: date context + history + user question.
        messages: List[Dict[str, Any]] = [build_date_context_message()]
        if conversation_history:
            for msg in conversation_history:
                if msg.get("role") in {"user", "assistant"}:
                    content = msg.get("content", "")
                    if content:
                        messages.append(
                            {"role": msg["role"], "content": str(content)}
                        )
        messages.append({"role": "user", "content": user_message.strip()})

        result = OrchestratorResult(answer="", prompt_version=PROMPT_VERSION)
        last_dax_query: Optional[str] = None
        last_dax_rows: Optional[List[Dict[str, Any]]] = None
        last_dax_columns: Optional[List[str]] = None
        last_visual_hint: Optional[Dict[str, Any]] = None

        for iteration in range(_MAX_ITERATIONS):
            start = time.monotonic()
            try:
                turn = self._create_turn(system_blocks, messages)
            except anthropic.APIError as exc:
                result.error = str(exc)
                result.error_type = type(exc).__name__
                result.answer = (
                    "Erro temporário ao contactar o serviço. Tenta novamente."
                )
                result.total_latency_ms += int((time.monotonic() - start) * 1000)
                return result

            log = IterationLog(
                iteration=iteration + 1,
                latency_ms=turn.elapsed_ms,
                stop_reason=turn.stop_reason,
                input_tokens=turn.usage["input_tokens"],
                output_tokens=turn.usage["output_tokens"],
                cache_write_tokens=turn.usage["cache_write_tokens"],
                cache_read_tokens=turn.usage["cache_read_tokens"],
                continuations=turn.continuations,
                truncated=turn.truncated,
            )
            print(
                f"[anthropic] elapsed: {turn.elapsed_ms}ms (iteration {iteration+1}) | "
                f"stop={log.stop_reason} continuations={turn.continuations} "
                f"truncated={turn.truncated} | "
                f"in={log.input_tokens} cache_read={log.cache_read_tokens} "
                f"cache_write={log.cache_write_tokens} out={log.output_tokens}"
            )
            result.total_latency_ms += turn.elapsed_ms
            result.total_cache_read_tokens += log.cache_read_tokens
            result.total_cache_write_tokens += log.cache_write_tokens
            result.total_input_tokens += log.input_tokens
            result.total_output_tokens += log.output_tokens

            # Branch 1: end_turn — final answer
            if turn.stop_reason == "end_turn":
                text_blocks = [b.text for b in turn.content if b.type == "text"]
                raw_answer = (turn.text_prefix + "\n".join(text_blocks)).strip()
                cleaned_answer, suggestions = _extract_suggestions(raw_answer)
                result.answer = cleaned_answer
                result.next_step_suggestions = suggestions
                result.iterations.append(log)
                result.dax_query = last_dax_query
                result.dax_rows = last_dax_rows
                result.dax_columns = last_dax_columns
                result.visual_hint = last_visual_hint
                return result

            # Branch 2: tool_use — execute DAX
            if turn.stop_reason == "tool_use":
                tool_uses = [b for b in turn.content if b.type == "tool_use"]
                text_blocks = [b.text for b in turn.content if b.type == "text"]
                if turn.text_prefix or text_blocks:
                    pre_tool = turn.text_prefix + (text_blocks[0] if text_blocks else "")
                    log.pre_tool_text = pre_tool[:500]

                # Append assistant turn to messages. When the turn was resumed
                # past max_tokens, the prefilled text is not repeated by the
                # final response, so it is restored here as a leading block.
                assistant_content: List[Any] = list(turn.content)
                if turn.text_prefix:
                    assistant_content.insert(
                        0, {"type": "text", "text": turn.text_prefix}
                    )
                messages.append({"role": "assistant", "content": assistant_content})

                tool_results = []
                dax_latency_total = 0
                for tu in tool_uses:
                    if tu.name != "execute_dax":
                        # Unknown tool — return error to Claude
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tu.id,
                                "content": json.dumps(
                                    {"ok": False, "error": f"unknown tool {tu.name}"}
                                ),
                                "is_error": True,
                            }
                        )
                        continue

                    dax = tu.input.get("query", "")
                    explanation = tu.input.get("explanation_pt", "")
                    visual_hint = tu.input.get("visual_hint")  # may be None today

                    log.dax_executed = dax[:1000]
                    log.dax_explanation = explanation[:500]

                    exec_result = self._execute_dax_safely(dax)
                    log.dax_call_count += 1
                    log.dax_row_count = exec_result.get("row_count")
                    dax_latency_total += exec_result.get("latency_ms") or 0
                    log.dax_latency_ms = dax_latency_total
                    # Claude may emit several execute_dax calls in one turn:
                    # the iteration counts as failed if any of them failed, and
                    # keeps the first error message.
                    if not exec_result.get("ok"):
                        log.dax_ok = False
                        if not log.dax_error:
                            log.dax_error = exec_result.get("error_message", "")[:500]
                    elif log.dax_ok is None:
                        log.dax_ok = True

                    # Remember last successful execution for the final result
                    if exec_result.get("ok"):
                        last_dax_query = dax
                        last_dax_rows = exec_result.get("rows")
                        last_dax_columns = exec_result.get("columns")
                        last_visual_hint = visual_hint

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": json.dumps(exec_result, ensure_ascii=False, default=str),
                            "is_error": not exec_result.get("ok"),
                        }
                    )

                messages.append({"role": "user", "content": tool_results})
                result.iterations.append(log)
                continue

            # Branch 3: still truncated — the continuation budget ran out, or
            # the reply was cut off inside a tool_use block, which cannot be
            # resumed. Return the text produced so far instead of discarding it.
            if turn.stop_reason == "max_tokens":
                text_blocks = [b.text for b in turn.content if b.type == "text"]
                partial = (turn.text_prefix + "\n".join(text_blocks)).strip()
                cleaned_answer, suggestions = _extract_suggestions(partial)
                result.error = (
                    f"response truncated at max_tokens after "
                    f"{turn.continuations} continuation(s)"
                )
                result.error_type = "MaxTokensTruncated"
                result.answer = (
                    f"{cleaned_answer}\n\n_(Resposta truncada por limite de "
                    f"tamanho — pede um recorte de cada vez para o detalhe "
                    f"que falta.)_"
                    if cleaned_answer
                    else (
                        "A resposta excedeu o limite de tamanho antes de "
                        "produzir texto. Divide a pergunta em partes."
                    )
                )
                result.next_step_suggestions = suggestions
                result.dax_query = last_dax_query
                result.dax_rows = last_dax_rows
                result.dax_columns = last_dax_columns
                result.visual_hint = last_visual_hint
                result.iterations.append(log)
                return result

            # Branch 4: unexpected stop reason
            result.error = f"unexpected stop_reason: {turn.stop_reason}"
            result.error_type = "UnexpectedStopReason"
            result.answer = "Erro inesperado no fluxo de geração."
            result.iterations.append(log)
            return result

        # Reached max iterations without end_turn
        result.error = f"max iterations reached ({_MAX_ITERATIONS})"
        result.error_type = "MaxIterationsReached"
        result.answer = (
            "Não consegui chegar a uma resposta dentro do limite de tentativas. "
            "Reformula a pergunta ou tenta novamente."
        )
        result.dax_query = last_dax_query
        result.dax_rows = last_dax_rows
        result.dax_columns = last_dax_columns
        result.visual_hint = last_visual_hint
        return result

    def _execute_dax_safely(self, dax: str) -> Dict[str, Any]:
        """
        Execute DAX and return a JSON-serializable dict.

        On success: {ok: True, row_count, columns, rows[:50], latency_ms}
        On failure: {ok: False, error_type, error_message, context}
        """
        if not dax or not dax.strip():
            return {
                "ok": False,
                "error_type": "ValueError",
                "error_message": "DAX query is empty",
                "context": {},
            }
        validation_error = validate_dax_query(dax)
        if validation_error:
            return {
                "ok": False,
                "error_type": "DaxValidationError",
                "error_message": validation_error,
                "context": {"guard": "evaluate_table_constructor"},
            }
        try:
            result = self._fabric.execute_query(self._dataset_id, dax)
            return {
                "ok": True,
                "row_count": result.row_count,
                "columns": result.columns,
                "rows": result.rows[:_MAX_ROWS_IN_TOOL_RESULT],
                "latency_ms": result.metadata.get("latency_ms"),
            }
        except (FabricAPIError, FabricAuthError, FabricConfigError) as exc:
            return {
                "ok": False,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "context": getattr(exc, "context", {}) or {},
            }
