"""Unit tests for DAXConversationOrchestrator.

All external dependencies (Anthropic API and FabricClient) are mocked.
These tests verify the orchestration logic, not the underlying services.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List
from unittest.mock import MagicMock

import anthropic
import pytest

from api.orchestrator import (
    _MAX_ITERATIONS,
    DAXConversationOrchestrator,
    IterationLog,
    OrchestratorResult,
)

# --- Helpers to build fake Anthropic responses ----------------------------

def _make_anthropic_text_response(text: str, usage: Dict[str, int] | None = None) -> Any:
    """Build a fake Anthropic response with stop_reason='end_turn'."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]
    response.usage = MagicMock(**(usage or {"input_tokens": 100, "output_tokens": 30,
                                            "cache_creation_input_tokens": 0,
                                            "cache_read_input_tokens": 0}))
    return response


def _make_anthropic_tool_use_response(
    dax_query: str,
    explanation: str = "test explanation",
    visual_hint: Dict[str, Any] | None = None,
    pre_text: str | None = None,
    usage: Dict[str, int] | None = None,
    tool_use_id: str = "tu_1",
    tool_name: str = "execute_dax",
) -> Any:
    """Build a fake Anthropic response with stop_reason='tool_use'."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = tool_use_id
    tool_block.name = tool_name
    tool_block.input = {"query": dax_query, "explanation_pt": explanation}
    if visual_hint is not None:
        tool_block.input["visual_hint"] = visual_hint

    content: List[Any] = []
    if pre_text:
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = pre_text
        content.append(text_block)
    content.append(tool_block)

    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = content
    response.usage = MagicMock(**(usage or {"input_tokens": 100, "output_tokens": 50,
                                            "cache_creation_input_tokens": 0,
                                            "cache_read_input_tokens": 34500}))
    return response


def _make_fabric_query_result(rows, columns, latency_ms=1234, row_count=None):
    """Build a fake QueryResult-like object."""
    result = MagicMock()
    result.rows = rows
    result.columns = columns
    result.row_count = row_count if row_count is not None else len(rows)
    result.metadata = {"latency_ms": latency_ms}
    return result


# --- Construction / validation --------------------------------------------

def test_orchestrator_requires_non_empty_dataset_id() -> None:
    with pytest.raises(ValueError):
        DAXConversationOrchestrator(
            anthropic_client=MagicMock(),
            fabric_client=MagicMock(),
            dataset_id="",
        )


def test_orchestrator_rejects_empty_user_message() -> None:
    orchestrator = DAXConversationOrchestrator(
        anthropic_client=MagicMock(),
        fabric_client=MagicMock(),
        dataset_id="dataset-teste",
    )
    result = orchestrator.run(user_message="")
    assert result.error == "empty_user_message"
    assert result.answer == "Pergunta vazia."


# --- Happy path: 2 iterations (tool_use → end_turn) -----------------------

def test_happy_path_two_iterations() -> None:
    anthropic_mock = MagicMock()
    fabric_mock = MagicMock()

    # Iter 1: Claude returns tool_use
    iter1 = _make_anthropic_tool_use_response(
        dax_query="EVALUATE ROW(\"Gasto\", 48805)",
        explanation="Test gasto",
        usage={"input_tokens": 200, "output_tokens": 150,
               "cache_creation_input_tokens": 34500, "cache_read_input_tokens": 0},
    )
    # Iter 2: Claude returns end_turn with answer
    iter2 = _make_anthropic_text_response(
        "Em 2025, o gasto foi de R$ 48.805.",
        usage={"input_tokens": 250, "output_tokens": 30,
               "cache_creation_input_tokens": 0, "cache_read_input_tokens": 34500},
    )
    anthropic_mock.messages.create.side_effect = [iter1, iter2]

    # Fabric returns 1 row
    fabric_mock.execute_query.return_value = _make_fabric_query_result(
        rows=[{"Gasto": 48805}],
        columns=["Gasto"],
        latency_ms=1234,
    )

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=anthropic_mock,
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )
    result = orchestrator.run("Quanto foi gasto em 2025?")

    assert result.error is None
    assert "48.805" in result.answer
    assert result.dax_query == "EVALUATE ROW(\"Gasto\", 48805)"
    assert result.dax_columns == ["Gasto"]
    assert result.dax_rows == [{"Gasto": 48805}]
    assert len(result.iterations) == 2
    assert result.total_cache_read_tokens == 34500
    assert result.total_cache_write_tokens == 34500
    # Totais de input/output somados das iterações (O.1), simétricos com cache.
    assert result.total_input_tokens == 450  # 200 + 250
    assert result.total_output_tokens == 180  # 150 + 30
    assert fabric_mock.execute_query.call_count == 1


# --- Per-iteration [anthropic] log includes usage tokens ------------------

def test_anthropic_log_includes_usage_tokens(capsys) -> None:
    anthropic_mock = MagicMock()
    fabric_mock = MagicMock()

    iter1 = _make_anthropic_tool_use_response(
        dax_query="EVALUATE ROW(\"Gasto\", 1)",
        usage={"input_tokens": 200, "output_tokens": 150,
               "cache_creation_input_tokens": 34500, "cache_read_input_tokens": 0},
    )
    iter2 = _make_anthropic_text_response(
        "resposta final",
        usage={"input_tokens": 250, "output_tokens": 30,
               "cache_creation_input_tokens": 0, "cache_read_input_tokens": 34500},
    )
    anthropic_mock.messages.create.side_effect = [iter1, iter2]
    fabric_mock.execute_query.return_value = _make_fabric_query_result(
        rows=[{"Gasto": 1}], columns=["Gasto"],
    )

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=anthropic_mock,
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )
    orchestrator.run("Quanto foi gasto?")

    out = capsys.readouterr().out
    # Iteration 1 was a tool_use response (cache write on first call).
    assert (
        "(iteration 1) | stop=tool_use continuations=0 truncated=False | "
        "in=200 cache_read=0 cache_write=34500 out=150"
    ) in out
    # Iteration 2 was the end_turn response (cache read on follow-up call).
    assert (
        "(iteration 2) | stop=end_turn continuations=0 truncated=False | "
        "in=250 cache_read=34500 cache_write=0 out=30"
    ) in out


# --- DAX execution failure: error returned to Claude in tool_result -------

def test_dax_failure_returns_error_to_claude() -> None:
    from api.adapters.fabric import FabricAPIError

    anthropic_mock = MagicMock()
    fabric_mock = MagicMock()

    iter1 = _make_anthropic_tool_use_response(
        dax_query="EVALUATE INVALID_DAX",
    )
    iter2 = _make_anthropic_text_response("Erro corrigido — resposta final.")
    anthropic_mock.messages.create.side_effect = [iter1, iter2]

    fabric_mock.execute_query.side_effect = FabricAPIError(
        "DAX query invalid",
        context={"status_code": 400},
    )

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=anthropic_mock,
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )
    result = orchestrator.run("pergunta com DAX inválido")

    # Verify the second call to Anthropic received the error in tool_result
    second_call = anthropic_mock.messages.create.call_args_list[1]
    messages_in_second_call = second_call.kwargs["messages"]
    user_with_tool_result = messages_in_second_call[-1]
    assert user_with_tool_result["role"] == "user"
    tool_result_block = user_with_tool_result["content"][0]
    assert tool_result_block["type"] == "tool_result"
    assert tool_result_block["is_error"] is True
    result_content = json.loads(tool_result_block["content"])
    assert result_content["ok"] is False
    assert result_content["error_type"] == "FabricAPIError"

    # Final answer was still returned (Claude formatted on iter 2)
    assert "Erro corrigido" in result.answer


# --- Max iterations exhausted ---------------------------------------------

def test_max_iterations_returns_graceful_error() -> None:
    anthropic_mock = MagicMock()
    fabric_mock = MagicMock()

    # Always return tool_use — Claude never decides to stop
    anthropic_mock.messages.create.return_value = _make_anthropic_tool_use_response(
        dax_query="EVALUATE ROW(\"x\", 1)",
    )
    fabric_mock.execute_query.return_value = _make_fabric_query_result(
        rows=[{"x": 1}], columns=["x"],
    )

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=anthropic_mock,
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )
    result = orchestrator.run("loop infinito de teste")

    assert result.error_type == "MaxIterationsReached"
    assert "limite de tentativas" in result.answer
    assert len(result.iterations) == _MAX_ITERATIONS


# --- Visual hint propagation ----------------------------------------------

def test_visual_hint_is_captured_when_provided() -> None:
    anthropic_mock = MagicMock()
    fabric_mock = MagicMock()

    visual_hint = {
        "chart_type": "bar",
        "x_field": "Parlamentar",
        "y_field": "Gasto",
        "title": "Top 5 marcas",
    }
    iter1 = _make_anthropic_tool_use_response(
        dax_query="EVALUATE TOPN(...)",
        visual_hint=visual_hint,
    )
    iter2 = _make_anthropic_text_response("Top 5 marcas: ...")
    anthropic_mock.messages.create.side_effect = [iter1, iter2]
    fabric_mock.execute_query.return_value = _make_fabric_query_result(
        rows=[{"Parlamentar": "Deputada A", "Gasto": 11827851}],
        columns=["Parlamentar", "Gasto"],
    )

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=anthropic_mock,
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )
    result = orchestrator.run("Top 5 marcas")
    assert result.visual_hint == visual_hint


# --- Unknown tool name handled gracefully ---------------------------------

def test_unknown_tool_name_returns_error_to_claude() -> None:
    anthropic_mock = MagicMock()
    fabric_mock = MagicMock()

    iter1 = _make_anthropic_tool_use_response(
        dax_query="ignored",
        tool_name="some_unknown_tool",
    )
    iter2 = _make_anthropic_text_response("Não consigo usar essa ferramenta.")
    anthropic_mock.messages.create.side_effect = [iter1, iter2]

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=anthropic_mock,
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )
    orchestrator.run("pergunta")
    # Fabric was never called for the unknown tool
    fabric_mock.execute_query.assert_not_called()
    # Tool result with error was passed back to Claude
    second_call = anthropic_mock.messages.create.call_args_list[1]
    tool_result_block = second_call.kwargs["messages"][-1]["content"][0]
    assert tool_result_block["is_error"] is True


# --- Conversation history is included in messages ------------------------

def test_conversation_history_is_prepended() -> None:
    anthropic_mock = MagicMock()
    fabric_mock = MagicMock()
    anthropic_mock.messages.create.return_value = _make_anthropic_text_response(
        "resposta direta sem tool"
    )

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=anthropic_mock,
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )
    history = [
        {"role": "user", "content": "Pergunta anterior"},
        {"role": "assistant", "content": "Resposta anterior"},
    ]
    orchestrator.run("Nova pergunta", conversation_history=history)

    call = anthropic_mock.messages.create.call_args
    messages = call.kwargs["messages"]
    # Order: date context, history user, history assistant, current user
    assert len(messages) == 4
    assert messages[0]["role"] == "user"  # date context is user role
    assert "Data de hoje" in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "Pergunta anterior"}
    assert messages[2] == {"role": "assistant", "content": "Resposta anterior"}
    assert messages[3] == {"role": "user", "content": "Nova pergunta"}


# --- Conversation history filters invalid roles ---------------------------

def test_conversation_history_filters_invalid_roles() -> None:
    anthropic_mock = MagicMock()
    fabric_mock = MagicMock()
    anthropic_mock.messages.create.return_value = _make_anthropic_text_response("ok")

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=anthropic_mock,
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )
    history = [
        {"role": "user", "content": "válido"},
        {"role": "system", "content": "inválido — não deve aparecer"},
        {"role": "assistant", "content": "válido"},
    ]
    orchestrator.run("nova", conversation_history=history)

    messages = anthropic_mock.messages.create.call_args.kwargs["messages"]
    contents = [m.get("content") for m in messages]
    assert "inválido — não deve aparecer" not in contents


# --- extra_system_blocks are appended ------------------------------------

def test_extra_system_blocks_are_appended() -> None:
    anthropic_mock = MagicMock()
    fabric_mock = MagicMock()
    anthropic_mock.messages.create.return_value = _make_anthropic_text_response("ok")

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=anthropic_mock,
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )
    voice_block = {"type": "text", "text": "Modo voz: responde sem markdown."}
    orchestrator.run("pergunta", extra_system_blocks=[voice_block])

    system_arg = anthropic_mock.messages.create.call_args.kwargs["system"]
    # Original G.2 blocks (2) + voice block (1)
    assert len(system_arg) == 3
    assert system_arg[-1]["text"] == "Modo voz: responde sem markdown."


# --- Anthropic API error handled gracefully -------------------------------

def test_anthropic_api_error_returns_graceful_error() -> None:
    import httpx

    anthropic_mock = MagicMock()
    fabric_mock = MagicMock()
    # Simulate an APIError from the SDK
    api_error = anthropic.APIError(
        message="rate limit",
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
        body=None,
    )
    anthropic_mock.messages.create.side_effect = api_error

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=anthropic_mock,
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )
    result = orchestrator.run("pergunta")
    assert result.error is not None
    assert result.error_type == "APIError"
    assert "Erro temporário" in result.answer


# --- DAX rows capped to MAX_ROWS_IN_TOOL_RESULT --------------------------

def test_dax_rows_capped_in_tool_result() -> None:
    from api.orchestrator import _MAX_ROWS_IN_TOOL_RESULT

    anthropic_mock = MagicMock()
    fabric_mock = MagicMock()
    iter1 = _make_anthropic_tool_use_response(dax_query="EVALUATE BIG")
    iter2 = _make_anthropic_text_response("resposta")
    anthropic_mock.messages.create.side_effect = [iter1, iter2]

    big_rows = [{"x": i} for i in range(200)]
    fabric_mock.execute_query.return_value = _make_fabric_query_result(
        rows=big_rows, columns=["x"], row_count=200,
    )

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=anthropic_mock,
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )
    orchestrator.run("pergunta")

    # The tool_result sent back to Claude should have capped rows
    second_call = anthropic_mock.messages.create.call_args_list[1]
    tool_result = second_call.kwargs["messages"][-1]["content"][0]
    parsed = json.loads(tool_result["content"])
    assert len(parsed["rows"]) == _MAX_ROWS_IN_TOOL_RESULT
    # But row_count reflects the true total
    assert parsed["row_count"] == 200


# --- OrchestratorResult.to_payload is JSON-serializable ------------------

def test_extract_suggestions_parses_marker_block() -> None:
    from api.orchestrator import _extract_suggestions

    raw = """Em 2025, o gasto foi de R$ 48.805.

