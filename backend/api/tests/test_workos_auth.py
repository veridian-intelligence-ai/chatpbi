"""Testes do login alternativo WorkOS AuthKit (integração em paralelo).

O SDK WorkOS e o Postgres são mockados — nenhum teste toca em rede ou BD real.
Mockam-se:
  - auth_server._get_workos_client → cliente WorkOS falso (get_authorization_url
    e authenticate_with_code controlados pelo teste);
  - auth_server.get_conn / release_conn → conexão Postgres falsa.
Segue o molde de test_auth_lockout.py.
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# auth_server vive na raiz do repositório.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Env vars necessárias para `auth_server` importar (fail-fast no módulo).
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
# Config WorkOS de teste (valores falsos; o cliente real é sempre mockado).
os.environ.setdefault("WORKOS_API_KEY", "sk_test")
os.environ.setdefault("WORKOS_CLIENT_ID", "client_test")
os.environ.setdefault(
    "WORKOS_REDIRECT_URI", "https://app.exemplo.com/callback"
)

from fastapi.testclient import TestClient  # noqa: E402

import auth_server  # noqa: E402

# O auth_server lê as WORKOS_* no import; como outro ficheiro de teste pode
# importá-lo primeiro (sem estas vars no ambiente), forçamos os valores no módulo
# aqui — torna estes testes independentes da ordem de import/coleção do pytest.
auth_server.WORKOS_API_KEY = "sk_test"
auth_server.WORKOS_CLIENT_ID = "client_test"
auth_server.WORKOS_REDIRECT_URI = "https://app.exemplo.com/callback"

# TestClient sem context manager → o startup (run_auth_migrations) não dispara,
# por isso não há ligação real à BD no import.
client = TestClient(auth_server.app, raise_server_exceptions=False)


# ─────────────────────────────────────────────
# Fakes
# ─────────────────────────────────────────────

def _fake_workos_client(
    *,
    email="maria@example.com",
    email_verified=True,
    authorization_url="https://api.workos.com/authkit/fake",
):
    """Cliente WorkOS falso com get_authorization_url, authenticate_with_code e
    authenticate_with_password controlados pelo teste."""
    wc = MagicMock()
    wc.user_management.get_authorization_url.return_value = authorization_url
    auth_response = SimpleNamespace(
        user=SimpleNamespace(
            id="user_123",
            email=email,
            email_verified=email_verified,
            first_name="Maria",
            last_name="Silva",
        ),
        organization_id="org_123",
        access_token="at",
        refresh_token="rt",
    )
    wc.user_management.authenticate_with_code.return_value = auth_response
    wc.user_management.authenticate_with_password.return_value = auth_response
    return wc


class _Cursor:
    """Cursor falso: responde ao SELECT do user e regista o INSERT da sessão."""

    def __init__(self, store):
        self.store = store
        self._last = ""

    def execute(self, sql, params=None):
        self._last = " ".join(sql.split())
        if self._last.startswith("INSERT INTO auth.sessions"):
            self.store["session_inserted"] = True
            self.store["session_user_id"] = params[0]
            self.store["session_token"] = params[1]

    def fetchone(self):
        if "FROM auth.users" in self._last:
            return self.store["user_row"]
        return None

    def close(self):
        pass


class _Conn:
    def __init__(self, store):
        self.store = store

    def cursor(self):
        return _Cursor(self.store)

    def commit(self):
        self.store["committed"] = True

    def close(self):
        pass


def _active_user_row():
    # Ordem do SELECT em workos_callback (6 colunas, sem must_change_password):
    # u.id, u.full_name, u.status, c.slug, c.name, c.status
    return (42, "Maria Silva", "active", "demo", "Empresa Demo", "active")


# ─────────────────────────────────────────────
# GET /auth/workos/login
# ─────────────────────────────────────────────

def test_login_redirects_to_authkit():
    wc = _fake_workos_client(authorization_url="https://api.workos.com/authkit/abc")
    with patch.object(auth_server, "_get_workos_client", lambda: wc):
        resp = client.get("/auth/workos/login", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://api.workos.com/authkit/abc"
    # provider="authkit" e o redirect_uri configurado são passados ao SDK.
    _, kwargs = wc.user_management.get_authorization_url.call_args
    assert kwargs["provider"] == "authkit"
    assert kwargs["redirect_uri"] == "https://app.exemplo.com/callback"


def test_login_passes_state_through():
    wc = _fake_workos_client()
    with patch.object(auth_server, "_get_workos_client", lambda: wc):
        resp = client.get(
            "/auth/workos/login", params={"state": "xyz"}, follow_redirects=False
        )
    assert resp.status_code == 302
    _, kwargs = wc.user_management.get_authorization_url.call_args
    assert kwargs["state"] == "xyz"


# ─────────────────────────────────────────────
# POST /auth/workos/callback
# ─────────────────────────────────────────────

def test_callback_happy_path_issues_our_session():
    store = {"user_row": _active_user_row()}
    wc = _fake_workos_client(email="maria@example.com", email_verified=True)
    with patch.object(auth_server, "_get_workos_client", lambda: wc), \
            patch.object(auth_server, "get_conn", lambda: _Conn(store)), \
            patch.object(auth_server, "release_conn", lambda c: None):
        resp = client.post("/auth/workos/callback", json={"code": "abc"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token"]  # token opaco NOSSO emitido
    assert body["client_slug"] == "demo"
    assert body["company_name"] == "Empresa Demo"
    assert body["user_name"] == "Maria Silva"
    # Sessão NOSSA persistida em auth.sessions para o user correcto.
    assert store["session_inserted"] is True
    assert store["session_user_id"] == 42
    assert store["session_token"] == body["token"]
    # O code foi trocado no WorkOS.
    _, kwargs = wc.user_management.authenticate_with_code.call_args
    assert kwargs["code"] == "abc"


def test_callback_unknown_email_rejected_403():
    store = {"user_row": None}  # email sem correspondência em auth.users
    wc = _fake_workos_client(email="ghost@example.com", email_verified=True)
    with patch.object(auth_server, "_get_workos_client", lambda: wc), \
            patch.object(auth_server, "get_conn", lambda: _Conn(store)), \
            patch.object(auth_server, "release_conn", lambda c: None):
        resp = client.post("/auth/workos/callback", json={"code": "abc"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "workos_user_not_provisioned"
    assert store.get("session_inserted") is None  # nenhuma sessão criada


def test_callback_unverified_email_rejected_403():
    store = {"user_row": _active_user_row()}
    wc = _fake_workos_client(email="maria@example.com", email_verified=False)
    with patch.object(auth_server, "_get_workos_client", lambda: wc), \
            patch.object(auth_server, "get_conn", lambda: _Conn(store)), \
            patch.object(auth_server, "release_conn", lambda c: None):
        resp = client.post("/auth/workos/callback", json={"code": "abc"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "workos_email_not_verified"
    assert store.get("session_inserted") is None


def test_callback_unverified_email_allowed_when_relaxed():
    """Com WORKOS_REQUIRE_VERIFIED_EMAIL=false (staging) um email não verificado entra."""
    store = {"user_row": _active_user_row()}
    wc = _fake_workos_client(email="maria@example.com", email_verified=False)
    with patch.object(auth_server, "WORKOS_REQUIRE_VERIFIED_EMAIL", False), \
            patch.object(auth_server, "_get_workos_client", lambda: wc), \
            patch.object(auth_server, "get_conn", lambda: _Conn(store)), \
            patch.object(auth_server, "release_conn", lambda c: None):
        resp = client.post("/auth/workos/callback", json={"code": "abc"})
    assert resp.status_code == 200, resp.text
    assert store["session_inserted"] is True


def test_callback_invalid_code_returns_401():
    wc = MagicMock()
    wc.user_management.authenticate_with_code.side_effect = auth_server.WorkOSError(
        "bad code"
    )
    with patch.object(auth_server, "_get_workos_client", lambda: wc):
        resp = client.post("/auth/workos/callback", json={"code": "expired"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "workos_authentication_failed"


def test_callback_inactive_user_returns_403():
    inactive = (42, "Maria", "suspended", "demo", "Empresa Demo", "active")
    wc = _fake_workos_client()
    with patch.object(auth_server, "_get_workos_client", lambda: wc), \
            patch.object(auth_server, "get_conn", lambda: _Conn({"user_row": inactive})), \
            patch.object(auth_server, "release_conn", lambda c: None):
        resp = client.post("/auth/workos/callback", json={"code": "abc"})
    assert resp.status_code == 403


def test_callback_missing_code_returns_422():
    # code é obrigatório → validação Pydantic devolve 422 antes de qualquer lógica.
    resp = client.post("/auth/workos/callback", json={})
    assert resp.status_code == 422


# ─────────────────────────────────────────────
# Isolamento: WorkOS desconfigurado responde 503 (não 500)
# ─────────────────────────────────────────────

def test_workos_unconfigured_returns_503():
    # Força "desconfigurado": sem client cacheado e sem credenciais.
    with patch.object(auth_server, "_workos_client", None), \
            patch.object(auth_server, "WORKOS_API_KEY", None), \
            patch.object(auth_server, "WORKOS_CLIENT_ID", None):
        resp = client.get("/auth/workos/login", follow_redirects=False)
    assert resp.status_code == 503
    assert resp.json()["detail"] in ("workos_not_configured", "workos_not_available")


# ─────────────────────────────────────────────
# POST /auth/workos/password-login (headless)
# ─────────────────────────────────────────────

def test_password_login_happy_path_issues_our_session():
    store = {"user_row": _active_user_row()}
    wc = _fake_workos_client(email="maria@example.com", email_verified=True)
    with patch.object(auth_server, "_get_workos_client", lambda: wc), \
            patch.object(auth_server, "get_conn", lambda: _Conn(store)), \
            patch.object(auth_server, "release_conn", lambda c: None):
        resp = client.post(
            "/auth/workos/password-login",
            json={"email": "maria@example.com", "password": "secret-pass-10"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token"]
    assert body["client_slug"] == "demo"
    assert body["user_name"] == "Maria Silva"
    assert store["session_inserted"] is True
    _, kwargs = wc.user_management.authenticate_with_password.call_args
    assert kwargs["email"] == "maria@example.com"
    assert kwargs["password"] == "secret-pass-10"


def test_password_login_invalid_credentials_returns_401():
    wc = MagicMock()
    wc.user_management.authenticate_with_password.side_effect = auth_server.WorkOSError(
        "bad credentials"
    )
    with patch.object(auth_server, "_get_workos_client", lambda: wc):
        resp = client.post(
            "/auth/workos/password-login",
            json={"email": "x@y.z", "password": "whatever-10c"},
        )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid_credentials"


def test_password_login_rate_limited_returns_429():
    wc = MagicMock()
    wc.user_management.authenticate_with_password.side_effect = (
        auth_server.RateLimitExceededError("rate limited")
    )
    with patch.object(auth_server, "_get_workos_client", lambda: wc):
        resp = client.post(
            "/auth/workos/password-login",
            json={"email": "x@y.z", "password": "whatever-10c"},
        )
    assert resp.status_code == 429


def test_password_login_unprovisioned_user_returns_403():
    store = {"user_row": None}  # autenticou no WorkOS mas não existe em auth.users
    wc = _fake_workos_client(email="ghost@example.com", email_verified=True)
    with patch.object(auth_server, "_get_workos_client", lambda: wc), \
            patch.object(auth_server, "get_conn", lambda: _Conn(store)), \
            patch.object(auth_server, "release_conn", lambda c: None):
        resp = client.post(
            "/auth/workos/password-login",
            json={"email": "ghost@example.com", "password": "whatever-10c"},
        )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "workos_user_not_provisioned"


def test_password_login_unverified_email_returns_403():
    store = {"user_row": _active_user_row()}
    wc = _fake_workos_client(email="maria@example.com", email_verified=False)
    with patch.object(auth_server, "_get_workos_client", lambda: wc), \
            patch.object(auth_server, "get_conn", lambda: _Conn(store)), \
            patch.object(auth_server, "release_conn", lambda c: None):
        resp = client.post(
            "/auth/workos/password-login",
            json={"email": "maria@example.com", "password": "whatever-10c"},
        )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "workos_email_not_verified"


# ─────────────────────────────────────────────
# POST /auth/workos/forgot-password (anti-enumeração: SEMPRE 200)
# ─────────────────────────────────────────────

def test_forgot_password_triggers_reset_and_returns_200():
    wc = MagicMock()
    with patch.object(auth_server, "_get_workos_client", lambda: wc):
        resp = client.post(
            "/auth/workos/forgot-password", json={"email": "maria@example.com"}
        )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    _, kwargs = wc.user_management.reset_password.call_args
    assert kwargs["email"] == "maria@example.com"


def test_forgot_password_unknown_email_still_returns_200():
    wc = MagicMock()
    wc.user_management.reset_password.side_effect = auth_server.WorkOSError("not found")
    with patch.object(auth_server, "_get_workos_client", lambda: wc):
        resp = client.post(
            "/auth/workos/forgot-password", json={"email": "ghost@example.com"}
        )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ─────────────────────────────────────────────
# POST /auth/workos/reset-password
# ─────────────────────────────────────────────

def test_reset_password_happy_path_returns_200():
    wc = MagicMock()
    with patch.object(auth_server, "_get_workos_client", lambda: wc):
        resp = client.post(
            "/auth/workos/reset-password",
            json={"token": "tok-123", "new_password": "brand-new-123"},
        )
    assert resp.status_code == 200
    _, kwargs = wc.user_management.confirm_password_reset.call_args
    assert kwargs["token"] == "tok-123"
    assert kwargs["new_password"] == "brand-new-123"


def test_reset_password_invalid_token_returns_400():
    wc = MagicMock()
    wc.user_management.confirm_password_reset.side_effect = auth_server.WorkOSError(
        "invalid token"
    )
    with patch.object(auth_server, "_get_workos_client", lambda: wc):
        resp = client.post(
            "/auth/workos/reset-password",
            json={"token": "bad", "new_password": "brand-new-123"},
        )
    assert resp.status_code == 400


def test_reset_password_too_short_returns_400_without_calling_workos():
    wc = MagicMock()
    with patch.object(auth_server, "_get_workos_client", lambda: wc):
        resp = client.post(
            "/auth/workos/reset-password",
            json={"token": "tok", "new_password": "short9chr"},  # 9 caracteres
        )
    assert resp.status_code == 400
    wc.user_management.confirm_password_reset.assert_not_called()
