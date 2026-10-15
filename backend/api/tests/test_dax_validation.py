"""Unit tests for the DAX structural guard (`validate_dax_query`).

The guard rejects a table constructor `{ ... }` used as the top-level
EVALUATE expression (which returns anonymous Value1/Value2 columns), while
leaving valid patterns — ROW, SELECTCOLUMNS, SUMMARIZECOLUMNS, TOPN and
`IN { ... }` filters — untouched.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from api.orchestrator import DAXConversationOrchestrator, validate_dax_query

# --- Accepted patterns (return None) --------------------------------------

@pytest.mark.parametrize(
    "dax",
    [
        # ROW with explicit column name (the prescribed single-value pattern)
        'EVALUATE ROW("Gasto", CALCULATE([Total gasto], Despesas[Ano] = 2025))',
        # ROW on its own line (whitespace/newline after EVALUATE)
        'EVALUATE\nROW("Gasto 2025", CALCULATE([Total gasto], Parlamentares[Tipo] = "Deputado(a)"))',
        # SELECTCOLUMNS over a constructor — the `{` is nested, not top-level
        'EVALUATE SELECTCOLUMNS({("Maio", 1), ("Abril", 2)}, "Periodo", [Value1], "Gasto", [Value2])',
        # SUMMARIZECOLUMNS aggregation
        'EVALUATE SUMMARIZECOLUMNS(Parlamentares[Parlamentar], "Gasto", [Total gasto])',
        # TOPN ranking
        "EVALUATE TOPN(5, VALUES(Parlamentares[Parlamentar]), [Total gasto], DESC)",
        # IN { ... } set-membership filter on a month key — legitimate braces
        "EVALUATE CALCULATETABLE(VALUES(Parlamentares[Parlamentar]), "
        "Despesas[Ano] IN {2024, 2025})",
        # IN { ... } on category ids — also legitimate
        "EVALUATE SUMMARIZECOLUMNS(Parlamentares[Parlamentar], "
        "FILTER(ALL(Categorias), Categorias[categoria_id] IN {3, 9, 11, 14}), "
        '"Despesas", [Quantidade de despesas])',
    ],
)
def test_validate_accepts_valid_patterns(dax: str) -> None:
    assert validate_dax_query(dax) is None


# --- Rejected patterns (return an instructive message) --------------------

@pytest.mark.parametrize(
    "dax",
    [
        # single-value constructor
        'EVALUATE { ("Gasto", 48805) }',
        # constructor with no inner whitespace
        'EVALUATE {("Gasto 2025", CALCULATE([Total gasto], Despesas[Ano] = 2025))}',
        # multi-row constructor spread across lines
        'EVALUATE\n{\n    ("2025", CALCULATE([Total gasto], Despesas[Ano] = 2025)),\n'
        '    ("2024", CALCULATE([Total gasto], Despesas[Ano] = 2024))\n}',
        # constructor after a DEFINE block
        'DEFINE MEASURE \'Despesas\'[m] = 1 EVALUATE { ("a", 1) }',
        # keyword is case-insensitive in DAX
        'evaluate { ("lower", 1) }',
    ],
)
def test_validate_rejects_evaluate_table_constructor(dax: str) -> None:
    msg = validate_dax_query(dax)
    assert msg is not None
    # The message must instruct the fix so the retry loop can self-correct
    assert "ROW(" in msg


# --- Integration: guard short-circuits before Fabric ----------------------

def test_execute_dax_safely_rejects_constructor_without_calling_fabric() -> None:
    fabric_mock = MagicMock()
    orchestrator = DAXConversationOrchestrator(
        anthropic_client=MagicMock(),
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )

    result = orchestrator._execute_dax_safely('EVALUATE { ("Gasto", 1) }')

    assert result["ok"] is False
    assert result["error_type"] == "DaxValidationError"
    assert "ROW(" in result["error_message"]
    fabric_mock.execute_query.assert_not_called()


def test_execute_dax_safely_allows_row_and_calls_fabric() -> None:
    fabric_mock = MagicMock()
    fabric_result = MagicMock()
    fabric_result.rows = [{"Gasto": 1}]
    fabric_result.columns = ["Gasto"]
    fabric_result.row_count = 1
    fabric_result.metadata = {"latency_ms": 10}
    fabric_mock.execute_query.return_value = fabric_result

    orchestrator = DAXConversationOrchestrator(
        anthropic_client=MagicMock(),
        fabric_client=fabric_mock,
        dataset_id="dataset-teste",
    )

    result = orchestrator._execute_dax_safely('EVALUATE ROW("Gasto", 1)')

    assert result["ok"] is True
    fabric_mock.execute_query.assert_called_once()
