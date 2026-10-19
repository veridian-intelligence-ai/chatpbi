"""
Login do app (WorkOS)
=====================
Servidor central de autenticação.

Stack:
- Postgres (Railway managed)
- bcrypt (password hashing, cost factor 12)
- FastAPI

Configuração (.env / auth.env):
    DATABASE_URL=postgresql://...        (do Railway via Variable Reference)
    AUTH_SECRET_KEY=<chave forte>        (opcional: liga os endpoints /admin/*)
    AUTH_TOKEN_EXPIRE_HOURS=24           (default 24h)
    API_PUBLIC_URL=https://<api>.up.railway.app  (opcional; nome antigo: VERIDIAN_API_URL)

Execução local:
    uvicorn auth_server:app --port 8080 --reload
"""

import atexit
import os
import secrets
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import psycopg2
import psycopg2.extensions
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from psycopg2 import pool as psycopg2_pool
from pydantic import BaseModel, Field

from cors_config import get_allowed_origins
from db_bootstrap import ensure_baseline_schema

# ─────────────────────────────────────────────
# Configuração
# ─────────────────────────────────────────────

load_dotenv("auth.env", override=True)

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("AUTH_SECRET_KEY")
TOKEN_EXPIRE_HOURS = int(os.getenv("AUTH_TOKEN_EXPIRE_HOURS", "24"))
# Endereço público da API, devolvido ao frontend no login. O frontend usa
# primeiro o VITE_API_BASE_URL do build, então este valor é só de reserva.
# VERIDIAN_API_URL é o nome antigo da variável e continua valendo.
API_URL_DEFAULT = (
    os.getenv("API_PUBLIC_URL") or os.getenv("VERIDIAN_API_URL") or "http://localhost:8000"
).strip().rstrip("/")

# ── WorkOS AuthKit (login alternativo — integração em paralelo) ──────────────
# Usadas só pelos endpoints /auth/workos/*. Lidas aqui, mas o cliente é criado
# lazy (em _get_workos_client) para que faltarem estas vars NÃO impeça o arranque
# nem o login por password.
WORKOS_API_KEY = os.getenv("WORKOS_API_KEY")
WORKOS_CLIENT_ID = os.getenv("WORKOS_CLIENT_ID")
WORKOS_REDIRECT_URI = os.getenv("WORKOS_REDIRECT_URI")
# Default: EXIGIR email verificado pelo WorkOS. Relaxar só em staging com
# WORKOS_REQUIRE_VERIFIED_EMAIL=false (demo credentials) — decisão 3.
WORKOS_REQUIRE_VERIFIED_EMAIL = (
    os.getenv("WORKOS_REQUIRE_VERIFIED_EMAIL", "true").strip().lower() != "false"
)

# ── Seed da instalação nova ─────────────────────────────────────────────────
# Numa BD vazia não há clientes nem utilizadores, e o login WorkOS só aceita
# users PRÉ-EXISTENTES em auth.users. Com SEED_ADMIN_EMAIL definido, o arranque
# cria (se ainda não existirem) o cliente SEED_CLIENT_SLUG / SEED_CLIENT_NAME e
# esse utilizador como admin activo, sem password local (a auth é WorkOS).
# Idempotente: correr de novo não altera nada. Os restantes utilizadores entram
# por POST /admin/users.
SEED_CLIENT_SLUG = os.getenv("SEED_CLIENT_SLUG", "").strip()
SEED_CLIENT_NAME = os.getenv("SEED_CLIENT_NAME", "").strip()
SEED_ADMIN_EMAIL = os.getenv("SEED_ADMIN_EMAIL", "").strip()
SEED_ADMIN_NAME = os.getenv("SEED_ADMIN_NAME", "").strip()
# Opcional: e-mails de outras pessoas, separados por vírgula, criados como
# membros ativos do mesmo cliente. No caminho só pelo WhatsApp (sem WorkOS nem
# frontend), é assim que se libera mais gente: o número entra em
# WHATSAPP_ALLOWED_NUMBERS e o e-mail aqui. Idempotente.
SEED_MEMBER_EMAILS = [
    e.strip() for e in os.getenv("SEED_MEMBER_EMAILS", "").split(",") if e.strip()
]

