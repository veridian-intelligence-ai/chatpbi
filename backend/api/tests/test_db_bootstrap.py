"""Testes do bootstrap do schema (db_bootstrap) e do seed do admin inicial.

Sem BD real: a conexão e o cursor são falsos e registam o SQL executado.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

# db_bootstrap e auth_server vivem na raiz do repositório.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _ROOT)

# Env vars necessárias para `auth_server` importar (fail-fast no módulo).
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test/test")

import pytest  # noqa: E402

import auth_server  # noqa: E402
import db_bootstrap  # noqa: E402


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.executed = []
        self._last = ""
        self.rowcount = 0

    def execute(self, sql, params=None):
        self._last = " ".join(sql.split())
        self.executed.append((self._last, params, self.conn.autocommit))
        if self._last.startswith("INSERT INTO auth.users"):
            self.rowcount = 0 if self.conn.user_exists else 1

    def fetchone(self):
        if "to_regclass" in self._last:
            answer = self.conn.exists_answers.pop(0) if self.conn.exists_answers else True
            return (answer,)
        if "SELECT id FROM auth.clients" in self._last:
            return (7,)
        return None


class _Conn:
    def __init__(self, exists_answers=(), user_exists=False):
        self.autocommit = False
        self.exists_answers = list(exists_answers)
        self.user_exists = user_exists
        self.rollbacks = 0
        self.commits = 0
        self._cursor = _Cursor(self)

    def cursor(self):
        return self._cursor

    def rollback(self):
        self.rollbacks += 1

    def commit(self):
        self.commits += 1


def _sql(conn):
    return [sql for sql, _, _ in conn._cursor.executed]


# ─────────────────────────────────────────────
# ensure_baseline_schema
# ─────────────────────────────────────────────

def test_baseline_skipped_when_schema_exists():
    conn = _Conn(exists_answers=[True])
    assert db_bootstrap.ensure_baseline_schema(conn) is False
    assert not any("pg_advisory_lock" in s for s in _sql(conn))
    assert conn.autocommit is False


def test_baseline_runs_scripts_under_lock_in_autocommit(tmp_path: Path):
    for name in db_bootstrap.BASELINE_FILES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"-- script {name}\nSELECT 1;", encoding="utf-8")

    conn = _Conn(exists_answers=[False, False])
    assert db_bootstrap.ensure_baseline_schema(conn, migrations_dir=tmp_path) is True

    executed = conn._cursor.executed
    sqls = [sql for sql, _, _ in executed]
    lock = next(i for i, s in enumerate(sqls) if "pg_advisory_lock" in s)
    unlock = next(i for i, s in enumerate(sqls) if "pg_advisory_unlock" in s)
    scripts = [i for i, s in enumerate(sqls) if s.startswith("-- script")]
    assert len(scripts) == len(db_bootstrap.BASELINE_FILES)
    assert lock < min(scripts) and max(scripts) < unlock
    # os scripts correm em autocommit (trazem os seus BEGIN/COMMIT)
    assert all(autocommit for sql, _, autocommit in executed if sql.startswith("-- script"))
    # e a conexão volta ao modo em que chegou
    assert conn.autocommit is False


def test_baseline_rechecks_after_waiting_for_the_lock(tmp_path: Path):
    # Outro processo criou o schema enquanto este esperava pelo lock.
    conn = _Conn(exists_answers=[False, True])
    assert db_bootstrap.ensure_baseline_schema(conn, migrations_dir=tmp_path) is False
    sqls = _sql(conn)
    assert any("pg_advisory_unlock" in s for s in sqls)
    assert not any(s.startswith("-- script") for s in sqls)


def test_baseline_files_exist_in_repo():
    for name in db_bootstrap.BASELINE_FILES:
        path = Path(_ROOT) / "scripts" / "migrations" / name
        assert path.exists(), name
        text = path.read_text(encoding="utf-8")
        assert "IF NOT EXISTS" in text


# ─────────────────────────────────────────────
# seed_initial_admin
# ─────────────────────────────────────────────

def _seed(conn, **env):
    values = {
        "SEED_CLIENT_SLUG": "demo",
        "SEED_CLIENT_NAME": "Empresa Demo",
        "SEED_ADMIN_EMAIL": "admin@example.com",
        "SEED_ADMIN_NAME": "Admin Demo",
        "SEED_MEMBER_EMAILS": [],
    }
    values.update(env)
    with patch.multiple(auth_server, **values), \
            patch.object(auth_server, "get_conn", lambda: conn), \
            patch.object(auth_server, "release_conn", lambda c: None):
        return auth_server.seed_initial_admin()


def test_seed_does_nothing_without_admin_email():
    conn = _Conn()
    assert _seed(conn, SEED_ADMIN_EMAIL="") is False
    assert _sql(conn) == []


def test_seed_requires_client_slug():
    with pytest.raises(RuntimeError):
        _seed(_Conn(), SEED_CLIENT_SLUG="")


def test_seed_creates_client_and_active_admin():
    conn = _Conn()
    assert _seed(conn) is True
    executed = conn._cursor.executed
    client_insert = next(e for e in executed if e[0].startswith("INSERT INTO auth.clients"))
    assert "ON CONFLICT (slug) DO NOTHING" in client_insert[0]
    assert client_insert[1] == ("demo", "Empresa Demo")
    user_insert = next(e for e in executed if e[0].startswith("INSERT INTO auth.users"))
    assert "'admin', 'active'" in user_insert[0]
    assert "WHERE NOT EXISTS" in user_insert[0]
    assert user_insert[1] == (7, "admin@example.com", "Admin Demo", "admin@example.com")
    assert conn.commits == 1


def test_seed_is_idempotent_when_user_exists():
    conn = _Conn(user_exists=True)
    assert _seed(conn) is False
    assert conn.commits == 1


def test_seed_creates_member_emails_as_active_members():
    conn = _Conn()
    _seed(conn, SEED_MEMBER_EMAILS=["ana@example.com", "ADMIN@example.com", "rui@example.com"])
    inserts = [e for e in conn._cursor.executed if e[0].startswith("INSERT INTO auth.users")]
    # o admin e os dois membros; o e-mail do admin na lista não entra de novo
    assert len(inserts) == 3
    members = [e for e in inserts if "'member', 'active'" in e[0]]
    assert [m[1] for m in members] == [
        (7, "ana@example.com", "ana@example.com"),
        (7, "rui@example.com", "rui@example.com"),
    ]
    assert all("WHERE NOT EXISTS" in m[0] for m in members)
    assert conn.commits == 1
