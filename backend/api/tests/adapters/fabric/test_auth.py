"""Testes para FabricAuthenticator."""

from __future__ import annotations

import time
from typing import Dict

import pytest
from pytest_httpx import HTTPXMock

from api.adapters.fabric.auth import FabricAuthenticator
from api.adapters.fabric.exceptions import FabricAuthError, FabricConfigError

_TOKEN_URL_PREFIX = "https://login.microsoftonline.com/"


def test_init_succeeds_with_valid_env_vars(mock_env_vars: Dict[str, str]) -> None:
    authenticator = FabricAuthenticator()
    assert authenticator is not None


@pytest.mark.parametrize(
    "missing_var",
    ["FABRIC_TENANT_ID", "FABRIC_CLIENT_ID", "FABRIC_CLIENT_SECRET"],
)
def test_init_raises_when_required_env_var_missing(
    mock_env_vars: Dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    missing_var: str,
) -> None:
    monkeypatch.delenv(missing_var, raising=False)

    with pytest.raises(FabricConfigError) as exc_info:
        FabricAuthenticator()

    assert missing_var in str(exc_info.value)
    assert missing_var in exc_info.value.context.get("missing", [])


def test_init_raises_when_env_var_is_empty(
    mock_env_vars: Dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FABRIC_CLIENT_SECRET", "   ")
    with pytest.raises(FabricConfigError):
        FabricAuthenticator()


def test_get_token_calls_azure_ad_and_returns_access_token(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url=f"{_TOKEN_URL_PREFIX}{mock_env_vars['FABRIC_TENANT_ID']}/oauth2/v2.0/token",
        method="POST",
        json=mock_token_response,
        status_code=200,
    )

    authenticator = FabricAuthenticator()
    token = authenticator.get_token()

    assert token == mock_token_response["access_token"]
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    body = requests[0].read().decode()
    assert "grant_type=client_credentials" in body
    assert "scope=" in body


def test_get_token_returns_cached_token_on_second_call(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url=f"{_TOKEN_URL_PREFIX}{mock_env_vars['FABRIC_TENANT_ID']}/oauth2/v2.0/token",
        method="POST",
        json=mock_token_response,
        status_code=200,
    )

    authenticator = FabricAuthenticator()
    first = authenticator.get_token()
    second = authenticator.get_token()

    assert first == second
    assert len(httpx_mock.get_requests()) == 1


def test_get_token_refreshes_when_cached_token_expired(
    mock_env_vars: Dict[str, str],
    mock_token_response: Dict[str, object],
    httpx_mock: HTTPXMock,
) -> None:
    token_url = f"{_TOKEN_URL_PREFIX}{mock_env_vars['FABRIC_TENANT_ID']}/oauth2/v2.0/token"
    httpx_mock.add_response(url=token_url, method="POST", json=mock_token_response, status_code=200)

    second_response = {**mock_token_response, "access_token": "refreshed-token-xyz"}
    httpx_mock.add_response(url=token_url, method="POST", json=second_response, status_code=200)

    authenticator = FabricAuthenticator()
    first = authenticator.get_token()
    assert first == mock_token_response["access_token"]

    # Força expiração do token em cache.
    authenticator._token_expires_at = time.time() - 1  # type: ignore[attr-defined]

    second = authenticator.get_token()
    assert second == "refreshed-token-xyz"
    assert len(httpx_mock.get_requests()) == 2


def test_get_token_raises_fabric_auth_error_on_http_401(
    mock_env_vars: Dict[str, str],
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url=f"{_TOKEN_URL_PREFIX}{mock_env_vars['FABRIC_TENANT_ID']}/oauth2/v2.0/token",
        method="POST",
        json={"error": "invalid_client"},
        status_code=401,
    )

    authenticator = FabricAuthenticator()
    with pytest.raises(FabricAuthError) as exc_info:
        authenticator.get_token()

    assert exc_info.value.context.get("status_code") == 401


def test_get_token_raises_fabric_auth_error_on_http_500(
    mock_env_vars: Dict[str, str],
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url=f"{_TOKEN_URL_PREFIX}{mock_env_vars['FABRIC_TENANT_ID']}/oauth2/v2.0/token",
        method="POST",
        text="boom",
        status_code=500,
    )

    authenticator = FabricAuthenticator()
    with pytest.raises(FabricAuthError) as exc_info:
        authenticator.get_token()

    assert exc_info.value.context.get("status_code") == 500
