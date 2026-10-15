import atexit
import json
import os
import threading
import time
from copy import deepcopy
from typing import Any

import psycopg2
import psycopg2.extensions
import psycopg2.extras
from psycopg2 import pool as psycopg2_pool

from db_bootstrap import ensure_baseline_schema

DEFAULT_CHAT_STATE = {
    "active_domain": None,
    "active_metric_id": None,
    "active_analysis_type": None,
    "active_filters": {},
    "active_date_range": None,
    "active_baseline_date_range": None,
    "active_comparison_mode": None,
    "active_dimension": None,
    "last_grouping_dimension": None,
    "last_time_grain": None,
    "last_top_entity": None,
    "last_analysis_goal": None,
    "last_user_intent": None,
    "last_result_summary": None,
    "pending_clarification": None,
}


# Registar conversão automática JSONB <-> dict Python
# Aplica-se globalmente a todas as conexões deste processo.
psycopg2.extras.register_default_jsonb(loads=json.loads, globally=True)


# ──────────────────────────────────────────────────────────────────────
# Connection pool (F.9)
# ──────────────────────────────────────────────────────────────────────
# Um pool partilhado por processo (singleton). Cada operação pede uma
# conexão com get_connection() e devolve-a com release_connection() no
# finally — em vez de connect()/close() por método. Sob carga concorrente
# o padrão antigo esgotava as conexões do Postgres managed do Railway
# (append_message abria 3 por mensagem).
#
# Dimensionamento: minconn/maxconn por env var. Default maxconn=10 para
# reduzir latência de espera sob carga, mantendo folga face ao limite do
# plano — api e auth são processos separados, cada um com o seu pool, e a
# soma (~20 max) tem de caber no limite do Railway.
#
# Espera (correção F.9): o ThreadedConnectionPool do psycopg2 rejeita de
# imediato com PoolError quando os maxconn estão todos em uso. Sob carga
# concorrente isso traduzia-se em 500s. Em vez de rejeitar, get_connection()
# ESPERA por uma conexão livre (backoff curto) até DB_POOL_TIMEOUT; só então
# desiste com PoolTimeout (→ 503 nos endpoints).

_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))
_POOL_TIMEOUT = float(os.getenv("DB_POOL_TIMEOUT", "10"))
_POOL_RETRY_INTERVAL = 0.05  # 50ms entre tentativas — evita busy-loop apertado

_pool: psycopg2_pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


class PoolTimeout(Exception):
    """Pool saturado para além de DB_POOL_TIMEOUT — sem conexão livre a tempo."""


def _get_pool() -> psycopg2_pool.ThreadedConnectionPool:
    """Devolve o pool, criando-o à primeira utilização (thread-safe)."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                dsn = os.getenv("DATABASE_URL")
                if not dsn:
                    raise RuntimeError("DATABASE_URL não configurada")
                _pool = psycopg2_pool.ThreadedConnectionPool(
                    _POOL_MIN, _POOL_MAX, dsn
                )
    return _pool


def get_connection():
    """Obtém uma conexão do pool, ESPERANDO por uma livre se necessário.

    O ThreadedConnectionPool levanta PoolError quando esgota; em vez de
    propagar o erro, fazemos retry com backoff curto até DB_POOL_TIMEOUT.
    Se mesmo assim não houver conexão, levantamos PoolTimeout (→ 503).
    TEM de ser devolvida com release_connection().
    """
    pool = _get_pool()
    deadline = time.monotonic() + _POOL_TIMEOUT
    while True:
        try:
            return pool.getconn()
        except psycopg2_pool.PoolError:
            if time.monotonic() >= deadline:
                raise PoolTimeout(
                    "Pool de conexões esgotado: nenhuma conexão livre "
                    f"em {_POOL_TIMEOUT}s."
                )
            time.sleep(_POOL_RETRY_INTERVAL)


def release_connection(conn) -> None:
    """Devolve a conexão ao pool.

    Faz rollback defensivo se a conexão ficou numa transação aberta (ex.:
    exceção a meio de uma query, sem commit) — nunca devolve uma conexão
    suja ao pool. NUNCA fecha a conexão de vez (isso esvaziaria o pool com
    o tempo); usa sempre putconn.
    """
    if conn is None:
        return
    try:
        if conn.closed == 0 and (
            conn.info.transaction_status
            != psycopg2.extensions.TRANSACTION_STATUS_IDLE
        ):
            conn.rollback()
    except Exception:
        # Se o rollback falhar a conexão está partida; putconn descarta-a.
        pass
    _get_pool().putconn(conn)


def close_pool() -> None:
    """Fecha todas as conexões do pool (shutdown). Idempotente."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


