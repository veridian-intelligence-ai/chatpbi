"""Smoke tests for visual_builder with the active semantic model labels.

Validates that DIMENSION_LABELS and MONEY_LIKE_KEYS include the active model
(Cota parlamentar) and that build_visual_payload renders labels in
Portuguese for its columns.
"""
from __future__ import annotations

from api import visual_builder


def test_dimension_labels_include_model_dimensions() -> None:
    assert visual_builder.DIMENSION_LABELS.get("UF atual") == "UF"
    assert visual_builder.DIMENSION_LABELS.get("Partido na época") == "Partido"
    assert visual_builder.DIMENSION_LABELS.get("CNPJ do fornecedor") == "CNPJ"


def test_dimension_labels_include_generic_time_dimensions() -> None:
    assert visual_builder.DIMENSION_LABELS.get("Ano e mês") == "Mês"
    assert visual_builder.DIMENSION_LABELS.get("year") == "Ano"
    assert visual_builder.DIMENSION_LABELS.get("quarter") == "Trimestre"


def test_dimension_labels_include_model_metrics() -> None:
    assert visual_builder.DIMENSION_LABELS.get("Gasto") == "Gasto (R$)"


def test_money_like_keys_include_model_metrics() -> None:
    assert "Gasto" in visual_builder.MONEY_LIKE_KEYS
    assert "Total gasto" in visual_builder.MONEY_LIKE_KEYS
    assert "Média por deputado" in visual_builder.MONEY_LIKE_KEYS


def test_sap_legacy_labels_still_present() -> None:
    # Backward compatibility — SAP labels must still exist
    assert visual_builder.DIMENSION_LABELS.get("bp_name") == "Fornecedor"
    assert visual_builder.DIMENSION_LABELS.get("amount_open") == "Valor em aberto"


def test_build_visual_payload_renders_top5_deputies() -> None:
    rows = [
        {"Parlamentar": "Deputada A", "Gasto": 811827.21},
        {"Parlamentar": "Deputado B", "Gasto": 742552.44},
        {"Parlamentar": "Deputada C", "Gasto": 696199.18},
        {"Parlamentar": "Deputado D", "Gasto": 670349.78},
        {"Parlamentar": "Deputada E", "Gasto": 659749.55},
    ]
    columns = ["Parlamentar", "Gasto"]
    result = {"ok": True, "rows": rows, "columns": columns}
    hint = {
        "chart_type": "bar",
        "x_field": "Parlamentar",
        "y_field": "Gasto",
        "title": "Os 5 deputados que mais gastaram em 2025",
        "value_format": "currency",
    }

    payload = visual_builder.build_visual_payload(visual_hint=hint, result=result)
    assert payload is not None
    assert payload["visual_type"] == "chart"
    assert payload["chart_type"] == "bar"
    assert payload["x_label"] == "Parlamentar"
    assert payload["y_label"] == "Gasto (R$)"
    assert payload["value_format"] == "currency"
    assert len(payload["data"]) == 5


def test_build_visual_payload_line_chart_evolution() -> None:
    rows = [
        {"Ano e mês": "2025-06", "Gasto": 20123456.0},
        {"Ano e mês": "2025-07", "Gasto": 21987654.0},
        {"Ano e mês": "2025-08", "Gasto": 18654321.0},
    ]
    columns = ["Ano e mês", "Gasto"]
    result = {"ok": True, "rows": rows, "columns": columns}
    hint = {
        "chart_type": "line",
        "x_field": "Ano e mês",
        "y_field": "Gasto",
        "title": "Gasto mês a mês",
        "value_format": "currency",
    }

    payload = visual_builder.build_visual_payload(visual_hint=hint, result=result)
    assert payload is not None
    assert payload["visual_type"] == "chart"
    assert payload["chart_type"] == "line"
    assert payload["x_label"] == "Mês"
    assert payload["y_label"] == "Gasto (R$)"


def test_table_marks_money_columns_and_sends_currency() -> None:
    rows = [
        {"Parlamentar": "Deputada A", "Gasto": 811827.21, "Despesas": 312},
        {"Parlamentar": "Deputado B", "Gasto": 742552.44, "Despesas": 280},
    ]
    result = {"ok": True, "rows": rows, "columns": ["Parlamentar", "Gasto", "Despesas"]}
    hint = {"chart_type": "table", "title": "Gastos por deputado"}

    payload = visual_builder.build_visual_payload(visual_hint=hint, result=result)
    assert payload is not None
    assert payload["visual_type"] == "detail_table"
    assert payload["currency"] == "BRL"
    formats = {col["key"]: col.get("format") for col in payload["columns"]}
    assert formats == {"Parlamentar": None, "Gasto": "currency", "Despesas": None}


def test_chart_payload_carries_model_currency() -> None:
    rows = [{"Parlamentar": "Deputada A", "Gasto": 1.0}]
    result = {"ok": True, "rows": rows, "columns": ["Parlamentar", "Gasto"]}
    hint = {"chart_type": "bar", "x_field": "Parlamentar", "y_field": "Gasto"}
    payload = visual_builder.build_visual_payload(visual_hint=hint, result=result)
    assert payload is not None
    assert payload["currency"] == "BRL"
