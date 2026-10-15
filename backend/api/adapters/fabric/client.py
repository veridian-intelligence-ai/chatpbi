"""
Cliente REST mínimo para Microsoft Fabric / Power BI.

Implementa o contrato `BaseDataSourceAdapter`:
- `health_check()` — verifica acesso à API.
- `list_models()` — enumera semantic models do workspace.
- `execute_query()` — executa DAX num dataset específico.
"""

from __future__ import annotations

import os
import time
from collections import Counter
from typing import Any, Dict, List

import httpx

from api.adapters.base import BaseDataSourceAdapter, QueryResult, SemanticModel
from api.adapters.fabric.auth import FabricAuthenticator
from api.adapters.fabric.exceptions import (
    FabricAPIError,
    FabricAuthError,
    FabricConfigError,
)

_POWER_BI_BASE_URL = "https://api.powerbi.com/v1.0/myorg"
_EXECUTE_QUERY_TIMEOUT_SECONDS = 120.0
_DEFAULT_TIMEOUT_SECONDS = 30.0


class FabricClient(BaseDataSourceAdapter):
    """Adapter para a Power BI REST API."""

    def __init__(self, authenticator: FabricAuthenticator) -> None:
        self._authenticator = authenticator

    def _auth_headers(self) -> Dict[str, str]:
        token = self._authenticator.get_token()
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _require_workspace_id() -> str:
        workspace_id = os.getenv("FABRIC_WORKSPACE_ID", "").strip()
        if not workspace_id:
            raise FabricConfigError(
                "FABRIC_WORKSPACE_ID not set",
                context={"missing": ["FABRIC_WORKSPACE_ID"]},
            )
        return workspace_id

    @staticmethod
    def _normalize_column_name(name: str) -> str:
        """
        Nome de display (candidato) para uma coluna de resultado:
        - measure pura '[Total Revenue]' -> 'Total Revenue'
        - coluna qualificada 'dim_brands[brand_name]' -> 'brand_name'
        - qualquer outro caso fica inalterado

        É apenas o *candidato*: o tratamento de colisões entre leafs vive em
        `_build_column_name_map`, que mantém os nomes qualificados quando duas
        colunas colapsariam no mesmo leaf (nunca perde dados em silêncio).
        """
        if len(name) >= 2 and name.endswith("]"):
            open_idx = name.find("[")
            if open_idx != -1:
                inner = name[open_idx + 1 : -1]
                # Conservador: rejeita brackets aninhados/escapados.
                if inner and "[" not in inner and "]" not in inner:
                    return inner
        return name

    @classmethod
    def _build_column_name_map(cls, raw_columns: List[str]) -> Dict[str, str]:
        """
        Mapeia cada coluna crua do resultado para o seu nome de display,
        removendo brackets de tabela/measure ('dim_brands[brand_name]' ->
        'brand_name', '[TREV]' -> 'TREV').

        Collision guard: se duas colunas cruas colapsarem no mesmo leaf, AMBAS
        mantêm o nome qualificado original. Nunca sobrescrevemos a chave de uma
        coluna — dados errados na resposta seriam piores do que um label
        verboso, e o visual apenas skipa (com log) nesse caso raro.
        """
        candidates = [cls._normalize_column_name(name) for name in raw_columns]
        counts = Counter(candidates)
        return {
            raw: (candidate if counts[candidate] == 1 else raw)
            for raw, candidate in zip(raw_columns, candidates)
        }

    def health_check(self) -> bool:
        """Confirma acesso à API listando workspaces visíveis."""
        url = f"{_POWER_BI_BASE_URL}/groups"
        try:
            response = httpx.get(
                url, headers=self._auth_headers(), timeout=_DEFAULT_TIMEOUT_SECONDS
            )
        except httpx.HTTPError as exc:
            print(f"[fabric.client] Fabric health check FAILED: {exc}")
            return False
        except Exception as exc:
            # Inclui FabricAuthError lançado pelo authenticator.
            print(f"[fabric.client] Fabric health check FAILED: {exc}")
            return False

        if response.status_code == 200:
            try:
                workspaces = response.json().get("value", [])
                count = len(workspaces)
            except ValueError:
                count = 0
            print(f"[fabric.client] Fabric health check OK, {count} workspaces visible")
            return True

        print(
            f"[fabric.client] Fabric health check FAILED: HTTP {response.status_code}"
        )
        return False

    def list_models(self) -> List[SemanticModel]:
        """Lista os semantic models (datasets) do workspace configurado."""
        workspace_id = self._require_workspace_id()
        url = f"{_POWER_BI_BASE_URL}/groups/{workspace_id}/datasets"

        try:
            response = httpx.get(
                url, headers=self._auth_headers(), timeout=_DEFAULT_TIMEOUT_SECONDS
            )
        except httpx.HTTPError as exc:
            print(f"[fabric.client] list_models FAILED: {exc}")
            raise FabricAPIError(
                "Network error calling Power BI datasets endpoint",
                context={"error": str(exc)},
            ) from exc

        if response.status_code in (401, 403):
            print(
                f"[fabric.client] list_models FAILED: HTTP {response.status_code} (auth)"
            )
            raise FabricAuthError(
                f"Power BI rejected token with status {response.status_code}",
                context={"status_code": response.status_code, "body": response.text[:500]},
            )

        if response.status_code != 200:
            print(
                f"[fabric.client] list_models FAILED: HTTP {response.status_code}"
            )
            raise FabricAPIError(
                f"Power BI datasets endpoint returned HTTP {response.status_code}",
                context={"status_code": response.status_code, "body": response.text[:500]},
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise FabricAPIError(
                "Power BI datasets response is not valid JSON",
                context={"error": str(exc)},
            ) from exc

        raw_models = payload.get("value", []) or []
        models: List[SemanticModel] = []
        for entry in raw_models:
            if not isinstance(entry, dict):
                continue
            model_id = entry.get("id", "")
            name = entry.get("name", "")
            metadata = {k: v for k, v in entry.items() if k not in {"id", "name"}}
            models.append(
                SemanticModel(
                    id=model_id,
                    name=name,
                    workspace_id=workspace_id,
                    metadata=metadata,
                )
            )

        print(f"[fabric.client] list_models: {len(models)} models found")
        return models

    def execute_query(self, dataset_id: str, dax_query: str) -> QueryResult:
        """Executa uma query DAX contra o dataset indicado."""
        workspace_id = self._require_workspace_id()

        if not dataset_id or not dataset_id.strip():
            raise FabricConfigError(
                "dataset_id is required",
                context={"missing": ["dataset_id"]},
            )

        if not dax_query or not dax_query.strip():
            raise FabricConfigError(
                "dax_query is required and cannot be empty",
                context={"missing": ["dax_query"]},
            )

        url = (
            f"{_POWER_BI_BASE_URL}/groups/{workspace_id}/datasets/"
            f"{dataset_id}/executeQueries"
        )
        body: Dict[str, Any] = {
            "queries": [{"query": dax_query}],
            "serializerSettings": {"includeNulls": True},
        }
        query_preview = dax_query.strip()[:200]

        print(f"[DAX_QUERY]\n{dax_query}\n[/DAX_QUERY]")

        start = time.monotonic()
        try:
            response = httpx.post(
                url,
                headers={**self._auth_headers(), "Content-Type": "application/json"},
                json=body,
                timeout=_EXECUTE_QUERY_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            print(f"[fabric.client] execute_query FAILED: {exc}")
            raise FabricAPIError(
                "Network error calling Power BI executeQueries endpoint",
                context={"error": str(exc), "dataset_id": dataset_id},
            ) from exc

        latency_ms = int((time.monotonic() - start) * 1000)
        status = response.status_code

        if status == 400:
            print("[fabric.client] execute_query FAILED: DAX query invalid (400)")
            raise FabricAPIError(
                "DAX query invalid",
                context={
                    "status_code": status,
                    "body": response.text[:1000],
                    "dataset_id": dataset_id,
                    "dax_query": query_preview,
                },
            )

        if status in (401, 403):
            print(f"[fabric.client] execute_query FAILED: auth error ({status})")
            raise FabricAuthError(
                f"Power BI rejected token with status {status}",
                context={"status_code": status, "body": response.text[:500]},
            )

        if status == 404:
            print("[fabric.client] execute_query FAILED: dataset not found (404)")
            raise FabricAPIError(
                "Dataset not found",
                context={
                    "status_code": status,
                    "dataset_id": dataset_id,
                    "workspace_id": workspace_id,
                },
            )

        if status == 429:
            retry_after = response.headers.get("Retry-After")
            print(
                f"[fabric.client] execute_query FAILED: throttled (429), "
                f"Retry-After={retry_after}"
            )
            ctx: Dict[str, Any] = {"status_code": status}
            if retry_after is not None:
                ctx["retry_after"] = retry_after
            raise FabricAPIError("Throttled by Power BI", context=ctx)

        if 500 <= status < 600:
            print(f"[fabric.client] execute_query FAILED: server error ({status})")
            raise FabricAPIError(
                "Power BI internal error",
                context={"status_code": status, "body": response.text[:500]},
            )

        if status != 200:
            print(f"[fabric.client] execute_query FAILED: HTTP {status}")
            raise FabricAPIError(
                f"Power BI executeQueries returned HTTP {status}",
                context={"status_code": status, "body": response.text[:500]},
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise FabricAPIError(
                "Power BI executeQueries response is not valid JSON",
                context={"error": str(exc)},
            ) from exc

        try:
            tables = payload["results"][0]["tables"]
            raw_rows = tables[0]["rows"]
        except (KeyError, IndexError, TypeError) as exc:
            print(
                f"[fabric.client] execute_query FAILED: malformed response ({exc})"
            )
            raise FabricAPIError(
                "Malformed Power BI executeQueries response",
                context={"response": payload, "error": str(exc)},
            ) from exc

        if not isinstance(raw_rows, list):
            raise FabricAPIError(
                "Malformed Power BI executeQueries response: rows is not a list",
                context={"response": payload},
            )

        if raw_rows:
            first_row = raw_rows[0]
            if not isinstance(first_row, dict):
                raise FabricAPIError(
                    "Malformed Power BI executeQueries response: row is not a dict",
                    context={"response": payload},
                )
            raw_columns = list(first_row.keys())
        else:
            raw_columns = []

        name_map = self._build_column_name_map(raw_columns)
        columns = [name_map[name] for name in raw_columns]
        normalized_rows: List[Dict[str, Any]] = []
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            normalized_rows.append(
                {name_map.get(k, k): v for k, v in row.items()}
            )

        result = QueryResult(
            columns=columns,
            rows=normalized_rows,
            row_count=len(normalized_rows),
            metadata={
                "dataset_id": dataset_id,
                "dax_query": query_preview,
                "latency_ms": latency_ms,
            },
        )

        print(
            f"[fabric.client] execute_query: returned {result.row_count} rows "
            f"in {latency_ms}ms"
        )
        return result