# Rede de segurança: fecha o pool ao terminar o processo, caso o lifespan
# da app não corra (ex.: arranque via script).
atexit.register(close_pool)


def run_migrations() -> None:
    """Run idempotent schema migrations on startup."""
    conn = None
    try:
        conn = get_connection()
        # BD vazia (instalação nova): cria primeiro o baseline dos schemas
        # auth e ai, sobre o qual as migrações abaixo acrescentam colunas.
        ensure_baseline_schema(conn)
        cursor = conn.cursor()
        cursor.execute(
            "ALTER TABLE ai.chat_sessions ADD COLUMN IF NOT EXISTS title TEXT;"
        )
        cursor.execute(
            """
            ALTER TABLE ai.chat_sessions
            ADD COLUMN IF NOT EXISTS user_id INTEGER;
            """
        )
        # Rate limiting por utilizador (I.2): regista cada chamada paga
        # (/chat/v2, /chat/voice). Estado em Postgres para sobreviver a
        # reinícios e funcionar com múltiplas instâncias.
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ai.api_usage_events (
                id          BIGSERIAL PRIMARY KEY,
                user_id     BIGINT NOT NULL,
                endpoint    TEXT NOT NULL,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_api_usage_events_user_time
            ON ai.api_usage_events (user_id, created_at);
            """
        )
        # Instrumentação de consumo (O.1): um evento por chamada paga, com
        # UNIDADES FÍSICAS apenas (tokens Claude, chars/bytes ElevenLabs).
        # Pricing e cálculo de custo ficam para O.2 — esta tabela não guarda €.
        # Tabela NOVA e separada de api_usage_events (hot-path do rate limiter,
        # que não tocamos). Índices alinhados às queries do admin portal
        # (consumo por cliente / por utilizador ao longo do tempo).
        # FOLLOW-UP: sem particionamento por agora (volume baixo); rever quando
        # crescer (ex.: particionar por mês sobre created_at).
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ai.usage_events (
                id                  BIGSERIAL PRIMARY KEY,
                created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                client_id           BIGINT NOT NULL,
                user_id             BIGINT NOT NULL,
                session_id          VARCHAR(100),
                endpoint            TEXT NOT NULL,
                provider            TEXT NOT NULL,
                model               TEXT NOT NULL,
                input_tokens        BIGINT,
                output_tokens       BIGINT,
                cache_read_tokens   BIGINT,
                cache_write_tokens  BIGINT,
                char_count          BIGINT,
                audio_bytes         BIGINT,
                latency_ms          INTEGER,
                iteration_count     INTEGER,
                status              TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_usage_events_client_time
            ON ai.usage_events (client_id, created_at);
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_usage_events_user_time
            ON ai.usage_events (user_id, created_at);
            """
        )
        conn.commit()
    finally:
        release_connection(conn)