# Sem AUTH_SECRET_KEY, os endpoints /admin/* ficam desligados (403 sempre): o
# admin inicial entra pelas SEED_* e o serviço arranca sem mais um segredo.
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL não configurada")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # DDL idempotente no arranque (run_auth_migrations definido abaixo).
    run_auth_migrations()
    # Cliente e admin iniciais a partir das SEED_* (instalação nova).
    seed_initial_admin()
    yield
    # Fecho limpo do pool de conexões no shutdown (F.9).
    close_pool()


app = FastAPI(title="ChatPBI Login", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────
# Connection pool (F.9)
# ──────────────────────────────────────────────────────────────────────
# Pool próprio deste processo (o auth_server corre separado do api/main.py,
# por isso NÃO partilha pool — cada um tem o seu). Cada operação pede uma
# conexão com get_conn() e devolve-a com release_conn() no finally, em vez
# de connect()/close() por request. Sob carga concorrente o padrão antigo
# esgotava as conexões do Postgres managed do Railway.
#
# Dimensionamento: maxconn por env var (default 10) para reduzir latência
# de espera sob carga, mantendo folga face ao limite do plano, partilhado
# com o pool do serviço backend (~20 max no total).
#
# Espera (correção F.9): o ThreadedConnectionPool rejeita de imediato com
# PoolError quando esgota. Em vez de rejeitar, get_conn() ESPERA por uma
# conexão livre (backoff curto) até DB_POOL_TIMEOUT; só então desiste com
# PoolTimeout (→ 503 nos endpoints).

_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))
_POOL_TIMEOUT = float(os.getenv("DB_POOL_TIMEOUT", "10"))
_POOL_RETRY_INTERVAL = 0.05  # 50ms entre tentativas — evita busy-loop apertado

_pool: Optional[psycopg2_pool.ThreadedConnectionPool] = None
_pool_lock = threading.Lock()


class PoolTimeout(Exception):
    """Pool saturado para além de DB_POOL_TIMEOUT — sem conexão livre a tempo."""


def _get_pool() -> psycopg2_pool.ThreadedConnectionPool:
    """Devolve o pool, criando-o à primeira utilização (thread-safe)."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = psycopg2_pool.ThreadedConnectionPool(
                    _POOL_MIN, _POOL_MAX, DATABASE_URL
                )
    return _pool


def get_conn():
    """Obtém uma conexão do pool, ESPERANDO por uma livre se necessário.

    O ThreadedConnectionPool levanta PoolError quando esgota; em vez de
    propagar o erro, fazemos retry com backoff curto até DB_POOL_TIMEOUT.
    Se mesmo assim não houver conexão, levantamos PoolTimeout (→ 503).
    TEM de ser devolvida com release_conn().
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


def release_conn(conn) -> None:
    """Devolve a conexão ao pool.

    Faz rollback defensivo se a conexão ficou numa transação aberta (ex.:
    exceção a meio de uma query, sem commit) — nunca devolve uma conexão
    suja ao pool. NUNCA fecha a conexão de vez (esvaziaria o pool); usa
    sempre putconn.
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
        # Conexão partida; putconn descarta-a.
        pass
    _get_pool().putconn(conn)


def close_pool() -> None:
    """Fecha todas as conexões do pool (shutdown). Idempotente."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


atexit.register(close_pool)


@app.exception_handler(PoolTimeout)
async def _pool_timeout_handler(_request: Request, _exc: PoolTimeout):
    """Pool saturado para além do timeout → 503 (não 500 genérico).

    A conexão nunca chegou a ser obtida, por isso não há nada para devolver
    ao pool; o processo segue normalmente para os próximos pedidos.
    """
    return JSONResponse(
        status_code=503,
        content={"detail": "Serviço temporariamente ocupado, tente novamente."},
    )


