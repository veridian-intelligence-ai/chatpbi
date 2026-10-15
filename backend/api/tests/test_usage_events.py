"""Testes da instrumentação de consumo ai.usage_events (Tarefa O.1).

(i)  Integração contra Postgres real: emit_usage_event grava uma linha com os
     campos certos. Skip automático quando não há DATABASE_URL real acessível
     (ex.: CI sem Postgres, ou DSN de teste) — padrão I.25.
(ii) Robustez best-effort: uma falha de BD no emit NÃO propaga nem altera a
     resposta do endpoint; apenas regista "[usage] emit FAILED" nos logs.
"""
import os
import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Env vars necessárias para `main` / `conversation_store` importarem
# (CORS + Fabric fazem fail-fast no import).
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("FABRIC_DEFAULT_DATASET_ID", "test-dataset")
os.environ.setdefault("FABRIC_TENANT_ID", "test-tenant")
os.environ.setdefault("FABRIC_CLIENT_ID", "test-client")
os.environ.setdefault("FABRIC_CLIENT_SECRET", "test-secret")
os.environ.setdefault("FABRIC_WORKSPACE_ID", "test-workspace")

import conversation_store as cs  # noqa: E402

# `main` chama run_migrations() no import, que tocaria no Postgres.
with patch("conversation_store.run_migrations"):
    import main as main_module  # noqa: E402

from api.orchestrator import IterationLog, OrchestratorResult  # noqa: E402

# ──────────────────────────────────────────────────────────────────────
# (i) Integração contra Postgres real (padrão I.25)
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def real_db_conn():
    """Liga ao Postgres real e garante a tabela (via run_migrations real).

    Skip quando não há DATABASE_URL real: sem variável, com o DSN-placeholder
    dos testes (postgresql://test/...), ou se o Postgres estiver inacessível.
    Mantém o CI (sem Postgres) verde.
    """
    dsn = os.getenv("DATABASE_URL")
    if not dsn or dsn.startswith("postgresql://test/"):
        pytest.skip("DATABASE_URL real não configurada — integração ignorada")

    import psycopg2

    try:
        conn = psycopg2.connect(dsn)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Postgres inacessível: {exc}")

    # Garante schema/tabela pelo caminho real de migração (idempotente).
    try:
        cs.run_migrations()
    except Exception as exc:  # noqa: BLE001
        conn.close()
        pytest.skip(f"run_migrations falhou (BD não provisionada?): {exc}")

    try:
        yield conn
    finally:
        conn.close()


def test_emit_usage_event_persists_row(real_db_conn):
    """(i) emit grava uma linha em ai.usage_events com os campos certos."""
    sentinel = f"o1-itest-{uuid.uuid4()}"
    cs.emit_usage_event(
        client_id=987654321,
        user_id=123456789,
        session_id=sentinel,
        endpoint="/chat/v2",
        provider="anthropic",
        model="claude-sonnet-4-5",
        input_tokens=450,
        output_tokens=180,
        cache_read_tokens=34500,
        cache_write_tokens=0,
        latency_ms=59242,
        iteration_count=2,
        status="success",
    )

    cur = real_db_conn.cursor()
    cur.execute(
        """
        SELECT client_id, user_id, session_id, endpoint, provider, model,
               input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
               char_count, audio_bytes, latency_ms, iteration_count, status
        FROM ai.usage_events
        WHERE session_id = %s
        """,
        (sentinel,),
    )
    row = cur.fetchone()
    # Limpa antes de assertar — não deixa lixo mesmo que a asserção falhe.
    cur.execute("DELETE FROM ai.usage_events WHERE session_id = %s", (sentinel,))
    real_db_conn.commit()

    assert row is not None, "emit não gravou a linha"
    assert row == (
        987654321, 123456789, sentinel, "/chat/v2", "anthropic", "claude-sonnet-4-5",
        450, 180, 34500, 0,
        None, None, 59242, 2, "success",
    )


# ──────────────────────────────────────────────────────────────────────
# (ii) Best-effort: falha de BD não propaga nem altera a resposta
# ──────────────────────────────────────────────────────────────────────

def test_emit_usage_event_never_raises_on_db_failure(capsys, monkeypatch):
    """Falha ao obter conexão → emit não levanta e regista [usage] emit FAILED."""
    def _boom():
        raise RuntimeError("db indisponível (simulado)")

    monkeypatch.setattr(cs, "get_connection", _boom)

    # Não deve levantar, mesmo com a BD em baixo.
    cs.emit_usage_event(
        client_id=1,
        user_id=1,
        endpoint="/tts",
        provider="elevenlabs",
        model="eleven_multilingual_v2",
        char_count=123,
        status="success",
    )

    assert "[usage] emit FAILED" in capsys.readouterr().out


def test_chat_v2_response_unaffected_by_emit_failure(capsys, monkeypatch):
    """Ao nível do endpoint: uma falha de BD no emit não altera a resposta."""
    result = OrchestratorResult(
        answer="resposta ok",
        total_latency_ms=1000,
        total_input_tokens=450,
        total_output_tokens=180,
        total_cache_read_tokens=34500,
        iterations=[
            IterationLog(
                iteration=1, latency_ms=1000, stop_reason="end_turn",
                input_tokens=450, output_tokens=180,
                cache_write_tokens=0, cache_read_tokens=34500,
            )
        ],
    )
    orchestrator_mock = MagicMock()
    orchestrator_mock.run.return_value = result

    # emit usa conversation_store.get_connection — força falha de BD aí.
    def _boom():
        raise RuntimeError("db indisponível (simulado)")

    monkeypatch.setattr(cs, "get_connection", _boom)

    request = main_module.ChatRequest(session_id="s1", message="Quanto foi gasto?")
    current_user = {"user_id": 1, "client_id": 1}

    store = main_module.conversation_store
    with patch.object(main_module, "check_rate_limit"), \
            patch.object(main_module, "_build_orchestrator", return_value=orchestrator_mock), \
            patch.object(store, "ensure_session"), \
            patch.object(store, "check_session_owner", return_value=True), \
            patch.object(store, "get_history", return_value=[]), \
            patch.object(store, "append_user_message"), \
            patch.object(store, "append_assistant_message"):
        payload = main_module.chat_v2(request, current_user=current_user)

    # Resposta intacta apesar da falha de emit.
    assert payload["status"] == "success"
    assert payload["answer"] == "resposta ok"
    assert "[usage] emit FAILED" in capsys.readouterr().out
