from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from api.semantic_models import get_active_model

_MODEL = get_active_model()

MAX_BAR_POINTS = 24
MAX_LINE_POINTS = 36
MAX_DETAIL_ROWS = 50
MAX_DETAIL_COLUMNS = 8

DIMENSION_LABELS: Dict[str, str] = {
    # SAP B1 (legacy — kept for backward compatibility)
    "bp_name": "Fornecedor",
    "bp_group_name": "Grupo de parceiro",
    "branch_name": "Filial",
    "payment_method": "Método de pagamento",
    "payment_terms": "Condição de pagamento",
    "title_status": "Status",
    "title_side": "Lado do título",
    "dataset_type": "Tipo de conjunto",
    "document_code": "Documento",
    "document_type": "Tipo",
    "due_date": "Vencimento",
    "document_date": "Data do documento",
    "posting_date": "Data de lançamento",
    "settlement_date": "Data de liquidação",
    "amount_open": "Valor em aberto",
    "amount_paid": "Valor pago",
    "amount_original": "Valor original",
    "reference_nf": "NF",
    "comments": "Observações",
    "bp_code": "Código do parceiro",
    "period_start": "Período",
    "aging_bucket": "Faixa de atraso",
    "result_value": "Valor",

    # Generic time dimensions
    "year": "Ano",
    "month": "Mês",
    "quarter": "Trimestre",

    # Active semantic model (api/semantic_models/<modelo>/__init__.py)
    **_MODEL.DIMENSION_LABELS,
}

DATE_LIKE_KEYS = {"due_date", "document_date", "posting_date", "settlement_date", "period_start"}
CURRENCY_CODE = getattr(_MODEL, "CURRENCY_CODE", "BRL")
MONEY_LIKE_KEYS = {
    # SAP B1 (legacy)
    "amount_open", "amount_paid", "amount_original", "result_value",
    # Active semantic model
    *_MODEL.MONEY_LIKE_KEYS,
}

_STRIP_SUFFIXES = ("_pct", "_value", "_count", "_total", "_amt", "_amount", "_qty", "_num")

_TERM_TRANSLATIONS: Dict[str, str] = {
    "concentration": "Concentração",
    "pct": "Percentual",
    "percent": "Percentual",
    "percentage": "Percentual",
    "count": "Quantidade",
    "total": "Total",
    "avg": "Média",
    "average": "Média",
    "max": "Máximo",
    "min": "Mínimo",
    "net": "Líquido",
    "gross": "Bruto",
    "balance": "Saldo",
    "amount": "Valor",
    "value": "Valor",
    "flow": "Fluxo",
    "cash": "Caixa",
    "overdue": "Vencido",
    "open": "Em aberto",
    "paid": "Pago",
    "received": "Recebido",
    "receivable": "A receber",
    "payable": "A pagar",
    "revenue": "Receita",
    "expense": "Despesa",
    "budget": "Orçamento",
    "forecast": "Previsão",
    "actual": "Realizado",
    "variance": "Variação",
    "ratio": "Índice",
    "rate": "Taxa",
    "share": "Participação",
    "rank": "Ranking",
    "period": "Período",
    "month": "Mês",
    "year": "Ano",
    "quarter": "Trimestre",
    "day": "Dia",
    "date": "Data",
    "start": "Início",
    "end": "Fim",
    "bucket": "Faixa",
    "group": "Grupo",
    "name": "Nome",
    "code": "Código",
    "type": "Tipo",
    "status": "Status",
    "result": "Resultado",
    "metric": "Indicador",
    "payment": "Pagamento",
    "receipt": "Recebimento",
    "top": "Top",
}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _humanize_key(key: str) -> str:
    """Converte qualquer nome de coluna técnico para português legível."""
    cleaned = key
    for suffix in _STRIP_SUFFIXES:
        if cleaned.endswith(suffix) and len(cleaned) > len(suffix):
            cleaned = cleaned[: -len(suffix)]
            break
    parts = cleaned.lower().split("_")
    translated = [_TERM_TRANSLATIONS.get(part, part) for part in parts]
    result = " ".join(translated)
    return result.capitalize()


def _label_for(key: Optional[str]) -> str:
    if not key:
        return "Indicador"
    if key in DIMENSION_LABELS:
        return DIMENSION_LABELS[key]
    return _humanize_key(key)


def _format_display_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if key in MONEY_LIKE_KEYS and _is_number(value):
        return float(value)
    if key in DATE_LIKE_KEYS and isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
            return dt.strftime("%d/%m/%Y")
        except Exception:
            return value
    return value


