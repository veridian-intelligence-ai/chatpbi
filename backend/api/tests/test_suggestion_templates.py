"""Unit tests for api.suggestion_templates (modelo activo: Cota parlamentar)."""

from __future__ import annotations

import string
from datetime import datetime
from zoneinfo import ZoneInfo

from api.suggestion_templates import (
    TEMPLATES,
    build_context,
    build_context_dax,
    get_current_month_pt,
    render_templates,
)

_NOW = datetime(2026, 10, 14, 21, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


def _placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def test_templates_pool_size() -> None:
    assert len(TEMPLATES) == 17


def test_templates_only_use_known_placeholders() -> None:
    allowed = {"current_month_pt", "ano_corrente", "ano_anterior", "top_deputado"}
    for template in TEMPLATES:
        assert _placeholders(template) <= allowed, template


def test_get_current_month_pt() -> None:
    assert get_current_month_pt(_NOW) == "Outubro de 2026"


def test_get_current_month_pt_all_months() -> None:
    for month_idx in range(1, 13):
        fake = datetime(2026, month_idx, 15, tzinfo=ZoneInfo("America/Sao_Paulo"))
        assert get_current_month_pt(fake).endswith("de 2026")


def test_build_context_dax_targets_previous_year_deputies() -> None:
    dax = build_context_dax(_NOW)
    assert dax.startswith("EVALUATE")
    assert "TREATAS ( { 2025 }, 'Calendário'[Ano] )" in dax
    assert '"Deputado(a)"' in dax
    assert "[Total gasto]" in dax


def test_build_context_with_rows_resolves_top_deputado() -> None:
    context = build_context([{"Parlamentar": " Deputada Exemplo ", "Gasto": 1.0}], _NOW)
    assert context["top_deputado"] == "Deputada Exemplo"
    assert context["ano_anterior"] == "2025"
    assert context["ano_corrente"] == "2026"
    assert context["current_month_pt"] == "Outubro de 2026"


def test_build_context_without_rows_leaves_top_deputado_out() -> None:
    context = build_context(None, _NOW)
    assert "top_deputado" not in context
    assert context["ano_anterior"] == "2025"


def test_render_templates_returns_requested_count() -> None:
    context = build_context([{"Parlamentar": "Deputada Exemplo"}], _NOW)
    rendered = render_templates(context, count=6)
    assert len(rendered) == 6
    for suggestion in rendered:
        assert "{" not in suggestion and "}" not in suggestion


def test_render_templates_skips_templates_with_missing_placeholders() -> None:
    context = build_context(None, _NOW)  # sem top_deputado
    rendered = render_templates(context, count=len(TEMPLATES))
    with_deputado = [t for t in TEMPLATES if "{top_deputado}" in t]
    assert with_deputado, "pool must have templates that use top_deputado"
    assert len(rendered) == len(TEMPLATES) - len(with_deputado)
    for suggestion in rendered:
        assert "{" not in suggestion and "}" not in suggestion


def test_render_templates_never_exceeds_pool() -> None:
    context = build_context([{"Parlamentar": "Deputada Exemplo"}], _NOW)
    assert len(render_templates(context, count=999)) == len(TEMPLATES)