def run_auth_migrations() -> None:
    """DDL idempotente executado no arranque do auth_server.

    Espelha:
      - scripts/migrations/003_login_attempts/01_login_attempts.sql
        (tabela de lockout de login)
      - scripts/migrations/004_must_change_password/01_must_change_password.sql
        (coluna auth.users.must_change_password — troca forçada no 1.º acesso)

    CREATE/ALTER ... IF NOT EXISTS — seguro correr múltiplas vezes / em paralelo.
    """
    conn = None
    try:
        conn = get_conn()
        # BD vazia (instalação nova): cria primeiro o baseline dos schemas
        # auth e ai (db_bootstrap.py), sobre o qual este DDL acrescenta.
        ensure_baseline_schema(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS auth.login_attempts (
                id            BIGSERIAL PRIMARY KEY,
                email         TEXT NOT NULL,
                ip_address    INET,
                success       BOOLEAN NOT NULL DEFAULT FALSE,
                attempted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_login_attempts_lookup
            ON auth.login_attempts (email, ip_address, attempted_at)
            """
        )
        # Força troca de senha no primeiro acesso (004_must_change_password).
        cursor.execute(
            """
            ALTER TABLE auth.users
            ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE
            """
        )
        conn.commit()
    finally:
        release_conn(conn)


def seed_initial_admin() -> bool:
    """Cria o cliente e o admin iniciais a partir das SEED_* (idempotente).

    Também cria como membros ativos os e-mails de SEED_MEMBER_EMAILS que ainda
    não existam. Não faz nada sem SEED_ADMIN_EMAIL. Devolve True se criou o admin.
    """
    if not SEED_ADMIN_EMAIL:
        return False
    if not SEED_CLIENT_SLUG:
        raise RuntimeError("SEED_ADMIN_EMAIL definido sem SEED_CLIENT_SLUG")

    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO auth.clients (slug, name)
            VALUES (%s, %s)
            ON CONFLICT (slug) DO NOTHING
            """,
            (SEED_CLIENT_SLUG, SEED_CLIENT_NAME or SEED_CLIENT_SLUG),
        )
        cursor.execute("SELECT id FROM auth.clients WHERE slug = %s", (SEED_CLIENT_SLUG,))
        client_id = cursor.fetchone()[0]
        cursor.execute(
            """
            INSERT INTO auth.users
                (client_id, email, password_hash, full_name, role, status, activated_at)
            SELECT %s, %s, NULL, %s, 'admin', 'active', NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM auth.users WHERE LOWER(email) = LOWER(%s)
            )
            """,
            (client_id, SEED_ADMIN_EMAIL, SEED_ADMIN_NAME or None, SEED_ADMIN_EMAIL),
        )
        created = cursor.rowcount == 1
        novos = 0
        for email in SEED_MEMBER_EMAILS:
            if email.lower() == SEED_ADMIN_EMAIL.lower():
                continue
            cursor.execute(
                """
                INSERT INTO auth.users
                    (client_id, email, password_hash, full_name, role, status, activated_at)
                SELECT %s, %s, NULL, NULL, 'member', 'active', NOW()
                WHERE NOT EXISTS (
                    SELECT 1 FROM auth.users WHERE LOWER(email) = LOWER(%s)
                )
                """,
                (client_id, email, email),
            )
            novos += cursor.rowcount == 1
        conn.commit()
        if created:
            print(f"[seed] admin inicial criado no cliente {SEED_CLIENT_SLUG}")
        if novos:
            print(f"[seed] {novos} membro(s) criado(s) a partir de SEED_MEMBER_EMAILS")
        return created
    finally:
        release_conn(conn)


# ─────────────────────────────────────────────
# Password hashing (bcrypt)
# ─────────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


# ─────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────

class LoginResponse(BaseModel):
    token: str
    api_url: str
    client_slug: str
    company_name: str
    user_name: str
    expires_at: str


class CreateClientRequest(BaseModel):
    slug: str = Field(..., max_length=100)
    company_name: str = Field(..., max_length=200)
    admin_email: str = Field(..., max_length=255)
    admin_password: str = Field(..., max_length=200)
    admin_name: str = Field(..., max_length=200)


class CreateUserRequest(BaseModel):
    client_slug: str = Field(..., max_length=100)
    email: str = Field(..., max_length=255)
    password: str = Field(..., max_length=200)
    full_name: str = Field(..., max_length=200)
    # Opcional; default "member". Validado no endpoint (admin/member) → 400 se inválido.
    role: str = Field(default="member", max_length=50)


# ─────────────────────────────────────────────
# Auth helper
# ─────────────────────────────────────────────

def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token não fornecido")

    token = authorization.replace("Bearer ", "")

    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.user_id, s.expires_at,
                   u.email, u.full_name, u.status,
                   c.slug, c.name, c.status
            FROM auth.sessions s
            INNER JOIN auth.users u ON u.id = s.user_id
            INNER JOIN auth.clients c ON c.id = u.client_id
            WHERE s.token = %s
              AND s.expires_at > NOW()
              AND s.revoked_at IS NULL
        """, (token,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Token inválido ou expirado")

        user_id, expires_at, email, full_name, user_status, \
            client_slug, company_name, client_status = row

        if user_status != "active":
            raise HTTPException(status_code=403, detail="Utilizador inactivo")
        if client_status != "active":
            raise HTTPException(status_code=403, detail="Cliente inactivo")

        return {
            "user_id": user_id,
            "email": email,
            "full_name": full_name,
            "client_slug": client_slug,
            "company_name": company_name,
            "api_url": API_URL_DEFAULT,
        }
    finally:
        release_conn(conn)


# ─────────────────────────────────────────────
# Endpoints públicos
# ─────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "auth"}


@app.post("/auth/logout")
def logout(user: dict = Depends(get_current_user),
           authorization: Optional[str] = Header(None)):
    token = authorization.replace("Bearer ", "")
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE auth.sessions
            SET revoked_at = NOW()
            WHERE token = %s AND revoked_at IS NULL
        """, (token,))
        conn.commit()
        return {"status": "ok"}
    finally:
        release_conn(conn)