[next_step_suggestions]
- Top 5 marcas em Maio 2026
- Comparação Abril vs Maio
- Gasto por categoria"""

    cleaned, suggestions = _extract_suggestions(raw)
    assert "48.805" in cleaned
    assert "[next_step_suggestions]" not in cleaned
    assert suggestions == [
        "Top 5 marcas em Maio 2026",
        "Comparação Abril vs Maio",
        "Gasto por categoria",
    ]


def test_extract_suggestions_handles_missing_marker() -> None:
    from api.orchestrator import _extract_suggestions

    raw = "Resposta sem bloco de sugestões."
    cleaned, suggestions = _extract_suggestions(raw)
    assert cleaned == "Resposta sem bloco de sugestões."
    assert suggestions == []


def test_extract_suggestions_caps_at_3() -> None:
    from api.orchestrator import _extract_suggestions

    raw = """Resposta.

[next_step_suggestions]
- um
- dois
- três
- quatro
- cinco"""

    _, suggestions = _extract_suggestions(raw)
    assert len(suggestions) == 3
    assert suggestions == ["um", "dois", "três"]


def test_extract_suggestions_accepts_asterisk_bullets() -> None:
    from api.orchestrator import _extract_suggestions

    raw = """Resposta.

[next_step_suggestions]
* primeira
* segunda
* terceira"""

    _, suggestions = _extract_suggestions(raw)
    assert suggestions == ["primeira", "segunda", "terceira"]


def test_orchestrator_populates_next_step_suggestions() -> None:
    anthropic_mock = MagicMock()
    fabric_mock = MagicMock()

    final_text = """Em 2025, o gasto foi de R$ 48.805.

