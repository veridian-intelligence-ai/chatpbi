"""
Bootstrap do schema Postgres numa BD vazia.

Os serviços api (api/main.py) e auth (auth_server.py) assumem que os schemas
`auth` e `ai` já existem: as migrações de arranque (`run_migrations()` e
`run_auth_migrations()`) só acrescentam colunas e tabelas a esse baseline.
Numa instalação nova, `ensure_baseline_schema()` corre antes delas os scripts
de baseline de scripts/migrations (000_auth_baseline e 001_ai_baseline), que
são idempotentes.

Os dois serviços arrancam ao mesmo tempo, por isso o baseline corre sob um
advisory lock do Postgres: o segundo processo espera pelo primeiro e depois
vê o schema já criado.

Partilhado pelos dois serviços (como o cors_config.py): fica na raiz e o
Dockerfile copia-o explicitamente.
"""
from __future__ import annotations

from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "scripts" / "migrations"

BASELINE_FILES = (
    "000_auth_baseline/01_auth_schema.sql",
    "001_ai_baseline/01_ai_schema.sql",
)

# Chave arbitrária e fixa do advisory lock do bootstrap.
_LOCK_KEY = 726_354_001


def _baseline_exists(cursor) -> bool:
    cursor.execute(
        "SELECT to_regclass('auth.users') IS NOT NULL "
        "AND to_regclass('ai.chat_messages') IS NOT NULL"
    )
    return bool(cursor.fetchone()[0])


def ensure_baseline_schema(conn, migrations_dir: Path = _MIGRATIONS_DIR) -> bool:
    """Cria os schemas `auth` e `ai` se ainda não existirem.

    Devolve True se correu os scripts de baseline, False se o schema já existia.
    A conexão é devolvida no mesmo modo de autocommit em que chegou.
    """
    cursor = conn.cursor()
    if _baseline_exists(cursor):
        conn.rollback()
        return False

    previous_autocommit = conn.autocommit
    if not previous_autocommit:
        conn.rollback()
    # Os scripts trazem os seus próprios BEGIN/COMMIT.
    conn.autocommit = True
    try:
        cursor.execute("SELECT pg_advisory_lock(%s)", (_LOCK_KEY,))
        try:
            # Outro processo pode ter criado o schema enquanto esperávamos.
            if _baseline_exists(cursor):
                return False
            for name in BASELINE_FILES:
                cursor.execute((migrations_dir / name).read_text(encoding="utf-8"))
            print("[db] baseline dos schemas auth e ai criado")
            return True
        finally:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_KEY,))
    finally:
        conn.autocommit = previous_autocommit
