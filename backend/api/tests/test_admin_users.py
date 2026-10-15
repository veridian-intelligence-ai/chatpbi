"""Testes do POST /admin/users (auth_server) — fix do role / check constraint.

O default da coluna auth.users.role é 'user', proibido pelo check constraint
users_role_check (só 'admin'/'member'). O endpoint passa a escrever role
explícito (default "member") e a validá-lo no corpo → 400 se inválido, em vez
de deixar o INSERT rebentar com 500 (CheckViolation).

Mockam-se as ligações Postgres (auth_server.get_conn) e a dependency de admin.
"""

import os
import sys
from unittest.mock import patch

# auth_server vive na raiz do repositório.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Env vars necessárias para `auth_server` importar (fail-fast no módulo).
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test/test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import auth_server  # noqa: E402

client = TestClient(auth_server.app, raise_server_exceptions=False)


class _Conn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def close(self):
        pass


class _CreateCursor:
    """Cursor falso: resolve o client por slug e regista os INSERTs."""

    def __init__(self, client_id=1):
        self.client_id = client_id
        self._last = ""
        self.executed = []  # (sql_normalizado, params)

    def execute(self, sql, params=None):
        self._last = " ".join(sql.split())
        self.executed.append((self._last, params))

    def fetchone(self):
        if "SELECT id FROM auth.clients" in self._last:
            return (self.client_id,) if self.client_id is not None else None
        return None

    def close(self):
        pass


def _create_user(body, client_id=1):
    cursor = _CreateCursor(client_id=client_id)
    conn = _Conn(cursor)
    # Fura a verificação de X-Admin-Key (testada noutro lado); isola o role.
    auth_server.app.dependency_overrides[auth_server.require_admin] = lambda: None
    try:
        with patch.object(auth_server, "get_conn", lambda: conn), \
                patch.object(auth_server, "release_conn", lambda c: None):
            resp = client.post("/admin/users", json=body)
    finally:
        auth_server.app.dependency_overrides.clear()
    return resp, cursor


def _base_body(**overrides):
    body = {
        "client_slug": "demo",
        "email": "novo@exemplo.com",
        "password": "temp-pass-123",
        "full_name": "Novo Utilizador",
    }
    body.update(overrides)
    return body


def _inserts(cursor):
    return [(s, p) for s, p in cursor.executed if "INSERT INTO auth.users" in s]


def test_create_user_default_role_is_member():
    """Sem role no corpo → default 'member' escrito explicitamente no INSERT."""
    resp, cursor = _create_user(_base_body())
    assert resp.status_code == 200, resp.text
    inserts = _inserts(cursor)
    assert inserts, "esperava um INSERT em auth.users"
    sql, params = inserts[0]
    # Cutover M.5: role presente; já NÃO se escreve must_change_password.
    assert "role" in sql
    assert "must_change_password" not in sql
    # params: (client_id, email, password_hash, full_name, role)
    assert params[4] == "member"


def test_create_user_explicit_admin_role():
    """role='admin' explícito → escrito no INSERT."""
    resp, cursor = _create_user(_base_body(role="admin"))
    assert resp.status_code == 200, resp.text
    _sql, params = _inserts(cursor)[0]
    assert params[4] == "admin"


@pytest.mark.parametrize("bad_role", ["user", "root", ""])
def test_create_user_invalid_role_returns_400_without_insert(bad_role):
    """role inválido (inclui 'user', o default da coluna que causava o 500) → 400,
    sem chegar ao INSERT."""
    resp, cursor = _create_user(_base_body(role=bad_role))
    assert resp.status_code == 400, resp.text
    assert not _inserts(cursor), "não devia ter havido INSERT com role inválido"
