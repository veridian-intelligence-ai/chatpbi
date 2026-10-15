"""Modelos Pydantic para respostas tipadas do adapter Fabric."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorkspaceInfo(BaseModel):
    id: str
    name: str
    is_on_dedicated_capacity: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class HealthCheckResult(BaseModel):
    success: bool
    workspaces_visible: int
    latency_ms: int


class DatasetInfo(BaseModel):
    """Power BI dataset metadata."""

    id: str
    name: str
    configured_by: Optional[str] = None
    is_refreshable: Optional[bool] = None
    web_url: Optional[str] = None


class ExecuteQueryRequest(BaseModel):
    """Body sent to executeQueries endpoint."""

    queries: List[Dict[str, str]]
    serializer_settings: Dict[str, Any] = Field(
        default_factory=lambda: {"includeNulls": True}
    )
