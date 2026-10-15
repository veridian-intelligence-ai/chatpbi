"""
Autenticador OAuth2 (client credentials) contra Azure AD para Power BI.

Lê credenciais do ambiente, faz fail-fast se faltarem, e mantém o token
em cache até expirar (com margem de segurança de 60s).
"""

from __future__ import annotations

import os
import time
from typing import Optional

import httpx

from api.adapters.fabric.exceptions import FabricAuthError, FabricConfigError

_TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
_EXPIRATION_SAFETY_BUFFER_SECONDS = 60


def _mask(value: str, keep: int = 8) -> str:
    """Devolve apenas os primeiros `keep` caracteres seguidos de '...' para logs."""
    if not value:
        return "<empty>"
    return f"{value[:keep]}..."


class FabricAuthenticator:
    """OAuth2 client-credentials flow com cache de token em memória."""

    def __init__(self) -> None:
        tenant_id = os.getenv("FABRIC_TENANT_ID", "").strip()
        client_id = os.getenv("FABRIC_CLIENT_ID", "").strip()
        client_secret = os.getenv("FABRIC_CLIENT_SECRET", "").strip()

        # Fail-fast: o serviço não deve arrancar sem credenciais válidas.
        missing = []
        if not tenant_id:
            missing.append("FABRIC_TENANT_ID")
        if not client_id:
            missing.append("FABRIC_CLIENT_ID")
        if not client_secret:
            missing.append("FABRIC_CLIENT_SECRET")

        if missing:
            raise FabricConfigError(
                f"Variáveis de ambiente em falta para o adapter Fabric: {', '.join(missing)}",
                context={"missing": missing},
            )

        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret

        self._cached_token: Optional[str] = None
        self._token_expires_at: float = 0.0

        print(f"[fabric.auth] Fabric authenticator initialized for tenant {_mask(tenant_id)}")

    def _is_token_valid(self) -> bool:
        if not self._cached_token:
            return False
        # Margem de segurança evita usar o token nos últimos segundos de vida útil.
        return time.time() < (self._token_expires_at - _EXPIRATION_SAFETY_BUFFER_SECONDS)

    def _request_new_token(self) -> None:
        url = _TOKEN_URL_TEMPLATE.format(tenant_id=self._tenant_id)
        data = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": _SCOPE,
        }

        try:
            response = httpx.post(url, data=data, timeout=30.0)
        except httpx.HTTPError as exc:
            raise FabricAuthError(
                "Falha de rede ao contactar Azure AD para obter token.",
                context={"error": str(exc)},
            ) from exc

        if response.status_code != 200:
            raise FabricAuthError(
                f"Azure AD devolveu status {response.status_code} ao pedir token.",
                context={"status_code": response.status_code, "body": response.text[:500]},
            )

        try:
            payload = response.json()
            access_token = payload["access_token"]
            expires_in = int(payload.get("expires_in", 3600))
        except (ValueError, KeyError, TypeError) as exc:
            raise FabricAuthError(
                "Resposta de Azure AD não tem o formato esperado.",
                context={"error": str(exc)},
            ) from exc

        self._cached_token = access_token
        self._token_expires_at = time.time() + expires_in

    def get_token(self) -> str:
        """Devolve um token válido, renovando-o se necessário."""
        if self._is_token_valid():
            assert self._cached_token is not None
            return self._cached_token

        is_refresh = self._cached_token is not None
        self._request_new_token()

        assert self._cached_token is not None
        remaining = int(self._token_expires_at - time.time())
        if is_refresh:
            print("[fabric.auth] Fabric token refreshed")
        else:
            print(f"[fabric.auth] Fabric token acquired, expires in {remaining}s")

        return self._cached_token
