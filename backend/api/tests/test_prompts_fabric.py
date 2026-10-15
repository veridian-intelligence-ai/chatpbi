"""Unit tests for `api.prompts_fabric`.

These tests cover the static contract of the module — building the system
prompt, loading the model context, and the shape of the Anthropic tool
definition. They do NOT call the Anthropic API.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from api import prompts_fabric


def test_build_system_prompt_returns_non_empty_string() -> None:
    prompt = prompts_fabric.build_system_prompt_fabric()
    assert isinstance(prompt, str)
    assert prompt.strip(), "system prompt must not be blank"


def test_build_system_prompt_includes_expected_sections() -> None:
    prompt = prompts_fabric.build_system_prompt_fabric()
    expected_markers = [
        "Modelo semântico",
        "Glossário",
        "Como escrever o DAX",
        "execute_dax",
        "EVALUATE",
        "Regras operacionais",
    ]
    for marker in expected_markers:
        assert marker in prompt, f"expected '{marker}' in system prompt"


def test_build_system_prompt_blocks_returns_two_blocks() -> None:
    blocks = prompts_fabric.build_system_prompt_blocks()
    assert isinstance(blocks, list)
    assert len(blocks) == 2


def test_second_block_has_cache_control() -> None:
    blocks = prompts_fabric.build_system_prompt_blocks()
    assert blocks[1].get("cache_control") == {"type": "ephemeral"}


def test_first_block_has_no_cache_control() -> None:
    blocks = prompts_fabric.build_system_prompt_blocks()
    assert "cache_control" not in blocks[0]


def test_first_block_contains_prompt_version() -> None:
    blocks = prompts_fabric.build_system_prompt_blocks()
    assert prompts_fabric.PROMPT_VERSION in blocks[0]["text"]


def test_second_block_contains_dax_examples_section_if_file_exists() -> None:
    blocks = prompts_fabric.build_system_prompt_blocks()
    # If dax_examples.md was loaded successfully, expect the section header
    if prompts_fabric._DAX_EXAMPLES:
        assert "Exemplos validados de DAX" in blocks[1]["text"]


def test_second_block_starts_with_model_fundamental_rules() -> None:
    # H.1: the fundamental rules come from the active model package and sit
    # before the model context, like the original REGRA FUNDAMENTAL sections.
    body = prompts_fabric.build_system_prompt_blocks()[1]["text"]
    rules = prompts_fabric._MODEL.FUNDAMENTAL_RULES
    assert rules in body
    assert body.index(rules) < body.index("Contexto completo")


def test_cota_rules_cover_time_and_leaderships() -> None:
    body = prompts_fabric.build_system_prompt_blocks()[1]["text"]
    assert "mês de competência" in body
    assert "meses recentes incompletos" in body
    assert 'Parlamentares[Tipo] = "Deputado(a)"' in body
    assert "Passagem aérea (SIGEPA)" in body


def test_model_context_includes_tables_and_measures() -> None:
    context = prompts_fabric._load_model_context()
    for table in ("Despesas", "Parlamentares", "Categorias", "Estados", "Calendário"):
        assert f"### `{table}`" in context
    for measure in ("[Total gasto]", "[Quantidade de despesas]", "[Último mês com dados]"):
        assert measure in context
    assert "## Relationships" in context


def test_prompt_uses_model_language_and_currency() -> None:
    body = prompts_fabric.build_system_prompt_blocks()[1]["text"]
    assert "português do Brasil" in body
    assert "reais (R$)" in body
    assert "€" not in body


def test_prompt_version_constant_format() -> None:
    assert isinstance(prompts_fabric.PROMPT_VERSION, str)
    assert prompts_fabric.PROMPT_VERSION.startswith("H.")
    assert prompts_fabric.PROMPT_VERSION == "H.1.1"


def test_build_date_context_message_returns_user_role() -> None:
    msg = prompts_fabric.build_date_context_message()
    assert msg["role"] == "user"
    assert isinstance(msg["content"], str)
    assert "Data de hoje" in msg["content"]
    assert "Mês corrente" in msg["content"]


def test_load_dax_examples_returns_string() -> None:
    result = prompts_fabric._load_dax_examples()
    assert isinstance(result, str)


def test_dax_examples_file_exists_with_content() -> None:
    examples_path = (
        Path(prompts_fabric.__file__).parent
        / "semantic_models" / "cota_parlamentar" / "dax_examples.md"
    )
    assert examples_path.exists(), "dax_examples.md must exist after G.2"
    content = examples_path.read_text(encoding="utf-8")
    for n in range(1, 12):
        assert f"Exemplo {n} " in content


def test_dax_examples_cover_same_months_comparison_and_cnpj() -> None:
    examples = prompts_fabric._DAX_EXAMPLES
    # ano corrente contra o anterior, nos mesmos meses
    assert "'Calendário'[Número do mês] <= UltimoMes" in examples
    # empresas agrupadas pelo CNPJ
    assert "Despesas[CNPJ do fornecedor]" in examples
    # nenhum exemplo usa table constructor no EVALUATE
    assert "EVALUATE {" not in examples


def test_build_system_prompt_length_is_reasonable() -> None:
    prompt = prompts_fabric.build_system_prompt_fabric()
    assert 5_000 <= len(prompt) <= 250_000, (
        f"prompt length {len(prompt)} chars outside expected envelope"
    )


def test_execute_dax_tool_has_required_top_level_fields() -> None:
    tool = prompts_fabric.EXECUTE_DAX_TOOL
    assert tool["name"] == "execute_dax"
    assert isinstance(tool["description"], str) and tool["description"].strip()
    assert isinstance(tool["input_schema"], dict)


def test_execute_dax_tool_schema_requires_query_and_explanation() -> None:
    schema = prompts_fabric.EXECUTE_DAX_TOOL["input_schema"]
    assert schema.get("type") == "object"

    properties = schema.get("properties", {})
    assert "query" in properties
    assert "explanation_pt" in properties
    assert properties["query"].get("type") == "string"
    assert properties["explanation_pt"].get("type") == "string"

    required = set(schema.get("required", []))
    assert {"query", "explanation_pt"}.issubset(required)


def test_load_model_context_contains_both_files() -> None:
    context = prompts_fabric._load_model_context()
    # SEMANTIC_MODEL.md header
    assert "Modelo semântico `Cota parlamentar`" in context
    # MODEL_SCHEMA.md header
    assert "MODEL_SCHEMA — `Cota parlamentar`" in context


def test_load_model_context_raises_if_file_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Point the module at an empty directory so the read fails.
    monkeypatch.setattr(prompts_fabric, "_MODEL_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        prompts_fabric._load_model_context()


def test_get_max_retries_returns_two() -> None:
    assert prompts_fabric.get_max_retries() == 4


def test_get_conversation_window_returns_five() -> None:
    assert prompts_fabric.get_conversation_window() == 5


def test_execute_dax_tool_supports_visual_hint() -> None:
    schema = prompts_fabric.EXECUTE_DAX_TOOL["input_schema"]
    properties = schema.get("properties", {})
    assert "visual_hint" in properties

    visual_hint_schema = properties["visual_hint"]
    assert visual_hint_schema.get("type") == "object"

    # visual_hint must NOT be required (it's optional by design)
    required = set(schema.get("required", []))
    assert "visual_hint" not in required

    # Verify visual_hint properties exist
    vh_props = visual_hint_schema.get("properties", {})
    assert "chart_type" in vh_props
    assert "x_field" in vh_props
    assert "y_field" in vh_props
    assert "title" in vh_props
    assert "value_format" in vh_props

    # chart_type must be an enum
    chart_type_enum = vh_props["chart_type"].get("enum", [])
    assert "bar" in chart_type_enum
    assert "line" in chart_type_enum
    assert "kpi" in chart_type_enum
    assert "table" in chart_type_enum
    assert "grouped_bar" in chart_type_enum


def test_execute_dax_tool_description_guides_visual_by_shape() -> None:
    # Issue 4 / G.2.3: the tool description lists the renderable chart types and
    # steers the model by answer shape (rankings -> bar, series -> line). kpi
    # stays a valid chart_type in the enum even though single values no longer
    # auto-suggest it (one data representation per response — number in prose).
    desc = prompts_fabric.EXECUTE_DAX_TOOL["description"]
    for token in ("bar", "line", "kpi", "table", "grouped_bar"):
        assert token in desc, f"tool description must mention '{token}'"
    # The old "omit for single values" guidance must remain gone.
    assert "Omitir para valores únicos" not in desc


def test_system_prompt_has_visual_hint_rule() -> None:
    body = prompts_fabric.build_system_prompt_blocks()[1]["text"]
    assert "visual_hint" in body
    # The rule must explicitly map rankings -> bar and keep grouped_bar around.
    assert "Ranking" in body
    assert "grouped_bar" in body


def test_dax_examples_include_bar_and_line_hints() -> None:
    # Example 3 (ranking) has a bar hint, Example 5 a line hint. These are the
    # few-shots Claude learns from. G.2.3: single values no longer carry a kpi
    # hint — one data representation per response, the number lives in prose.
    examples = prompts_fabric._DAX_EXAMPLES
    assert '"chart_type": "bar"' in examples
    assert '"chart_type": "line"' in examples
    assert '"chart_type": "kpi"' not in examples


def test_build_voice_system_block_returns_text_block() -> None:
    block = prompts_fabric.build_voice_system_block()
    assert block["type"] == "text"
    assert "MODO VOZ" in block["text"]
    assert "markdown" in block["text"].lower()
    # Must NOT have cache_control — voice block is per-call, not cached
    assert "cache_control" not in block


def test_voice_block_forbids_next_step_suggestions() -> None:
    block = prompts_fabric.build_voice_system_block()
    # Voice mode must explicitly forbid suggestions output
    assert "next_step_suggestions" in block["text"]


def test_system_prompt_mentions_next_step_suggestions_marker() -> None:
    prompt = prompts_fabric.build_system_prompt_fabric()
    # The system prompt must instruct Claude to use the exact marker
    assert "[next_step_suggestions]" in prompt


def test_system_prompt_requires_3_suggestions() -> None:
    prompt = prompts_fabric.build_system_prompt_fabric()
    # The rule must mention "3" suggestions somewhere
    # (3 sugestões, três sugestões, etc.)
    text_lower = prompt.lower()
    assert "3 sugest" in text_lower or "três sugest" in text_lower


def test_module_reimport_loads_context_at_import_time() -> None:
    # Reimport and confirm _MODEL_CONTEXT is populated eagerly (not lazy).
    reloaded = importlib.reload(prompts_fabric)
    assert isinstance(reloaded._MODEL_CONTEXT, str)
    assert reloaded._MODEL_CONTEXT.strip()


def test_voice_block_uses_model_examples_and_persona() -> None:
    text = prompts_fabric.build_voice_system_block()["text"]
    assert prompts_fabric._MODEL.VOICE_EXAMPLES in text
    assert prompts_fabric._MODEL.DATA_SUBJECT in text
    assert f"Você é o {prompts_fabric.ASSISTANT_NAME}" in text
