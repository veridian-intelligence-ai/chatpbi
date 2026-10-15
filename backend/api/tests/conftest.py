"""Fixtures partilhadas pelos testes do adapter Fabric."""

from __future__ import annotations

import os
import sys
from typing import Dict

import pytest

# Garante que `api` é importável como pacote a partir da raiz do repositório.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


@pytest.fixture
def mock_workspace_id() -> str:
    """UUID falso de workspace para testes que usam FABRIC_WORKSPACE_ID."""
    return "fake-workspace-id-22222222-2222-2222-2222-222222222222"


@pytest.fixture
def mock_env_vars(
    monkeypatch: pytest.MonkeyPatch, mock_workspace_id: str
) -> Dict[str, str]:
    """Define variáveis FABRIC_* falsas para testes."""
    values = {
        "FABRIC_TENANT_ID": "fake-tenant-id-00000000-0000-0000-0000-000000000000",
        "FABRIC_CLIENT_ID": "fake-client-id-11111111-1111-1111-1111-111111111111",
        "FABRIC_CLIENT_SECRET": "fake-client-secret-shhh",
        "FABRIC_WORKSPACE_ID": mock_workspace_id,
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


@pytest.fixture
def mock_token_response() -> Dict[str, object]:
    """Resposta tipo Azure AD para o endpoint de token."""
    return {
        "access_token": "fake-access-token-abc123",
        "token_type": "Bearer",
        "expires_in": 3600,
        "ext_expires_in": 3600,
    }