@app.get("/auth/me")
def me(user: dict = Depends(get_current_user)):
    return user


# ─────────────────────────────────────────────
# WorkOS AuthKit — login alternativo (integração em paralelo)
# ─────────────────────────────────────────────
# Caminho de login ADITIVO: o utilizador autentica-se no AuthKit (email+password,
# Google ou Microsoft) e nós, no fim, emitimos a NOSSA sessão opaca em
# auth.sessions — exactamente como o /auth/login. O api/main.py não muda: continua
# a validar o token opaco por DB lookup. Só users PRÉ-EXISTENTES em auth.users
# entram (match por email); criar users novos via WorkOS fica para fase posterior.
#
# Fluxo (Opção A — o redirect_uri aponta ao FRONTEND, não muda):
#   1. Frontend  → GET /auth/workos/login        → 302 para o AuthKit
#   2. AuthKit autentica e redirige para           https://stg…/callback?code=…
#   3. Frontend lê o ?code e faz                   POST /auth/workos/callback {code}
#   4. Aqui trocamos o code, validamos o email e devolvemos LoginResponse
#
# Isolamento: a ausência/erro do SDK ou da config NUNCA quebra o login por
# password — _get_workos_client() responde 503 e o resto do serviço segue.

# Import opcional do SDK: se faltar, o caminho WorkOS desliga-se (503), mas o
# módulo arranca na mesma (login por password intacto).
try:
    from workos import RateLimitExceededError, WorkOSClient, WorkOSError
except ImportError:  # pragma: no cover - SDK ausente
    WorkOSClient = None
    WorkOSError = Exception
    RateLimitExceededError = Exception