def _first_numeric_key(row: Dict[str, Any], preferred: Optional[str] = None) -> Optional[str]:
    if preferred and _is_number(row.get(preferred)):
        return preferred
    if "result_value" in row and _is_number(row.get("result_value")):
        return "result_value"
    for key, value in row.items():
        if _is_number(value):
            return key
    return None


def _infer_chart_type(rows: List[Dict[str, Any]], columns: List[str]) -> str:
    """Infere o tipo de visual mais adequado com base nos dados retornados."""
    if not rows:
        return "table"

    numeric_cols = [c for c in columns if _is_number(rows[0].get(c))]
    non_numeric_cols = [c for c in columns if not _is_number(rows[0].get(c))]

    # Uma linha com pelo menos uma coluna numérica -> KPI
    if len(rows) == 1 and numeric_cols:
        return "kpi"

    # Poucas linhas com 1 categórica + 1 numérica -> multi-KPI
    if len(rows) <= 6 and len(non_numeric_cols) == 1 and len(numeric_cols) == 1:
        return "kpi"

    # 2 dimensões categóricas + 1 numérica -> grouped bar
    if len(non_numeric_cols) >= 2 and numeric_cols:
        return "grouped_bar"

    # Coluna de período -> linha temporal
    if "period_start" in columns:
        return "line"

    return "bar"


