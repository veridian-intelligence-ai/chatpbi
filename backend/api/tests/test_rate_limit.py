"""Testes do rate limiting por utilizador no chat (Tarefa I.2).

Exercita check_rate_limit directamente, com a ligação Postgres
(main.get_connection) mockada por uma conexão falsa que conta eventos em
memória.
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Env vars necessárias para `main` importar.
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("FABRIC_DEFAULT_DATASET_ID", "test-dataset")
os.environ.setdefault("FABRIC_TENANT_ID", "test-tenant")
os.environ.setdefault("FABRIC_CLIENT_ID", "test-client")
os.environ.setdefault("FABRIC_CLIENT_SECRET", "test-secret")
os.environ.setdefault("FABRIC_WORKSPACE_ID", "test-workspace")

# `main` chama run_migrations() no import, que tocaria no Postgres.
with patch("conversation_store.run_migrations"):
    import main as main_module

from fastapi import HTTPException  # noqa: E402


class _FakeCursor:
    """Conta INSERTs e responde às COUNT de minuto/hora."""

    def __init__(self, store):
        self.store = store
        self._last = ""

    def execute(self, sql, params=None):
        self._last = " ".join(sql.split())
        if self._last.startswith("INSERT INTO ai.api_usage_events"):
            self.store["minute"] += 1
            self.store["hour"] += 1

    def fetchone(self):
        if "COUNT(*)" in self._last:
            if "hours =>" in self._last:
                return (self.store["hour"],)
            return (self.store["minute"],)
        return None

    def close(self):
        pass


class _FakeConn:
    def __init__(self, store):
        self.store = store

    def cursor(self):
        return _FakeCursor(self.store)

    def commit(self):
        pass

    def close(self):
        pass


def test_rate_limit_blocks_21st_request_in_a_minute():
    """Os 20 primeiros pedidos passam; o 21º no minuto → 429."""
    store = {"minute": 0, "hour": 0}
    # Com pool (F.9): a conexão é devolvida com release_connection, não fechada.
    # Mockamos release_connection como no-op porque a _FakeConn não vem do pool.
    with patch.object(main_module, "get_connection", lambda: _FakeConn(store)), \
            patch.object(main_module, "release_connection", lambda conn: None):
        for i in range(main_module.RATE_LIMIT_PER_MIN):
            main_module.check_rate_limit(1, "/chat/v2")  # 20 pedidos OK
        assert store["minute"] == main_module.RATE_LIMIT_PER_MIN

        with pytest.raises(HTTPException) as exc:
            main_module.check_rate_limit(1, "/chat/v2")  # 21º
        assert exc.value.status_code == 429
        assert "Demasiados pedidos" in exc.value.detail


def test_rate_limit_blocks_on_hourly_limit():
    """Abaixo do limite/min mas no limite/hora → 429 (limite horário)."""
    store = {"minute": 0, "hour": main_module.RATE_LIMIT_PER_HOUR}
    with patch.object(main_module, "get_connection", lambda: _FakeConn(store)), \
            patch.object(main_module, "release_connection", lambda conn: None):
        with pytest.raises(HTTPException) as exc:
            main_module.check_rate_limit(1, "/chat/voice")
        assert exc.value.status_code == 429


def test_rate_limit_records_event_when_under_limit():
    """Dentro dos limites, regista o evento e deixa prosseguir."""
    store = {"minute": 0, "hour": 0}
    with patch.object(main_module, "get_connection", lambda: _FakeConn(store)), \
            patch.object(main_module, "release_connection", lambda conn: None):
        main_module.check_rate_limit(7, "/chat/v2")
    assert store["minute"] == 1
    assert store["hour"] == 1