_workos_client = None
_workos_lock = threading.Lock()


def _get_workos_client():
    """WorkOSClient como singleton lazy. 503 se o SDK ou a config faltarem.

    Nunca levanta no import — só aqui, no uso — para isolar o caminho WorkOS do
    login por password.
    """
    global _workos_client
    if _workos_client is None:
        if WorkOSClient is None:
            raise HTTPException(status_code=503, detail="workos_not_available")
        if not (WORKOS_API_KEY and WORKOS_CLIENT_ID):
            raise HTTPException(status_code=503, detail="workos_not_configured")
        with _workos_lock:
            if _workos_client is None:
                _workos_client = WorkOSClient(
                    api_key=WORKOS_API_KEY, client_id=WORKOS_CLIENT_ID
                )
    return _workos_client


def _issue_session(cursor, user_id: int) -> tuple[str, datetime]:
    """Emite a NOSSA sessão opaca e persiste em auth.sessions.

    Mesma mecânica do /auth/login: token_urlsafe(48) + INSERT + last_login_at.
    NÃO faz commit nem gere a conexão — o chamador controla a transação.
    """
    token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    cursor.execute(
        "INSERT INTO auth.sessions (user_id, token, expires_at) VALUES (%s, %s, %s)",
        (user_id, token, expires_at),
    )
    cursor.execute(
        "UPDATE auth.users SET last_login_at = NOW() WHERE id = %s", (user_id,)
    )
    return token, expires_at


def _complete_workos_login(workos_user) -> LoginResponse:
    """Dado um user JÁ autenticado no WorkOS (por code OAuth ou por password),
    valida o email, faz match com auth.users e emite a NOSSA sessão opaca.

    Partilhado pelo callback OAuth e pelo password-login headless — mesma política:
    email verificado + só users PRÉ-EXISTENTES (match por email) entram.
    """
    email = (workos_user.email or "").strip()
    if not email:
        raise HTTPException(status_code=401, detail="workos_authentication_failed")

    # Exigir email verificado (relaxável só em staging via WORKOS_REQUIRE_VERIFIED_EMAIL).
    if WORKOS_REQUIRE_VERIFIED_EMAIL and not workos_user.email_verified:
        raise HTTPException(status_code=403, detail="workos_email_not_verified")

    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()

        # Match por email (case-insensitive) com auth.users + clients. Sem password.
        cursor.execute(
            """
            SELECT u.id, u.full_name, u.status,
                   c.slug, c.name, c.status
            FROM auth.users u
            INNER JOIN auth.clients c ON c.id = u.client_id
            WHERE LOWER(u.email) = LOWER(%s)
            """,
            (email,),
        )
        row = cursor.fetchone()

        # User WorkOS sem correspondência em auth.users → 403 (sem auto-criação).
        if not row:
            raise HTTPException(status_code=403, detail="workos_user_not_provisioned")

        user_id, full_name, user_status, \
            client_slug, company_name, client_status = row

        if user_status != "active":
            raise HTTPException(status_code=403, detail="Utilizador inactivo")
        if client_status != "active":
            raise HTTPException(status_code=403, detail="Cliente inactivo")

        token, expires_at = _issue_session(cursor, user_id)
        conn.commit()

        return LoginResponse(
            token=token,
            api_url=API_URL_DEFAULT,
            client_slug=client_slug,
            company_name=company_name,
            user_name=full_name or email,
            expires_at=expires_at.isoformat(),
        )
    finally:
        release_conn(conn)


class WorkOSCallbackRequest(BaseModel):
    # code do AuthKit (válido ~10 min). state é opcional (CSRF gerido no frontend).
    code: str = Field(..., max_length=2000)
    state: Optional[str] = Field(default=None, max_length=2000)