def _build_kpi(
    rows: List[Dict[str, Any]],
    y_field: Optional[str],
    title: Optional[str],
    columns: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    if not rows:
        return None

    all_cols = columns or list(rows[0].keys())
    numeric_cols = [c for c in all_cols if _is_number(rows[0].get(c))]
    non_numeric_cols = [c for c in all_cols if not _is_number(rows[0].get(c))]

    # Multi-KPI: múltiplas linhas com label + valor
    if len(rows) > 1 and non_numeric_cols and numeric_cols:
        label_key = non_numeric_cols[0]
        value_key = y_field if (y_field and _is_number(rows[0].get(y_field))) else numeric_cols[0]

        cards = []
        for row in rows:
            label = row.get(label_key)
            value = row.get(value_key)
            if label is not None and _is_number(value):
                cards.append({"label": str(label), "value": float(value)})

        if cards:
            return {
                "visual_type": "kpi_cards",
                "title": title or _label_for(value_key),
                "cards": cards,
            }

    # KPI único
    first_row = rows[0]
    value_key = _first_numeric_key(first_row, y_field)
    if value_key is None:
        return None

    value = first_row.get(value_key)
    if not _is_number(value):
        return None

    return {
        "visual_type": "kpi_cards",
        "title": title or _label_for(value_key),
        "cards": [{"label": _label_for(value_key), "value": float(value)}],
    }


def _build_chart(
    rows: List[Dict[str, Any]],
    columns: List[str],
    x_field: Optional[str],
    y_field: Optional[str],
    title: Optional[str],
    chart_type: str,
) -> Optional[Dict[str, Any]]:
    if not rows:
        return None

    non_numeric_cols = [c for c in columns if not _is_number(rows[0].get(c))]
    numeric_cols = [c for c in columns if _is_number(rows[0].get(c))]

    if not x_field:
        x_field = non_numeric_cols[0] if non_numeric_cols else columns[0]
    if not y_field:
        y_field = numeric_cols[0] if numeric_cols else None

    if not x_field or not y_field:
        return None

    # Grouped bar: 2 dimensões categóricas + 1 numérica
    series_field = None
    if len(non_numeric_cols) >= 2 and chart_type in ("bar", "grouped_bar"):
        series_field = next(
            (c for c in non_numeric_cols if c != x_field),
            None,
        )

    cap = MAX_LINE_POINTS if chart_type == "line" else MAX_BAR_POINTS

    if series_field:
        series_values = list(dict.fromkeys(
            str(row.get(series_field)) for row in rows if row.get(series_field) is not None
        ))
        x_values = list(dict.fromkeys(
            str(row.get(x_field)) for row in rows if row.get(x_field) is not None
        ))

        data_index: Dict[tuple, float] = {}
        for row in rows:
            x_val = str(row.get(x_field)) if row.get(x_field) is not None else None
            s_val = str(row.get(series_field)) if row.get(series_field) is not None else None
            y_val = row.get(y_field)
            if x_val and s_val and _is_number(y_val):
                data_index[(x_val, s_val)] = float(y_val)

        grouped_data = []
        for x_val in x_values[:cap]:
            entry: Dict[str, Any] = {x_field: x_val}
            for s_val in series_values:
                entry[s_val] = data_index.get((x_val, s_val), 0.0)
            grouped_data.append(entry)

        if not grouped_data:
            return None

        return {
            "visual_type": "chart",
            "chart_type": "grouped_bar",
            "title": title or _label_for(y_field),
            "x_field": x_field,
            "series": series_values,
            "x_label": _label_for(x_field),
            "y_label": _label_for(y_field),
            "data": grouped_data,
        }

    # Bar ou line simples
    cleaned: List[Dict[str, Any]] = []
    for row in rows[:cap]:
        x_value = row.get(x_field)
        y_value = row.get(y_field)
        if x_value is None or not _is_number(y_value):
            continue
        cleaned.append({x_field: x_value, y_field: float(y_value)})

    if not cleaned:
        return None

    return {
        "visual_type": "chart",
        "chart_type": chart_type if chart_type != "grouped_bar" else "bar",
        "title": title or _label_for(y_field),
        "x_field": x_field,
        "y_field": y_field,
        "x_label": _label_for(x_field),
        "y_label": _label_for(y_field),
        "data": cleaned,
    }


def _build_table(
    rows: List[Dict[str, Any]],
    columns: List[str],
    title: Optional[str],
) -> Optional[Dict[str, Any]]:
    if not rows or not columns:
        return None

    selected_columns = columns[:MAX_DETAIL_COLUMNS]

    visual_columns = []
    for col in selected_columns:
        column: Dict[str, Any] = {"key": col, "label": _label_for(col)}
        if col in MONEY_LIKE_KEYS:
            column["format"] = "currency"
        visual_columns.append(column)

    visual_rows: List[Dict[str, Any]] = []
    for row in rows[:MAX_DETAIL_ROWS]:
        item: Dict[str, Any] = {}
        for col in selected_columns:
            item[col] = _format_display_value(col, row.get(col))
        visual_rows.append(item)

    if not visual_rows:
        return None

    return {
        "visual_type": "detail_table",
        "title": title or "Detalhamento",
        "columns": visual_columns,
        "data": visual_rows,
        "row_count": len(rows),
    }


def build_visual_payload(
    visual_hint: Optional[Dict[str, Any]],
    result: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not result.get("ok"):
        return None

    rows = result.get("rows") or []
    columns = result.get("columns") or []

    if not rows:
        return None

    hint = visual_hint or {}
    chart_type = hint.get("chart_type")
    x_field = hint.get("x_field")
    y_field = hint.get("y_field")
    title = hint.get("title")
    value_format = hint.get("value_format")

    if not chart_type:
        chart_type = _infer_chart_type(rows, columns)

    # Inferência automática de value_format
    EXPLICIT_MONEY_COLS = {"amount_open", "amount_paid", "amount_original"}
    PERCENT_TITLE_TERMS = {
        "concentra", "percentual", "percent", "participa",
        "taxa", "propor", "share", "ratio", "distribui",
    }
    if not value_format:
        effective_y = y_field or ""
        effective_title = (title or "").lower()

        if effective_y in EXPLICIT_MONEY_COLS:
            value_format = "currency"
        elif any(t in effective_y for t in ("_pct", "_percent", "_rate", "_ratio", "_share")):
            value_format = "percent"
        elif any(t in effective_title for t in PERCENT_TITLE_TERMS):
            value_format = "percent"

    payload = None

    if chart_type == "kpi":
        payload = _build_kpi(rows, y_field, title, columns)
    elif chart_type in ("bar", "grouped_bar"):
        payload = _build_chart(rows, columns, x_field, y_field, title, chart_type)
    elif chart_type == "line":
        payload = _build_chart(rows, columns, x_field, y_field, title, "line")
    elif chart_type == "table":
        payload = _build_table(rows, columns, title)

    if payload:
        # Moeda do modelo activo: o frontend formata os valores monetários.
        payload["currency"] = CURRENCY_CODE

    if payload and value_format:
        payload["value_format"] = value_format

        # Normaliza percentuais: se value_format="percent" e o valor está entre 0 e 1,
        # multiplica por 100 — convenção universal de apresentação.
        if value_format == "percent":
            if payload.get("visual_type") == "kpi_cards":
                for card in payload.get("cards", []):
                    v = card.get("value")
                    if isinstance(v, float) and 0 < v <= 1:
                        card["value"] = round(v * 100, 4)
            elif payload.get("visual_type") == "chart":
                y_field = payload.get("y_field")
                if y_field:
                    for row in payload.get("data", []):
                        v = row.get(y_field)
                        if isinstance(v, float) and 0 < v <= 1:
                            row[y_field] = round(v * 100, 4)

    return payload