def emit_usage_event(
    *,
    client_id: int,
    user_id: int,
    endpoint: str,
    provider: str,
    model: str,
    session_id: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_read_tokens: int | None = None,
    cache_write_tokens: int | None = None,
    char_count: int | None = None,
    audio_bytes: int | None = None,
    latency_ms: int | None = None,
    iteration_count: int | None = None,
    status: str = "success",
) -> None:
    """Regista um evento de consumo em ai.usage_events (ponto único — O.1).

    Best-effort: NUNCA levanta. Um pedido pago que já teve sucesso não pode
    falhar por causa do logging de consumo — em caso de erro só imprime
    "[usage] emit FAILED: ..." para dar visibilidade nos logs do Railway.
    Garantia forte (outbox/retry) fica para quando a cobrança for real (O.2+).
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ai.usage_events (
                client_id, user_id, session_id, endpoint, provider, model,
                input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                char_count, audio_bytes, latency_ms, iteration_count, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                client_id, user_id, session_id, endpoint, provider, model,
                input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                char_count, audio_bytes, latency_ms, iteration_count, status,
            ),
        )
        conn.commit()
    except Exception as exc:
        print(f"[usage] emit FAILED: {exc}")
    finally:
        release_connection(conn)


class ConversationStore:
    def __init__(self, history_limit: int = 12):
        self.history_limit = history_limit

    def ensure_session(self, session_id: str, module: str = "finance",
                       user_id: int = None) -> None:
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT 1
                FROM ai.chat_sessions
                WHERE session_id = %s AND module = %s
                """,
                (session_id, module),
            )
            session_exists = cursor.fetchone() is not None

            if not session_exists:
                # client_id is derived from user_id to enforce tenant isolation.
                # The sub-query SELECT will return NULL if user_id is None or invalid,
                # causing the INSERT to fail with NOT NULL constraint — which is the
                # desired behaviour (sessions must always belong to a tenant).
                cursor.execute(
                    """
                    INSERT INTO ai.chat_sessions (
                        session_id,
                        module,
                        is_active,
                        user_id,
                        client_id,
                        created_at,
                        updated_at,
                        last_user_message_at,
                        last_assistant_message_at
                    )
                    VALUES (
                        %s, %s, TRUE, %s,
                        (SELECT client_id FROM auth.users WHERE id = %s),
                        NOW(), NOW(), NULL, NULL
                    )
                    """,
                    (session_id, module, user_id, user_id),
                )

            cursor.execute(
                """
                SELECT 1
                FROM ai.chat_state
                WHERE session_id = %s AND module = %s
                """,
                (session_id, module),
            )
            state_exists = cursor.fetchone() is not None

            if not state_exists:
                cursor.execute(
                    """
                    INSERT INTO ai.chat_state (
                        session_id,
                        module,
                        state_json,
                        updated_at
                    )
                    VALUES (%s, %s, %s, NOW())
                    """,
                    (session_id, module, psycopg2.extras.Json(DEFAULT_CHAT_STATE)),
                )

            conn.commit()
        finally:
            release_connection(conn)

    def get_history(self, session_id: str, module: str = "finance", limit: int | None = None) -> list[dict[str, str]]:
        history_limit = limit or self.history_limit

        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT role, content
                FROM (
                    SELECT role, content, message_order
                    FROM ai.chat_messages
                    WHERE session_id = %s AND module = %s
                    ORDER BY message_order DESC
                    LIMIT %s
                ) AS recent_messages
                ORDER BY message_order ASC
                """,
                (session_id, module, history_limit),
            )

            rows = cursor.fetchall()
            return [{"role": row[0], "content": row[1]} for row in rows]
        finally:
            release_connection(conn)

    def _get_next_message_order(self, session_id: str, module: str = "finance") -> int:
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT COALESCE(MAX(message_order), 0) + 1
                FROM ai.chat_messages
                WHERE session_id = %s AND module = %s
                """,
                (session_id, module),
            )

            row = cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else 1
        finally:
            release_connection(conn)

    def _normalize_content_for_storage(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)

    def append_message(self, session_id: str, role: str, content: Any, module: str = "finance") -> None:
        if role not in {"user", "assistant"}:
            raise ValueError(f"Role inválido: {role}")

        self.ensure_session(session_id, module=module)
        next_order = self._get_next_message_order(session_id, module=module)
        normalized_content = self._normalize_content_for_storage(content)

        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO ai.chat_messages (
                    session_id,
                    module,
                    role,
                    content,
                    message_order,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, NOW())
                """,
                (session_id, module, role, normalized_content, next_order),
            )

            if role == "user":
                cursor.execute(
                    """
                    UPDATE ai.chat_sessions
                    SET
                        updated_at = NOW(),
                        last_user_message_at = NOW(),
                        is_active = TRUE
                    WHERE session_id = %s AND module = %s
                    """,
                    (session_id, module),
                )
            else:
                cursor.execute(
                    """
                    UPDATE ai.chat_sessions
                    SET
                        updated_at = NOW(),
                        last_assistant_message_at = NOW(),
                        is_active = TRUE
                    WHERE session_id = %s AND module = %s
                    """,
                    (session_id, module),
                )

            conn.commit()
        finally:
            release_connection(conn)

    def append_user_message(self, session_id: str, content: str, module: str = "finance") -> None:
        self.append_message(session_id=session_id, role="user", content=content, module=module)

    def append_assistant_message(self, session_id: str, content: Any, module: str = "finance") -> None:
        self.append_message(session_id=session_id, role="assistant", content=content, module=module)

    def get_state(self, session_id: str, module: str = "finance") -> dict[str, Any]:
        self.ensure_session(session_id, module=module)

        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT state_json
                FROM ai.chat_state
                WHERE session_id = %s AND module = %s
                """,
                (session_id, module),
            )

            row = cursor.fetchone()
            if not row or not row[0]:
                return deepcopy(DEFAULT_CHAT_STATE)

            state = row[0]
            if not isinstance(state, dict):
                return deepcopy(DEFAULT_CHAT_STATE)
            return {**deepcopy(DEFAULT_CHAT_STATE), **state}
        finally:
            release_connection(conn)

    def update_state(self, session_id: str, state: dict, module: str = "finance") -> None:
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE ai.chat_state
                SET state_json = %s, updated_at = NOW()
                WHERE session_id = %s AND module = %s
                """,
                (psycopg2.extras.Json(state), session_id, module),
            )
            conn.commit()
        finally:
            release_connection(conn)

    def list_sessions(self, module: str = "fabric", limit: int = 20,
                      user_id: int = None) -> list[dict]:
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    cs.session_id,
                    cs.updated_at,
                    cs.created_at,
                    COALESCE(
                        NULLIF(cs.title, ''),
                        (
                            SELECT content
                            FROM ai.chat_messages cm
                            WHERE cm.session_id = cs.session_id
                              AND cm.module = cs.module
                              AND cm.role = 'user'
                            ORDER BY cm.message_order ASC
                            LIMIT 1
                        )
                    ) AS first_message
                FROM ai.chat_sessions cs
                WHERE cs.module = %s
                  AND (%s::INTEGER IS NULL OR cs.user_id = %s)
                  AND cs.last_user_message_at IS NOT NULL
                  AND cs.session_id NOT LIKE 'smoke-%%'
                  AND cs.session_id NOT LIKE 'test-%%'
                ORDER BY cs.updated_at DESC
                LIMIT %s
                """,
                (module, user_id, user_id, limit),
            )
            rows = cursor.fetchall()
            return [
                {
                    "session_id": row[0],
                    "updated_at": row[1].isoformat() if row[1] else None,
                    "created_at": row[2].isoformat() if row[2] else None,
                    "title": (row[3][:60] + "...") if row[3] and len(row[3]) > 60 else (row[3] or "Nova conversa"),
                }
                for row in rows
            ]
        finally:
            release_connection(conn)

    def check_session_owner(self, session_id: str, user_id: int,
                            client_id: int, module: str = "fabric") -> bool:
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 1 FROM ai.chat_sessions
                WHERE session_id = %s
                  AND module = %s
                  AND user_id = %s
                  AND client_id = %s
                """,
                (session_id, module, user_id, client_id),
            )
            return cursor.fetchone() is not None
        finally:
            release_connection(conn)

    def get_session_messages(self, session_id: str, module: str = "fabric") -> list[dict]:
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT role, content, created_at, message_order
                FROM ai.chat_messages
                WHERE session_id = %s AND module = %s
                ORDER BY message_order ASC
                """,
                (session_id, module),
            )
            rows = cursor.fetchall()
            return [
                {
                    "role": row[0],
                    "content": row[1],
                    "created_at": row[2].isoformat() if row[2] else None,
                    "message_order": row[3],
                }
                for row in rows
            ]
        finally:
            release_connection(conn)

    def rename_session(self, session_id: str, title: str, module: str = "fabric") -> None:
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE ai.chat_sessions
                SET title = %s, updated_at = NOW()
                WHERE session_id = %s AND module = %s
                """,
                (title, session_id, module),
            )
            conn.commit()
        finally:
            release_connection(conn)

    def clear(self, session_id: str, module: str = "finance") -> None:
        self.ensure_session(session_id, module=module)

        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                DELETE FROM ai.chat_messages
                WHERE session_id = %s AND module = %s
                """,
                (session_id, module),
            )

            cursor.execute(
                """
                UPDATE ai.chat_state
                SET
                    state_json = %s,
                    updated_at = NOW()
                WHERE session_id = %s AND module = %s
                """,
                (psycopg2.extras.Json(DEFAULT_CHAT_STATE), session_id, module),
            )

            cursor.execute(
                """
                UPDATE ai.chat_sessions
                SET
                    updated_at = NOW(),
                    last_user_message_at = NULL,
                    last_assistant_message_at = NULL,
                    is_active = TRUE
                WHERE session_id = %s AND module = %s
                """,
                (session_id, module),
            )

            conn.commit()
        finally:
            release_connection(conn)
