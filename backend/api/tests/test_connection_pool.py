"""Testes do connection pool do Postgres (Tarefa F.9).

Validam, sem uma BD real, que:
- cada get_connection() tem o seu release_connection() (não há fuga);
- o pool nunca é excedido sob ciclos repetidos de pedir/devolver;
- uma conexão devolvida numa transação aberta sofre rollback antes do
  putconn (não volta suja para o pool);
- release_connection() NUNCA fecha a conexão (usa sempre putconn).
"""

import os
import sys
import threading
import time

import psycopg2.extensions
import pytest
from psycopg2 import pool as psycopg2_pool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import conversation_store as cs  # noqa: E402

IDLE = psycopg2.extensions.TRANSACTION_STATUS_IDLE
IN_TRANS = psycopg2.extensions.TRANSACTION_STATUS_INTRANS


class _FakeInfo:
    def __init__(self, status):
        self.transaction_status = status


class _FakeConn:
    def __init__(self, status=IDLE):
        self.closed = 0
        self.info = _FakeInfo(status)
        self.rolled_back = False
        self.closed_hard = False

    def rollback(self):
        self.rolled_back = True
        self.info.transaction_status = IDLE

    def close(self):
        self.closed_hard = True
        self.closed = 1


class _FakePool:
    """Pool falso que rastreia conexões em uso vs. disponíveis."""

    def __init__(self, minconn, maxconn):
        self.maxconn = maxconn
        self._available = [_FakeConn() for _ in range(minconn)]
        self._in_use = []
        self.peak_in_use = 0
        self.closed_all = False

    def getconn(self):
        if self._available:
            conn = self._available.pop()
        else:
            if len(self._in_use) >= self.maxconn:
                raise RuntimeError("pool esgotado")
            conn = _FakeConn()
        self._in_use.append(conn)
        self.peak_in_use = max(self.peak_in_use, len(self._in_use))
        return conn

    def putconn(self, conn):
        self._in_use.remove(conn)
        self._available.append(conn)

    def closeall(self):
        self.closed_all = True


def _install_fake_pool(monkeypatch, minconn=1, maxconn=3):
    fake = _FakePool(minconn, maxconn)
    monkeypatch.setattr(cs, "_pool", fake)
    return fake


def test_get_release_does_not_leak(monkeypatch):
    """Muitos ciclos pedir/devolver: nenhuma conexão fica presa e o pool
    nunca é excedido."""
    fake = _install_fake_pool(monkeypatch, minconn=1, maxconn=3)
    for _ in range(100):
        conn = cs.get_connection()
        cs.release_connection(conn)
    assert len(fake._in_use) == 0, "conexões não devolvidas → fuga"
    assert fake.peak_in_use <= fake.maxconn


def test_release_none_is_safe(monkeypatch):
    """release_connection(None) é no-op (caminho de erro antes do getconn)."""
    _install_fake_pool(monkeypatch)
    cs.release_connection(None)  # não levanta


def test_dirty_connection_is_rolled_back(monkeypatch):
    """Conexão devolvida numa transação aberta sofre rollback antes do putconn."""
    fake = _install_fake_pool(monkeypatch)
    conn = cs.get_connection()
    conn.info.transaction_status = IN_TRANS
    cs.release_connection(conn)
    assert conn.rolled_back is True
    assert conn in fake._available
    assert conn.closed_hard is False


def test_release_never_closes(monkeypatch):
    """release_connection devolve ao pool — nunca fecha de vez a conexão."""
    fake = _install_fake_pool(monkeypatch)
    conn = cs.get_connection()
    cs.release_connection(conn)
    assert conn.closed_hard is False
    assert conn in fake._available


def test_close_pool_is_idempotent(monkeypatch):
    """close_pool() fecha tudo e pode ser chamado várias vezes."""
    fake = _install_fake_pool(monkeypatch)
    cs.close_pool()
    assert fake.closed_all is True
    cs.close_pool()  # idempotente, não levanta


# ──────────────────────────────────────────────────────────────────────
# Espera + timeout (correção F.9)
# ──────────────────────────────────────────────────────────────────────
# O pool real (ThreadedConnectionPool) levanta psycopg2.pool.PoolError
# quando esgota. get_connection() deve ESPERAR por uma conexão livre em vez
# de propagar o erro, e só ao fim de DB_POOL_TIMEOUT levantar PoolTimeout.


class _ExhaustiblePool:
    """Pool falso que esgota a maxconn e levanta PoolError real, como o
    ThreadedConnectionPool. Devolver com putconn liberta uma conexão."""

    def __init__(self, maxconn):
        self.maxconn = maxconn
        self._in_use = 0

    def getconn(self):
        if self._in_use >= self.maxconn:
            raise psycopg2_pool.PoolError("connection pool exhausted")
        self._in_use += 1
        return _FakeConn()

    def putconn(self, conn):
        self._in_use -= 1


def test_getconn_waits_then_succeeds_when_connection_freed(monkeypatch):
    """Pool esgotado: get_connection espera e obtém a conexão quando outra
    thread a liberta — em vez de falhar de imediato."""
    pool = _ExhaustiblePool(maxconn=1)
    monkeypatch.setattr(cs, "_pool", pool)
    monkeypatch.setattr(cs, "_POOL_TIMEOUT", 2.0)
    monkeypatch.setattr(cs, "_POOL_RETRY_INTERVAL", 0.01)

    held = pool.getconn()  # esgota o pool (1/1 em uso)

    def _release_soon():
        time.sleep(0.1)
        pool.putconn(held)

    threading.Thread(target=_release_soon).start()

    start = time.monotonic()
    conn = cs.get_connection()  # deve esperar ~0.1s, não levantar
    waited = time.monotonic() - start

    assert conn is not None
    assert waited >= 0.05, "deveria ter esperado pela libertação, não obtido logo"
    cs.release_connection(conn)


def test_getconn_raises_pool_timeout_after_deadline(monkeypatch):
    """Pool saturado para além do timeout → PoolTimeout (mapeado a 503)."""
    pool = _ExhaustiblePool(maxconn=1)
    monkeypatch.setattr(cs, "_pool", pool)
    monkeypatch.setattr(cs, "_POOL_TIMEOUT", 0.2)
    monkeypatch.setattr(cs, "_POOL_RETRY_INTERVAL", 0.01)

    pool.getconn()  # esgota e nunca liberta

    start = time.monotonic()
    with pytest.raises(cs.PoolTimeout):
        cs.get_connection()
    waited = time.monotonic() - start

    assert waited >= 0.2, "deveria ter esperado até ao timeout antes de desistir"
