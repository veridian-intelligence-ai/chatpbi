import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Env vars required for `main` to import successfully.
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("FABRIC_DEFAULT_DATASET_ID", "test-dataset")
os.environ.setdefault("FABRIC_TENANT_ID", "test-tenant")
os.environ.setdefault("FABRIC_CLIENT_ID", "test-client")
os.environ.setdefault("FABRIC_CLIENT_SECRET", "test-secret")
os.environ.setdefault("FABRIC_WORKSPACE_ID", "test-workspace")

# `main` calls run_migrations() at import time, which would hit Postgres.
with patch("conversation_store.run_migrations"):
    from main import app

from fastapi.testclient import TestClient

client = TestClient(app, raise_server_exceptions=False)

PROTECTED_ENDPOINTS = [
    ("POST", "/chat/v2", {"session_id": "test", "message": "test"}),
    ("POST", "/chat/voice", {"session_id": "test", "message": "test"}),
    ("POST", "/chat/reset", {"session_id": "test", "message": "test"}),
    ("GET", "/conversations", None),
    ("POST", "/suggestions", {}),
    ("POST", "/stt", None),
    ("POST", "/tts", {"text": "test"}),
]


@pytest.mark.parametrize("method,path,body", PROTECTED_ENDPOINTS)
def test_endpoint_requires_auth(method, path, body):
    """All protected endpoints must return 403 or 401 without token."""
    if method == "GET":
        response = client.get(path)
    else:
        response = client.post(path, json=body or {})
    assert response.status_code in (401, 403)


def test_health_is_public():
    """Health check must remain public."""
    response = client.get("/health")
    assert response.status_code == 200


# ─────────────────────────────────────────────
# Ownership enforcement (step 3)
# ─────────────────────────────────────────────

import main as main_module  # noqa: E402

OWNERSHIP_ENDPOINTS = [
    ("GET", "/conversations/foo/messages", None),
    ("PATCH", "/conversations/foo/title", {"title": "x"}),
    ("DELETE", "/conversations/foo", None),
    ("POST", "/chat/reset", {"session_id": "foo", "message": "x"}),
    ("POST", "/chat/v2", {"session_id": "foo", "message": "x"}),
    ("POST", "/chat/voice", {"session_id": "foo", "message": "x"}),
]


@pytest.fixture
def fake_user():
    """Override get_current_user so we can hit the endpoints past auth."""
    app.dependency_overrides[main_module.get_current_user] = lambda: {
        "user_id": 42,
        "email": "a@b.c",
        "full_name": "Test",
        "role": "member",
        "client_id": 1,
        "client_slug": "test",
        "company_name": "Test Co",
    }
    yield
    app.dependency_overrides.clear()


@pytest.mark.parametrize("method,path,body", OWNERSHIP_ENDPOINTS)
def test_ownership_denied_returns_403(fake_user, method, path, body):
    """Foreign session_id must produce a clean 403, not a 500."""
    # check_rate_limit corre antes da verificação de ownership em /chat/* (I.2);
    # neutraliza-o aqui para isolar o teste à lógica de ownership.
    with patch.object(
        main_module.conversation_store, "check_session_owner", return_value=False
    ), patch.object(
        main_module.conversation_store, "ensure_session"
    ), patch.object(
        main_module, "check_rate_limit"
    ):
        if method == "GET":
            response = client.get(path)
        elif method == "DELETE":
            response = client.delete(path)
        elif method == "PATCH":
            response = client.patch(path, json=body or {})
        else:
            response = client.post(path, json=body or {})

    assert response.status_code == 403, (
        f"{method} {path} returned {response.status_code} "
        f"(body: {response.text}) — ownership check should return clean 403"
    )


# ─────────────────────────────────────────────
# Role-based privilege enforcement (require_role)
# ─────────────────────────────────────────────

# Endpoint dummy registado APENAS no contexto de teste, protegido por
# require_role('admin'). Não toca na app real — serve só para exercitar a
# dependency factory. Fica pronta para o admin portal (Épico L).
@app.get("/_test_admin_only", dependencies=[main_module.Depends(main_module.require_role("admin"))])
def _test_admin_only():
    return {"ok": True}


def _override_user_with_role(role: str):
    app.dependency_overrides[main_module.get_current_user] = lambda: {
        "user_id": 42,
        "email": "a@b.c",
        "full_name": "Test",
        "role": role,
        "client_id": 1,
        "client_slug": "test",
        "company_name": "Test Co",
    }


def test_require_role_member_denied():
    """Um member não tem privilégio para um endpoint require_role('admin') → 403."""
    _override_user_with_role("member")
    try:
        response = client.get("/_test_admin_only")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403


def test_require_role_admin_allowed():
    """Um admin tem privilégio → 200."""
    _override_user_with_role("admin")
    try:
        response = client.get("/_test_admin_only")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == {"ok": True}


# ─────────────────────────────────────────────
# get_current_user: validação de sessão (cutover M.5 — sem must_change_password)
# O gate password_change_required foi removido; o SELECT já não lê a coluna.
# ─────────────────────────────────────────────

from fastapi.security import HTTPAuthorizationCredentials  # noqa: E402


class _AuthCursor:
    """Cursor falso: responde à query de validação de sessão do get_current_user."""

    def __init__(self):
        self._last = ""

    def execute(self, sql, params=None):
        self._last = " ".join(sql.split())

    def fetchone(self):
        if "FROM auth.sessions" in self._last:
            # Ordem do SELECT em main.get_current_user (9 colunas, sem a flag):
            # s.user_id, u.email, u.full_name, u.status, u.role,
            # c.id, c.slug, c.name, c.status
            return (42, "a@b.c", "Test", "active", "member",
                    1, "test", "Test Co", "active")
        return None

    def close(self):
        pass


class _AuthConn:
    def cursor(self):
        return _AuthCursor()

    def commit(self):
        pass

    def close(self):
        pass


def test_get_current_user_returns_user_for_valid_session():
    """Sessão válida → get_current_user devolve o user (sem gate de password)."""
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok")
    with patch.object(main_module, "get_connection", lambda: _AuthConn()), \
            patch.object(main_module, "release_connection", lambda c: None):
        user = main_module.get_current_user(credentials=creds)
    assert user["user_id"] == 42
    assert user["role"] == "member"
    assert "must_change_password" not in user


def test_valid_session_allows_data_endpoint():
    """Endpoint protegido aceita (200) com uma sessão válida."""
    with patch.object(main_module, "get_connection", lambda: _AuthConn()), \
            patch.object(main_module, "release_connection", lambda c: None), \
            patch.object(main_module.conversation_store, "list_sessions", return_value=[]):
        response = client.get("/conversations", headers={"Authorization": "Bearer tok"})
    assert response.status_code == 200, response.text
