"""Testes para FabricClient."""

from __future__ import annotations

import json
from typing import Dict

import pytest
from pytest_httpx import HTTPXMock

from api.adapters.fabric.auth import FabricAuthenticator
from api.adapters.fabric.client import FabricClient
from api.adapters.fabric.exceptions import (
    FabricAPIError,
    FabricAuthError,
    FabricConfigError,
)

_TOKEN_URL_PREFIX = "https://login.microsoftonline.com/"
_POWER_BI_BASE_URL = "https://api.powerbi.com/v1.0/myorg"
_GROUPS_URL = f"{_POWER_BI_BASE_URL}/groups"


def _build_client(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    httpx_mock: HTTPXMock,
) -> FabricClient:
    httpx_mock.add_response(
        url=f"{_TOKEN_URL_PREFIX}{mock_env_vars['FABRIC_TENANT_ID']}/oauth2/v2.0/token",
        method="POST",
        json=mock_token_response,
        status_code=200,
    )
    return FabricClient(FabricAuthenticator())


def _datasets_url(workspace_id: str) -> str:
    return f"{_POWER_BI_BASE_URL}/groups/{workspace_id}/datasets"


def _execute_queries_url(workspace_id: str, dataset_id: str) -> str:
    return (
        f"{_POWER_BI_BASE_URL}/groups/{workspace_id}/datasets/"
        f"{dataset_id}/executeQueries"
    )


# ─────────────────────────────────────────────────────────────────────────────
# health_check (existing tests)
# ─────────────────────────────────────────────────────────────────────────────


def test_health_check_returns_true_on_http_200(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    httpx_mock: HTTPXMock,
) -> None:
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    httpx_mock.add_response(
        url=_GROUPS_URL,
        method="GET",
        json={"value": [{"id": "w1"}, {"id": "w2"}]},
        status_code=200,
    )

    assert client.health_check() is True


@pytest.mark.parametrize("status_code", [401, 500])
def test_health_check_returns_false_on_error_status(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    httpx_mock: HTTPXMock,
    status_code: int,
) -> None:
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    httpx_mock.add_response(
        url=_GROUPS_URL,
        method="GET",
        text="error",
        status_code=status_code,
    )

    assert client.health_check() is False