[next_step_suggestions]
- Top 5 marcas em Maio 2026
- Comparação Abril vs Maio
- Gasto por categoria"""

    iter1 = _make_anthropic_text_response(final_text)
    anthropic_mock.messages.create.return_value = iter1

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=anthropic_mock,
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )
    result = orchestrator.run("Quanto foi gasto?")

    assert "[next_step_suggestions]" not in result.answer
    assert len(result.next_step_suggestions) == 3
    assert result.next_step_suggestions[0] == "Top 5 marcas em Maio 2026"


def test_to_payload_includes_next_step_suggestions() -> None:
    result = OrchestratorResult(
        answer="ok",
        next_step_suggestions=["s1", "s2", "s3"],
    )
    payload = result.to_payload()
    assert payload["next_step_suggestions"] == ["s1", "s2", "s3"]


def test_orchestrator_result_default_next_step_suggestions_is_empty_list() -> None:
    result = OrchestratorResult(answer="x")
    assert result.next_step_suggestions == []


def test_to_payload_is_json_serializable() -> None:
    result = OrchestratorResult(
        answer="ok",
        dax_query="EVALUATE",
        dax_rows=[{"k": "v"}],
        iterations=[
            IterationLog(
                iteration=1, latency_ms=100, stop_reason="end_turn",
                input_tokens=10, output_tokens=20,
                cache_write_tokens=0, cache_read_tokens=5,
            )
        ],
    )
    payload = result.to_payload()
    # Must be JSON-serializable
    json.dumps(payload, default=str)
    assert payload["answer"] == "ok"
    assert payload["dax_query"] == "EVALUATE"
    assert payload["prompt_version"]  # non-empty


# --- max_tokens: truncated replies are resumed, never discarded -----------

def _make_anthropic_truncated_text_response(
    text: str, usage: Dict[str, int] | None = None
) -> Any:
    """Build a fake text-only response cut off at max_tokens."""
    response = _make_anthropic_text_response(text, usage=usage)
    response.stop_reason = "max_tokens"
    return response


def test_truncated_reply_is_resumed_and_answer_is_complete() -> None:
    anthropic_mock = MagicMock()
    fabric_mock = MagicMock()
    anthropic_mock.messages.create.side_effect = [
        _make_anthropic_truncated_text_response("Evolução do gasto em 2026:"),
        _make_anthropic_text_response(" Janeiro 1.234, Fevereiro 2.345."),
    ]

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=anthropic_mock,
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )
    result = orchestrator.run("Evolução do gasto mês a mês em 2026?")

    assert result.error is None
    assert result.answer == (
        "Evolução do gasto em 2026: Janeiro 1.234, Fevereiro 2.345."
    )
    # The truncated text is replayed as an assistant prefill on the retry.
    resumed_messages = anthropic_mock.messages.create.call_args_list[1].kwargs[
        "messages"
    ]
    assert resumed_messages[-1] == {
        "role": "assistant",
        "content": "Evolução do gasto em 2026:",
    }
    # Both calls are one logical iteration, with usage summed across them.
    assert len(result.iterations) == 1
    assert result.iterations[0].continuations == 1
    assert result.iterations[0].output_tokens == 60


def test_truncated_reply_resumed_into_tool_use_keeps_prefix() -> None:
    anthropic_mock = MagicMock()
    fabric_mock = MagicMock()
    anthropic_mock.messages.create.side_effect = [
        _make_anthropic_truncated_text_response("Vou consultar o modelo"),
        _make_anthropic_tool_use_response(dax_query='EVALUATE ROW("Gasto", 1)'),
        _make_anthropic_text_response("Foi 1 despesa."),
    ]
    fabric_mock.execute_query.return_value = _make_fabric_query_result(
        rows=[{"Gasto": 1}], columns=["Gasto"],
    )

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=anthropic_mock,
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )
    result = orchestrator.run("Quanto foi gasto?")

    assert result.answer == "Foi 1 despesa."
    # The assistant turn sent back to Claude must carry the prefilled text,
    # which the resumed response does not repeat.
    final_messages = anthropic_mock.messages.create.call_args_list[2].kwargs["messages"]
    assistant_turn = [m for m in final_messages if m["role"] == "assistant"][0]
    assert assistant_turn["content"][0] == {
        "type": "text",
        "text": "Vou consultar o modelo",
    }


def test_truncation_beyond_budget_returns_partial_answer() -> None:
    from api.orchestrator import _MAX_CONTINUATIONS

    anthropic_mock = MagicMock()
    fabric_mock = MagicMock()
    anthropic_mock.messages.create.return_value = (
        _make_anthropic_truncated_text_response("Resposta muito longa")
    )

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=anthropic_mock,
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )
    result = orchestrator.run("Analisa tudo")

    assert result.error_type == "MaxTokensTruncated"
    # The text produced so far is returned, not replaced by an error message.
    assert result.answer.startswith("Resposta muito longa")
    assert "truncada" in result.answer
    assert anthropic_mock.messages.create.call_count == _MAX_CONTINUATIONS + 1


def test_truncated_tool_use_is_never_executed() -> None:
    anthropic_mock = MagicMock()
    fabric_mock = MagicMock()
    truncated = _make_anthropic_tool_use_response(dax_query="EVALUATE ROW(")
    truncated.stop_reason = "max_tokens"
    anthropic_mock.messages.create.return_value = truncated

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=anthropic_mock,
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )
    result = orchestrator.run("Quanto foi gasto?")

    # A tool_use cut mid-JSON cannot be resumed and must not reach Fabric.
    fabric_mock.execute_query.assert_not_called()
    assert result.error_type == "MaxTokensTruncated"
    assert anthropic_mock.messages.create.call_count == 1


def test_parallel_tool_calls_are_all_counted() -> None:
    anthropic_mock = MagicMock()
    fabric_mock = MagicMock()

    first = _make_anthropic_tool_use_response(
        dax_query='EVALUATE ROW("A", 1)', tool_use_id="tu_1",
    )
    second_block = MagicMock()
    second_block.type = "tool_use"
    second_block.id = "tu_2"
    second_block.name = "execute_dax"
    second_block.input = {"query": 'EVALUATE ROW("B", 2)', "explanation_pt": "b"}
    first.content = list(first.content) + [second_block]

    anthropic_mock.messages.create.side_effect = [
        first,
        _make_anthropic_text_response("pronto"),
    ]
    fabric_mock.execute_query.return_value = _make_fabric_query_result(
        rows=[{"A": 1}], columns=["A"], latency_ms=500,
    )

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=anthropic_mock,
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )
    result = orchestrator.run("Duas métricas?")

    assert fabric_mock.execute_query.call_count == 2
    # One iteration, two DAX calls: latency is summed, not overwritten.
    assert result.iterations[0].dax_call_count == 2
    assert result.iterations[0].dax_latency_ms == 1000


def test_max_tokens_above_nonstreaming_ceiling_is_clamped() -> None:
    from api.orchestrator import _MAX_NONSTREAMING_TOKENS

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=MagicMock(),
        fabric_client=MagicMock(),
        dataset_id="dataset-teste",
        max_tokens=64_000,
    )
    assert orchestrator._max_tokens == _MAX_NONSTREAMING_TOKENS


def test_truncated_tool_use_salvages_the_complete_calls() -> None:
    """A turn cut mid-tool_use still runs the calls that did complete."""
    anthropic_mock = MagicMock()
    fabric_mock = MagicMock()

    # Claude emitted one full query and was cut while writing the second.
    truncated = _make_anthropic_tool_use_response(
        dax_query='EVALUATE ROW("A", 1)',
        pre_text="Vou correr as duas queries.",
        tool_use_id="tu_1",
    )
    incomplete = MagicMock()
    incomplete.type = "tool_use"
    incomplete.id = "tu_2"
    incomplete.name = "execute_dax"
    incomplete.input = {"query": 'EVALUATE ROW("B",'}
    truncated.content = list(truncated.content) + [incomplete]
    truncated.stop_reason = "max_tokens"

    anthropic_mock.messages.create.side_effect = [
        truncated,
        _make_anthropic_text_response("A=1 e B=2."),
    ]
    fabric_mock.execute_query.return_value = _make_fabric_query_result(
        rows=[{"A": 1}], columns=["A"],
    )

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=anthropic_mock,
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )
    result = orchestrator.run("Duas métricas?")

    # Only the complete call reaches Fabric; the incomplete one is dropped.
    assert fabric_mock.execute_query.call_count == 1
    assert result.iterations[0].dax_call_count == 1
    assert result.iterations[0].stop_reason == "tool_use"
    assert result.iterations[0].truncated is True
    # The turn is not an error: the loop carries on to a complete answer.
    assert result.error is None
    assert result.answer == "A=1 e B=2."
    # The assistant turn replayed to Claude must not carry the dropped block.
    followup = anthropic_mock.messages.create.call_args_list[1].kwargs["messages"]
    assistant_turn = [m for m in followup if m["role"] == "assistant"][0]
    assert [b.id for b in assistant_turn["content"] if b.type == "tool_use"] == ["tu_1"]