@app.get("/auth/workos/login")
def workos_login(state: Optional[str] = None):
    """Inicia o login WorkOS: gera a authorization URL do AuthKit e redirige (302).

    redirect_uri vem de WORKOS_REDIRECT_URI e aponta ao frontend (Opção A); tem de
    coincidir com o redirect URI configurado no dashboard WorkOS.
    """
    if not WORKOS_REDIRECT_URI:
        raise HTTPException(status_code=503, detail="workos_not_configured")
    client = _get_workos_client()
    authorization_url = client.user_management.get_authorization_url(
        provider="authkit",
        redirect_uri=WORKOS_REDIRECT_URI,
        state=state,
    )
    return RedirectResponse(url=authorization_url, status_code=302)


@app.post("/auth/workos/callback", response_model=LoginResponse)
def workos_callback(request: WorkOSCallbackRequest):
    """OAuth (hosted AuthKit): troca o code por um user autenticado e delega no
    helper partilhado. DORMENTE — fica para a futura activação de Google/Microsoft.
    """
    client = _get_workos_client()
    try:
        auth_response = client.user_management.authenticate_with_code(code=request.code)
    except WorkOSError as e:
        # code inválido/expirado ou erro do WorkOS → 401 limpo (nunca 500).
        raise HTTPException(
            status_code=401, detail="workos_authentication_failed"
        ) from e
    return _complete_workos_login(auth_response.user)


# ─────────────────────────────────────────────
# WorkOS HEADLESS — a nossa UI valida credenciais via API (sem redirect)
# ─────────────────────────────────────────────
# Caminho ACTIVO: o frontend chama estes endpoints directamente. O OAuth hospedado
# (acima) fica dormente. password-login devolve a NOSSA sessão opaca; forgot/reset
# delegam o ciclo de password reset no WorkOS (email gerido + token).

class PasswordLoginRequest(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., max_length=200)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., max_length=255)


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., max_length=2000)
    new_password: str = Field(..., max_length=200)


@app.post("/auth/workos/password-login", response_model=LoginResponse)
def workos_password_login(request: PasswordLoginRequest):
    """Login headless: valida email+password no WorkOS (sem redirect) e, em caso
    de sucesso, faz o mesmo match/sessão do callback OAuth.
    """
    client = _get_workos_client()
    try:
        auth_response = client.user_management.authenticate_with_password(
            email=request.email,
            password=request.password,
        )
    except RateLimitExceededError as e:
        raise HTTPException(
            status_code=429,
            detail="Demasiados pedidos. Tente novamente em alguns minutos.",
        ) from e
    except WorkOSError as e:
        # Mensagem estável — não revela se o erro é o email ou a password.
        raise HTTPException(status_code=401, detail="invalid_credentials") from e
    return _complete_workos_login(auth_response.user)


@app.post("/auth/workos/forgot-password")
def workos_forgot_password(request: ForgotPasswordRequest):
    """Dispara o email de reset do WorkOS. SEMPRE devolve 200 com corpo neutro,
    mesmo se o email não existir (anti-enumeração de contas).
    """
    client = _get_workos_client()
    try:
        client.user_management.reset_password(email=request.email)
    except WorkOSError:
        # Engole qualquer erro do WorkOS (incl. NotFoundError de email inexistente)
        # — a resposta é sempre neutra para não revelar se a conta existe.
        pass
    return {"status": "ok"}


@app.post("/auth/workos/reset-password")
def workos_reset_password(request: ResetPasswordRequest):
    """Consome o token do email de reset e define a nova password no WorkOS."""
    # Policy do nosso WorkOS: comprimento mínimo 10 (alinhado com o frontend).
    if len(request.new_password) < 10:
        raise HTTPException(
            status_code=400,
            detail="A nova password tem de ter pelo menos 10 caracteres",
        )
    client = _get_workos_client()
    try:
        client.user_management.confirm_password_reset(
            token=request.token,
            new_password=request.new_password,
        )
    except RateLimitExceededError as e:
        raise HTTPException(
            status_code=429,
            detail="Demasiados pedidos. Tente novamente em alguns minutos.",
        ) from e
    except WorkOSError as e:
        # Token inválido/expirado, ou password recusada pela policy → 400 claro.
        raise HTTPException(
            status_code=400, detail="token inválido ou expirado"
        ) from e
    return {"status": "ok"}