def test_health_check_sends_bearer_token_header(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    httpx_mock: HTTPXMock,
) -> None:
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    httpx_mock.add_response(
        url=_GROUPS_URL,
        method="GET",
        json={"value": []},
        status_code=200,
    )

    client.health_check()

    groups_requests = [r for r in httpx_mock.get_requests() if str(r.url) == _GROUPS_URL]
    assert len(groups_requests) == 1
    assert groups_requests[0].headers["Authorization"] == (
        f"Bearer {mock_token_response['access_token']}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# list_models
# ─────────────────────────────────────────────────────────────────────────────


def test_list_models_returns_semantic_models_on_http_200(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    mock_workspace_id: str,
    httpx_mock: HTTPXMock,
) -> None:
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    httpx_mock.add_response(
        url=_datasets_url(mock_workspace_id),
        method="GET",
        json={
            "value": [
                {
                    "id": "ds-1",
                    "name": "Sales Model",
                    "configuredBy": "user@example.com",
                    "isRefreshable": True,
                },
                {
                    "id": "ds-2",
                    "name": "Marketing Model",
                    "configuredBy": "user@example.com",
                    "isRefreshable": False,
                },
            ]
        },
        status_code=200,
    )

    models = client.list_models()

    assert len(models) == 2
    assert models[0].id == "ds-1"
    assert models[0].name == "Sales Model"
    assert models[0].workspace_id == mock_workspace_id
    assert models[0].metadata.get("configuredBy") == "user@example.com"
    assert models[0].metadata.get("isRefreshable") is True
    assert models[1].id == "ds-2"
    assert models[1].name == "Marketing Model"


def test_list_models_returns_empty_list_on_empty_value(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    mock_workspace_id: str,
    httpx_mock: HTTPXMock,
) -> None:
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    httpx_mock.add_response(
        url=_datasets_url(mock_workspace_id),
        method="GET",
        json={"value": []},
        status_code=200,
    )

    assert client.list_models() == []


def test_list_models_raises_config_error_when_workspace_id_missing(
    mock_env_vars: Dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FabricClient(FabricAuthenticator())
    monkeypatch.delenv("FABRIC_WORKSPACE_ID", raising=False)

    with pytest.raises(FabricConfigError) as exc_info:
        client.list_models()

    assert "FABRIC_WORKSPACE_ID" in str(exc_info.value)


def test_list_models_raises_api_error_on_http_401(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    mock_workspace_id: str,
    httpx_mock: HTTPXMock,
) -> None:
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    httpx_mock.add_response(
        url=_datasets_url(mock_workspace_id),
        method="GET",
        text="unauthorized",
        status_code=401,
    )

    # 401 maps to FabricAuthError (subclass of FabricError but distinct from FabricAPIError).
    with pytest.raises((FabricAuthError, FabricAPIError)) as exc_info:
        client.list_models()

    assert exc_info.value.context.get("status_code") == 401


def test_list_models_raises_api_error_on_http_500(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    mock_workspace_id: str,
    httpx_mock: HTTPXMock,
) -> None:
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    httpx_mock.add_response(
        url=_datasets_url(mock_workspace_id),
        method="GET",
        text="boom",
        status_code=500,
    )

    with pytest.raises(FabricAPIError) as exc_info:
        client.list_models()

    assert exc_info.value.context.get("status_code") == 500


def test_list_models_sends_bearer_token_header(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    mock_workspace_id: str,
    httpx_mock: HTTPXMock,
) -> None:
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    url = _datasets_url(mock_workspace_id)
    httpx_mock.add_response(url=url, method="GET", json={"value": []}, status_code=200)

    client.list_models()

    datasets_requests = [r for r in httpx_mock.get_requests() if str(r.url) == url]
    assert len(datasets_requests) == 1
    assert datasets_requests[0].headers["Authorization"] == (
        f"Bearer {mock_token_response['access_token']}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# execute_query
# ─────────────────────────────────────────────────────────────────────────────


_DATASET_ID = "dataset-abc-def"


def _execute_response_body() -> Dict[str, object]:
    return {
        "results": [
            {
                "tables": [
                    {
                        "rows": [
                            {"Parlamentar": "Brand A", "[Total Revenue]": 12500.0},
                            {"Parlamentar": "Brand B", "[Total Revenue]": 8300.0},
                        ]
                    }
                ]
            }
        ]
    }


def test_execute_query_returns_query_result_on_http_200(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    mock_workspace_id: str,
    httpx_mock: HTTPXMock,
) -> None:
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    httpx_mock.add_response(
        url=_execute_queries_url(mock_workspace_id, _DATASET_ID),
        method="POST",
        json=_execute_response_body(),
        status_code=200,
    )

    result = client.execute_query(_DATASET_ID, "EVALUATE Sales")

    assert result.row_count == 2
    assert result.columns == ["Parlamentar", "Total Revenue"]
    assert result.rows[0] == {"Parlamentar": "Brand A", "Total Revenue": 12500.0}
    assert result.rows[1] == {"Parlamentar": "Brand B", "Total Revenue": 8300.0}
    assert result.metadata["dataset_id"] == _DATASET_ID
    assert result.metadata["dax_query"] == "EVALUATE Sales"
    assert isinstance(result.metadata["latency_ms"], int)


def test_execute_query_normalizes_measure_column_names(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    mock_workspace_id: str,
    httpx_mock: HTTPXMock,
) -> None:
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    httpx_mock.add_response(
        url=_execute_queries_url(mock_workspace_id, _DATASET_ID),
        method="POST",
        json={
            "results": [
                {
                    "tables": [
                        {
                            "rows": [
                                {"[Total Revenue]": 100.0, "[Count]": 5},
                            ]
                        }
                    ]
                }
            ]
        },
        status_code=200,
    )

    result = client.execute_query(_DATASET_ID, "EVALUATE ROW(\"a\", 1)")

    assert result.columns == ["Total Revenue", "Count"]
    assert result.rows[0] == {"Total Revenue": 100.0, "Count": 5}


# --- column name normalization (table-qualified + collision guard) ----------

def test_normalize_column_name_strips_table_prefix() -> None:
    assert FabricClient._normalize_column_name("Parlamentares[Parlamentar]") == "Parlamentar"


def test_normalize_column_name_strips_pure_measure() -> None:
    assert FabricClient._normalize_column_name("[Total gasto]") == "Total gasto"


def test_normalize_column_name_leaves_plain_name() -> None:
    assert FabricClient._normalize_column_name("Parlamentar") == "Parlamentar"


def test_normalize_column_name_ignores_nested_brackets() -> None:
    # Conservador: não tocar em brackets aninhados/escapados.
    assert FabricClient._normalize_column_name("weird[a][b]") == "weird[a][b]"


def test_build_column_name_map_mixed_case() -> None:
    raw = ["Parlamentares[Parlamentar]", "[Total gasto]", "'Calendário'[Ano e mês]"]
    assert FabricClient._build_column_name_map(raw) == {
        "Parlamentares[Parlamentar]": "Parlamentar",
        "[Total gasto]": "Total gasto",
        "'Calendário'[Ano e mês]": "Ano e mês",
    }


def test_build_column_name_map_collision_keeps_qualified() -> None:
    # Dois leafs colapsariam em 'Parlamentar' -> manter ambos qualificados.
    raw = ["Despesas[Parlamentar]", "Parlamentares[Parlamentar]", "[Total gasto]"]
    assert FabricClient._build_column_name_map(raw) == {
        "Despesas[Parlamentar]": "Despesas[Parlamentar]",
        "Parlamentares[Parlamentar]": "Parlamentares[Parlamentar]",
        "[Total gasto]": "Total gasto",
    }


def test_execute_query_strips_table_qualified_column_names(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    mock_workspace_id: str,
    httpx_mock: HTTPXMock,
) -> None:
    # The Issue 4 root cause: Fabric returns 'Parlamentares[Parlamentar]'.
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    httpx_mock.add_response(
        url=_execute_queries_url(mock_workspace_id, _DATASET_ID),
        method="POST",
        json={
            "results": [
                {
                    "tables": [
                        {
                            "rows": [
                                {"Parlamentares[Parlamentar]": "Deputada A", "[Total gasto]": 11827851.0},
                                {"Parlamentares[Parlamentar]": "Deputado B", "[Total gasto]": 7425525.0},
                            ]
                        }
                    ]
                }
            ]
        },
        status_code=200,
    )

    result = client.execute_query(_DATASET_ID, "EVALUATE TOPN(...)")

    assert result.columns == ["Parlamentar", "Total gasto"]
    assert result.rows[0] == {"Parlamentar": "Deputada A", "Total gasto": 11827851.0}
    assert result.rows[1] == {"Parlamentar": "Deputado B", "Total gasto": 7425525.0}


def test_execute_query_keeps_qualified_names_on_leaf_collision(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    mock_workspace_id: str,
    httpx_mock: HTTPXMock,
) -> None:
    # Distinct values under two same-leaf columns: neither may be dropped.
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    httpx_mock.add_response(
        url=_execute_queries_url(mock_workspace_id, _DATASET_ID),
        method="POST",
        json={
            "results": [
                {
                    "tables": [
                        {
                            "rows": [
                                {
                                    "Despesas[Parlamentar]": "ACC_STAKE",
                                    "Parlamentares[Parlamentar]": "BRAND_STAKE",
                                    "[Total gasto]": 10.0,
                                },
                            ]
                        }
                    ]
                }
            ]
        },
        status_code=200,
    )

    result = client.execute_query(_DATASET_ID, "EVALUATE ...")

    assert result.columns == [
        "Despesas[Parlamentar]",
        "Parlamentares[Parlamentar]",
        "Total gasto",
    ]
    assert result.rows[0] == {
        "Despesas[Parlamentar]": "ACC_STAKE",
        "Parlamentares[Parlamentar]": "BRAND_STAKE",
        "Total gasto": 10.0,
    }


def test_execute_query_returns_empty_rows_gracefully(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    mock_workspace_id: str,
    httpx_mock: HTTPXMock,
) -> None:
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    httpx_mock.add_response(
        url=_execute_queries_url(mock_workspace_id, _DATASET_ID),
        method="POST",
        json={"results": [{"tables": [{"rows": []}]}]},
        status_code=200,
    )

    result = client.execute_query(_DATASET_ID, "EVALUATE ROW(\"a\", 1)")

    assert result.row_count == 0
    assert result.rows == []
    assert result.columns == []


def test_execute_query_raises_config_error_on_empty_dataset_id(
    mock_env_vars: Dict[str, str],
) -> None:
    client = FabricClient(FabricAuthenticator())

    with pytest.raises(FabricConfigError):
        client.execute_query("", "EVALUATE ROW(\"a\", 1)")


def test_execute_query_raises_config_error_on_whitespace_dax_query(
    mock_env_vars: Dict[str, str],
) -> None:
    client = FabricClient(FabricAuthenticator())

    with pytest.raises(FabricConfigError):
        client.execute_query(_DATASET_ID, "   \n  ")


def test_execute_query_raises_config_error_when_workspace_id_missing(
    mock_env_vars: Dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FabricClient(FabricAuthenticator())
    monkeypatch.delenv("FABRIC_WORKSPACE_ID", raising=False)

    with pytest.raises(FabricConfigError):
        client.execute_query(_DATASET_ID, "EVALUATE ROW(\"a\", 1)")


def test_execute_query_raises_api_error_on_http_400_with_body_in_context(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    mock_workspace_id: str,
    httpx_mock: HTTPXMock,
) -> None:
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    httpx_mock.add_response(
        url=_execute_queries_url(mock_workspace_id, _DATASET_ID),
        method="POST",
        text="DAX syntax error near token 'FOO'",
        status_code=400,
    )

    with pytest.raises(FabricAPIError) as exc_info:
        client.execute_query(_DATASET_ID, "EVALUATE FOO BAR")

    assert "DAX query invalid" in str(exc_info.value)
    assert exc_info.value.context.get("status_code") == 400
    assert "DAX syntax error" in exc_info.value.context.get("body", "")


def test_execute_query_raises_auth_error_on_http_401(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    mock_workspace_id: str,
    httpx_mock: HTTPXMock,
) -> None:
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    httpx_mock.add_response(
        url=_execute_queries_url(mock_workspace_id, _DATASET_ID),
        method="POST",
        text="unauthorized",
        status_code=401,
    )

    with pytest.raises(FabricAuthError) as exc_info:
        client.execute_query(_DATASET_ID, "EVALUATE ROW(\"a\", 1)")

    assert exc_info.value.context.get("status_code") == 401


def test_execute_query_raises_api_error_on_http_404(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    mock_workspace_id: str,
    httpx_mock: HTTPXMock,
) -> None:
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    httpx_mock.add_response(
        url=_execute_queries_url(mock_workspace_id, _DATASET_ID),
        method="POST",
        text="not found",
        status_code=404,
    )

    with pytest.raises(FabricAPIError) as exc_info:
        client.execute_query(_DATASET_ID, "EVALUATE ROW(\"a\", 1)")

    assert "Dataset not found" in str(exc_info.value)
    assert exc_info.value.context.get("status_code") == 404


def test_execute_query_raises_api_error_on_http_429_with_retry_after(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    mock_workspace_id: str,
    httpx_mock: HTTPXMock,
) -> None:
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    httpx_mock.add_response(
        url=_execute_queries_url(mock_workspace_id, _DATASET_ID),
        method="POST",
        text="too many requests",
        status_code=429,
        headers={"Retry-After": "30"},
    )

    with pytest.raises(FabricAPIError) as exc_info:
        client.execute_query(_DATASET_ID, "EVALUATE ROW(\"a\", 1)")

    assert "Throttled" in str(exc_info.value)
    assert exc_info.value.context.get("retry_after") == "30"


def test_execute_query_raises_api_error_on_http_500(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    mock_workspace_id: str,
    httpx_mock: HTTPXMock,
) -> None:
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    httpx_mock.add_response(
        url=_execute_queries_url(mock_workspace_id, _DATASET_ID),
        method="POST",
        text="boom",
        status_code=500,
    )

    with pytest.raises(FabricAPIError) as exc_info:
        client.execute_query(_DATASET_ID, "EVALUATE ROW(\"a\", 1)")

    assert "Power BI internal error" in str(exc_info.value)
    assert exc_info.value.context.get("status_code") == 500


def test_execute_query_raises_api_error_on_malformed_response(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    mock_workspace_id: str,
    httpx_mock: HTTPXMock,
) -> None:
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    httpx_mock.add_response(
        url=_execute_queries_url(mock_workspace_id, _DATASET_ID),
        method="POST",
        json={"results": []},  # missing tables
        status_code=200,
    )

    with pytest.raises(FabricAPIError) as exc_info:
        client.execute_query(_DATASET_ID, "EVALUATE ROW(\"a\", 1)")

    assert "Malformed" in str(exc_info.value)


def test_execute_query_sends_correct_json_body_and_records_latency(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    mock_workspace_id: str,
    httpx_mock: HTTPXMock,
) -> None:
    client = _build_client(mock_env_vars, mock_token_response, httpx_mock)
    url = _execute_queries_url(mock_workspace_id, _DATASET_ID)
    httpx_mock.add_response(
        url=url,
        method="POST",
        json=_execute_response_body(),
        status_code=200,
    )

    dax = "EVALUATE Sales"
    result = client.execute_query(_DATASET_ID, dax)

    posts = [r for r in httpx_mock.get_requests() if str(r.url) == url]
    assert len(posts) == 1
    sent_body = json.loads(posts[0].read().decode())
    assert sent_body["queries"] == [{"query": dax}]
    assert sent_body["serializerSettings"] == {"includeNulls": True}
    assert posts[0].headers["Authorization"] == (
        f"Bearer {mock_token_response['access_token']}"
    )
    assert "latency_ms" in result.metadata
    assert result.metadata["latency_ms"] >= 0