# ─────────────────────────────────────────────
# Endpoints de gestão (protegidos por secret key)
# ─────────────────────────────────────────────

def require_admin(x_admin_key: Optional[str] = Header(None)):
    if (
        not SECRET_KEY
        or not x_admin_key
        or not secrets.compare_digest(x_admin_key, SECRET_KEY)
    ):
        raise HTTPException(status_code=403, detail="Acesso negado")


@app.post("/admin/clients", dependencies=[Depends(require_admin)])
def create_client(request: CreateClientRequest):
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO auth.clients (slug, name)
            VALUES (%s, %s)
            RETURNING id
        """, (request.slug, request.company_name))
        client_id = cursor.fetchone()[0]

        password_hash = hash_password(request.admin_password)
        cursor.execute("""
            INSERT INTO auth.users (client_id, email, password_hash, full_name, role)
            VALUES (%s, %s, %s, %s, 'admin')
        """, (client_id, request.admin_email, password_hash, request.admin_name))

        conn.commit()
        return {"status": "ok", "client_id": client_id, "slug": request.slug}
    except psycopg2.errors.UniqueViolation as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=409, detail=f"Conflito de dados: {e.diag.message_detail or 'slug ou email já existem'}")
    finally:
        release_conn(conn)


@app.get("/admin/clients", dependencies=[Depends(require_admin)])
def list_clients():
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.id, c.slug, c.name, c.status,
                   COUNT(u.id) AS user_count
            FROM auth.clients c
            LEFT JOIN auth.users u ON u.client_id = c.id
            GROUP BY c.id, c.slug, c.name, c.status, c.created_at
            ORDER BY c.created_at DESC
        """)
        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "slug": r[1],
                "company_name": r[2],
                "status": r[3],
                "user_count": r[4],
            }
            for r in rows
        ]
    finally:
        release_conn(conn)


@app.post("/admin/users", dependencies=[Depends(require_admin)])
def create_user(request: CreateUserRequest):
    # Valida o role no corpo → HTTP 400, ANTES de tocar na BD. O default da coluna
    # auth.users.role é 'user', que o check constraint users_role_check PROÍBE
    # (só aceita 'admin'/'member'); por isso o role tem de ser escrito explicitamente
    # e validado aqui — caso contrário o INSERT rebentava com 500 (CheckViolation).
    if request.role not in ("admin", "member"):
        raise HTTPException(
            status_code=400,
            detail="role inválido: tem de ser 'admin' ou 'member'",
        )
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM auth.clients WHERE slug = %s", (request.client_slug,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Cliente '{request.client_slug}' não encontrado")

        client_id = row[0]
        password_hash = hash_password(request.password)

        # Cutover M.5: a auth é só WorkOS; já não há troca de password forçada.
        # O password_hash continua a ser gravado — é o que o script de migração
        # sincroniza para o WorkOS. must_change_password fica no default (FALSE).
        cursor.execute("""
            INSERT INTO auth.users (client_id, email, password_hash, full_name, role)
            VALUES (%s, %s, %s, %s, %s)
        """, (client_id, request.email, password_hash, request.full_name, request.role))
        conn.commit()
        return {"status": "ok", "email": request.email}
    except psycopg2.errors.UniqueViolation:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=409, detail="Email já existe para este cliente")
    finally:
        release_conn(conn)


@app.delete("/admin/sessions/cleanup", dependencies=[Depends(require_admin)])
def cleanup_sessions():
    """Apaga sessões expiradas há mais de 7 dias (mantém revogadas recentes para auditoria)."""
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM auth.sessions
            WHERE expires_at < NOW() - INTERVAL '7 days'
        """)
        deleted = cursor.rowcount
        conn.commit()
        return {"status": "ok", "deleted": deleted}
    finally:
        release_conn(conn)
