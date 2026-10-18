import json
import os
import re
import sys
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import anthropic
import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

# Allow `from api.X import Y` when running uvicorn from /app/api directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversation_store import (
    ConversationStore,
    PoolTimeout,
    close_pool,
    emit_usage_event,
    get_connection,
    release_connection,
    run_migrations,
)
from visual_builder import build_visual_payload

from api.adapters.fabric import (
    FabricAPIError,
    FabricAuthenticator,
    FabricAuthError,
    FabricClient,
    FabricConfigError,
)
from api.orchestrator import DEFAULT_MAX_TOKENS, DAXConversationOrchestrator
from api.prompts_fabric import ASSISTANT_NAME, PROMPT_VERSION, build_voice_system_block
from api.realtime_voice import (
    RealtimeError,
    create_client_secret,
    realtime_api_key,
    realtime_available,
)
from api.semantic_models import get_active_model
from api.suggestion_templates import (
    build_context,
    build_context_dax,
    now_in_model_timezone,
    render_templates,
)
from api.whatsapp import (
    DEFAULT_ELEVENLABS_TTS_MODEL,
    DEFAULT_OPENAI_TTS_MODEL,
    DEFAULT_OPENAI_TTS_VOICE,
    InboundMessage,
    WhatsAppConfig,
    allowed_numbers_from_env,
    build_whatsapp_system_block,
    claim_message,
    download_media,
    find_active_user,
    history_for_model,
    is_reset_command,
    parse_inbound,
    run_whatsapp_migrations,
    send_audio,
    send_text,
    session_id_for,
    synthesize_speech_elevenlabs,
    synthesize_speech_openai,
    text_for_speech,
    to_ogg_opus,
    to_whatsapp_format,
    transcribe_audio,
    unwrap_answer,
    upload_media,
    verify_signature,
)
from cors_config import get_allowed_origins

load_dotenv()

# Constant for the conversation_store module column. Sessions from the
# legacy SAP era live under "finance"/"sales"; new Fabric sessions use
# "fabric". Old sessions remain readable but isolated.
MODULE = "fabric"

# timeout=85.0 sits just under the frontend's 90s AbortController, so the
# backend stops waiting on Anthropic before the user has already given up
# (the frontend, in turn, stays under Cloudflare Free's ~100s 524 cut-off).
# NOTE: the SDK applies this timeout PER request, not across the whole
# orchestrator loop. The orchestrator runs up to 6 Anthropic calls per turn
# (get_max_retries() == 4, + 2), so each individual call is capped at 85s but
# the cumulative turn can still exceed that. On timeout the SDK raises
# anthropic.APITimeoutError (a subclass of anthropic.APIError, already handled
# in the orchestrator). Default max_retries (2) still applies.
# Timeout por chamada à API. Tem de acomodar MAX_TOKENS abaixo: a geração corre
# a ~85-110 tokens/s em produção, logo 12k tokens podem levar ~140s. Um timeout
# perde a resposta inteira (não é retomável), ao contrário de uma truncagem.
ANTHROPIC_TIMEOUT_SECONDS = float(os.getenv("ANTHROPIC_TIMEOUT_SECONDS", "180"))

anthropic_client = anthropic.Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    timeout=ANTHROPIC_TIMEOUT_SECONDS,
)
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
VOICE_MODEL = os.getenv("ANTHROPIC_VOICE_MODEL", "claude-haiku-5-5")

# Tecto de output por chamada à API, não da resposta: uma resposta de texto
# cortada neste tecto é retomada pelo orquestrador. Tem de acomodar um turno
# inteiro de tool_use (várias queries DAX), que só é parcialmente recuperável.
# Manter ANTHROPIC_TIMEOUT_SECONDS acima de MAX_TOKENS / ~85 tokens por segundo.
# Ver DEFAULT_MAX_TOKENS / _MAX_CONTINUATIONS em orchestrator.py.
MAX_TOKENS = int(os.getenv("ANTHROPIC_MAX_TOKENS", str(DEFAULT_MAX_TOKENS)))
VOICE_MAX_TOKENS = int(os.getenv("ANTHROPIC_VOICE_MAX_TOKENS", "4096"))

# Rate limiting por utilizador nos endpoints que custam API (I.2).
# Discriminante: user_id. Estado em Postgres (ai.api_usage_events).
RATE_LIMIT_PER_MIN = 20
RATE_LIMIT_PER_HOUR = 300

FABRIC_DATASET_ID = os.getenv("FABRIC_DEFAULT_DATASET_ID", "").strip()
if not FABRIC_DATASET_ID:
    raise RuntimeError(
        "FABRIC_DEFAULT_DATASET_ID must be set in environment. "
        "This is the Power BI semantic model ID the app queries against."
    )

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # run_migrations() já correu no import (abaixo). Aqui só garantimos o
    # fecho limpo do pool de conexões no shutdown (F.9).
    yield
    close_pool()


app = FastAPI(title="ChatPBI API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


conversation_store = ConversationStore(history_limit=12)
run_migrations()

# Build singletons used by chat endpoints. Lazily wrap them so an import
# failure does not crash the whole module at startup.
_fabric_authenticator: Optional[FabricAuthenticator] = None
_fabric_client: Optional[FabricClient] = None


def _get_fabric_client() -> FabricClient:
    """Return a singleton FabricClient, building it on first use."""
    global _fabric_authenticator, _fabric_client
    if _fabric_client is None:
        _fabric_authenticator = FabricAuthenticator()
        _fabric_client = FabricClient(_fabric_authenticator)
    return _fabric_client


def _build_orchestrator() -> DAXConversationOrchestrator:
    """Build a fresh orchestrator per request. Cheap — no network."""
    return DAXConversationOrchestrator(
        anthropic_client=anthropic_client,
        fabric_client=_get_fabric_client(),
        dataset_id=FABRIC_DATASET_ID,
        model=MODEL,
        max_tokens=MAX_TOKENS,
    )


def _build_voice_orchestrator() -> DAXConversationOrchestrator:
    return DAXConversationOrchestrator(
        anthropic_client=anthropic_client,
        fabric_client=_get_fabric_client(),
        dataset_id=FABRIC_DATASET_ID,
        model=VOICE_MODEL,
        max_tokens=VOICE_MAX_TOKENS,
    )


class MessageHistoryItem(BaseModel):
    role: str = Field(..., max_length=32)
    content: str = Field(..., max_length=4000)


class ChatRequest(BaseModel):
    session_id: str = Field(..., max_length=64)
    message: str = Field(..., max_length=4000)
    historico: List[MessageHistoryItem] = Field(default_factory=list, max_length=50)
    modelo: Optional[str] = Field(default=None, max_length=64)
    debug: bool = False
    # `module` and `connector_token` were removed in F.5.
    # We still accept them silently if the frontend sends them, but
    # they are ignored. Pydantic by default rejects unknown fields;
    # use `model_config` to allow them through without 422 errors.
    model_config = {"extra": "ignore"}


class VoiceChatRequest(BaseModel):
    session_id: str = Field(..., max_length=64)
    message: str = Field(..., max_length=4000)
    model_config = {"extra": "ignore"}


class SuggestionsRequest(BaseModel):
    language: Optional[str] = Field(default="pt", max_length=16)
    session_id: Optional[str] = Field(default=None, max_length=64)
    model_config = {"extra": "ignore"}


class TTSRequest(BaseModel):
    text: str = Field(..., max_length=5000)
    voice_id: Optional[str] = Field(default=None, max_length=64)


def normalize_history(history: List[MessageHistoryItem]) -> List[dict]:
    messages = []
    for item in history:
        if item.role in {"user", "assistant"}:
            messages.append({"role": item.role, "content": item.content})
    return messages


_http_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_http_bearer),
) -> dict:
    """Validate session token against auth.sessions in Postgres."""
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Token em falta")

    token = credentials.credentials
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.user_id, u.email, u.full_name, u.status, u.role,
                   c.id AS client_id, c.slug AS client_slug, c.name AS company_name,
                   c.status AS client_status
            FROM auth.sessions s
            JOIN auth.users u ON u.id = s.user_id
            JOIN auth.clients c ON c.id = u.client_id
            WHERE s.token = %s
              AND s.expires_at > NOW()
              AND s.revoked_at IS NULL
            """,
            (token,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Sessão inválida ou expirada")
        user_id, email, full_name, user_status, role, client_id, client_slug, company_name, client_status = row
        if user_status != 'active':
            raise HTTPException(status_code=403, detail="Utilizador inactivo")
        if client_status != 'active':
            raise HTTPException(status_code=403, detail="Cliente inactivo")
        return {
            "user_id": user_id,
            "email": email,
            "full_name": full_name,
            "role": role,
            "client_id": client_id,
            "client_slug": client_slug,
            "company_name": company_name,
        }
    finally:
        release_connection(conn)


def require_role(*allowed_roles: str):
    """Dependency factory: exige que o utilizador autenticado tenha um dos roles indicados.

    NOTA: verifica apenas PRIVILÉGIO (role), NÃO tenant. O isolamento por client_id
    é uma checagem separada que cada endpoint sobre dados de um cliente deve fazer
    (ver padrão do check_session_owner, I.18). Um admin do cliente A continua a precisar
    de verificação de client_id para não tocar em recursos do cliente B.
    """
    def _dependency(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(status_code=403, detail="Privilégio insuficiente")
        return current_user
    return _dependency


def check_rate_limit(user_id: int, endpoint: str) -> None:
    """Rate limiting por utilizador, estado em Postgres (ai.api_usage_events).

    Conta os eventos do user_id na última janela; se exceder qualquer limite
    (por minuto OU por hora) levanta 429. Caso contrário regista o evento e
    deixa prosseguir. Aplica-se apenas aos endpoints que custam API.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM ai.api_usage_events
            WHERE user_id = %s
              AND created_at > NOW() - make_interval(mins => %s)
            """,
            (user_id, 1),
        )
        if cursor.fetchone()[0] >= RATE_LIMIT_PER_MIN:
            raise HTTPException(status_code=429, detail="Demasiados pedidos. Aguarde um momento.")

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM ai.api_usage_events
            WHERE user_id = %s
              AND created_at > NOW() - make_interval(hours => %s)
            """,
            (user_id, 1),
        )
        if cursor.fetchone()[0] >= RATE_LIMIT_PER_HOUR:
            raise HTTPException(status_code=429, detail="Demasiados pedidos. Aguarde um momento.")

        cursor.execute(
            """
            INSERT INTO ai.api_usage_events (user_id, endpoint)
            VALUES (%s, %s)
            """,
            (user_id, endpoint),
        )
        conn.commit()
    finally:
        release_connection(conn)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/conversations")
def list_conversations(current_user: dict = Depends(get_current_user)):
    try:
        sessions = conversation_store.list_sessions(
            module=MODULE,
            user_id=current_user["user_id"],
        )
        return {"status": "success", "conversations": sessions}
    except PoolTimeout:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/conversations/{session_id}/messages")
def get_conversation_messages(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    if not conversation_store.check_session_owner(
        session_id, current_user["user_id"], current_user["client_id"], module=MODULE
    ):
        raise HTTPException(status_code=403, detail="Acesso negado")
    try:
        messages = conversation_store.get_session_messages(session_id, module=MODULE)
        return {"status": "success", "session_id": session_id, "messages": messages}
    except PoolTimeout:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.patch("/conversations/{session_id}/title")
def rename_conversation(
    session_id: str,
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    if not conversation_store.check_session_owner(
        session_id, current_user["user_id"], current_user["client_id"], module=MODULE
    ):
        raise HTTPException(status_code=403, detail="Acesso negado")
    try:
        conversation_store.rename_session(session_id, title, module=MODULE)
        return {"status": "success"}
    except PoolTimeout:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/conversations/{session_id}")
def delete_conversation(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    if not conversation_store.check_session_owner(
        session_id, current_user["user_id"], current_user["client_id"], module=MODULE
    ):
        raise HTTPException(status_code=403, detail="Acesso negado")
    try:
        conversation_store.clear(session_id, module=MODULE)
        return {"status": "success"}
    except PoolTimeout:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/chat/reset")
def reset_chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    if not conversation_store.check_session_owner(
        request.session_id, current_user["user_id"], current_user["client_id"], module=MODULE
    ):
        raise HTTPException(status_code=403, detail="Acesso negado")
    try:
        conversation_store.clear(request.session_id, module=MODULE)
        return {
            "session_id": request.session_id,
            "status": "success",
            "answer": "Sessão limpa com sucesso.",
        }
    except PoolTimeout:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/chat/v2")
def chat_v2(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Main chat endpoint. Uses DAXConversationOrchestrator against the
    active Power BI semantic model (SEMANTIC_MODEL / FABRIC_DEFAULT_DATASET_ID).
    """
    request_start = time.monotonic()
    check_rate_limit(current_user["user_id"], "/chat/v2")
    try:
        conversation_store.ensure_session(
            request.session_id,
            module=MODULE,
            user_id=current_user["user_id"],
        )
        if not conversation_store.check_session_owner(
            request.session_id, current_user["user_id"], current_user["client_id"], module=MODULE
        ):
            raise HTTPException(status_code=403, detail="Acesso negado")
        # Fetch persisted history BEFORE appending the current user message,
        # so the orchestrator does not see the current question twice
        # (once in history, once as user_message param).
        stored_history = conversation_store.get_history(
            request.session_id, module=MODULE,
        )
        conversation_store.append_user_message(
            request.session_id, request.message, module=MODULE,
        )
        # Merge with optional history from the request body (for clients
        # that maintain their own context like Lovable).
        request_history = normalize_history(request.historico)
        combined_history = (stored_history + request_history)[-12:]

        orchestrator = _build_orchestrator()
        result = orchestrator.run(
            user_message=request.message,
            conversation_history=combined_history,
        )

        # Build visual payload from the captured visual_hint + DAX rows.
        # The [visual] log distinguishes a built visual from the three skip
        # paths (no rows / model omitted the hint / builder returned None),
        # so we stop being blind to why a turn falls back to text. `cols` on
        # the skip line surfaces the real DAX column names for diagnosis.
        visual = None
        if not result.dax_rows:
            _visual_reason = "no_dax_rows"
        elif not result.visual_hint:
            _visual_reason = "no_visual_hint_from_model"
        else:
            visual = build_visual_payload(
                visual_hint=result.visual_hint,
                result={
                    "ok": True,
                    "rows": result.dax_rows,
                    "columns": result.dax_columns or [],
                },
            )
            _visual_reason = None if visual else "builder_returned_none"

        if visual:
            print(
                f"[visual] built type={visual.get('visual_type')}/"
                f"{visual.get('chart_type', '-')} "
                f"rows={len(result.dax_rows)} "
                f"hint_chart={result.visual_hint.get('chart_type')}"
            )
        else:
            _hint_chart = (
                result.visual_hint.get("chart_type") if result.visual_hint else None
            )
            print(
                f"[visual] skipped reason={_visual_reason} "
                f"hint={bool(result.visual_hint)} hint_chart={_hint_chart} "
                f"rows={len(result.dax_rows or [])} "
                f"cols={result.dax_columns or []}"
            )

        # Persist the assistant answer for follow-up turns
        conversation_store.append_assistant_message(
            request.session_id,
            {
                "message_type": "assistant_response",
                "answer": result.answer,
                "response_mode": "visual" if visual else "text",
                "visual": visual,
                "next_step_suggestions": result.next_step_suggestions,
            },
            module=MODULE,
        )

        payload: Dict[str, Any] = {
            "session_id": request.session_id,
            "status": "success",
            "answer": result.answer,
            "response_mode": "visual" if visual else "text",
            "visual": visual,
            "next_step_suggestions": result.next_step_suggestions,
            "error": result.error,
        }

        if request.debug:
            payload["debug"] = {
                "prompt_version": PROMPT_VERSION,
                "dax_query": result.dax_query,
                "dax_rows": result.dax_rows,
                "dax_columns": result.dax_columns,
                "iterations": [vars(it) for it in result.iterations],
                "total_latency_ms": result.total_latency_ms,
                "total_cache_read_tokens": result.total_cache_read_tokens,
                "total_cache_write_tokens": result.total_cache_write_tokens,
            }

        # Timing breakdown: total wall-clock minus the measured Anthropic and
        # Fabric slices yields "other" (DB lookups, history, serialization).
        total_ms = int((time.monotonic() - request_start) * 1000)
        anthropic_ms = result.total_latency_ms
        n_iterations = len(result.iterations)
        fabric_ms = sum(
            it.dax_latency_ms
            for it in result.iterations
            if it.dax_latency_ms is not None
        )
        # Claude pode emitir várias execute_dax na mesma iteração, por isso a
        # contagem vem de dax_call_count e não do número de iterações.
        n_queries = sum(it.dax_call_count for it in result.iterations)
        other_ms = total_ms - anthropic_ms - fabric_ms
        print(
            f"[timing] /chat/v2 total={total_ms}ms | "
            f"anthropic={anthropic_ms}ms "
            f"({n_iterations} {'iteration' if n_iterations == 1 else 'iterations'}) | "
            f"fabric={fabric_ms}ms "
            f"({n_queries} {'query' if n_queries == 1 else 'queries'}) | "
            f"other={other_ms}ms"
        )

        # Instrumentação de consumo (O.1): ponto único de emissão. Endpoint
        # síncrono (threadpool, F.13) → INSERT inline é seguro, não bloqueia o
        # event loop. emit_usage_event é best-effort (nunca levanta).
        emit_usage_event(
            client_id=current_user["client_id"],
            user_id=current_user["user_id"],
            session_id=request.session_id,
            endpoint="/chat/v2",
            provider="anthropic",
            model=MODEL,
            input_tokens=result.total_input_tokens,
            output_tokens=result.total_output_tokens,
            cache_read_tokens=result.total_cache_read_tokens,
            cache_write_tokens=result.total_cache_write_tokens,
            latency_ms=result.total_latency_ms,
            iteration_count=len(result.iterations),
            status="error" if result.error else "success",
        )

        return payload

    except HTTPException:
        raise
    except PoolTimeout:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/chat/voice")
def chat_voice(
    request: VoiceChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Voice-mode chat endpoint. Same orchestrator, but adds the voice
    system block (no markdown, max 2 sentences, no visualizations,
    no next_step_suggestions).
    """
    check_rate_limit(current_user["user_id"], "/chat/voice")
    try:
        conversation_store.ensure_session(
            request.session_id,
            module=MODULE,
            user_id=current_user["user_id"],
        )
        if not conversation_store.check_session_owner(
            request.session_id, current_user["user_id"], current_user["client_id"], module=MODULE
        ):
            raise HTTPException(status_code=403, detail="Acesso negado")
        # Fetch persisted history BEFORE appending the current user message
        # (see /chat/v2 for rationale).
        stored_history = conversation_store.get_history(
            request.session_id, module=MODULE,
        )
        conversation_store.append_user_message(
            request.session_id, request.message, module=MODULE,
        )
        combined_history = stored_history[-12:]

        orchestrator = _build_voice_orchestrator()
        result = orchestrator.run(
            user_message=request.message,
            conversation_history=combined_history,
            extra_system_blocks=[build_voice_system_block()],
        )

        conversation_store.append_assistant_message(
            request.session_id,
            {
                "message_type": "voice_response",
                "answer": result.answer,
            },
            module=MODULE,
        )

        # Instrumentação de consumo (O.1) — ver /chat/v2. Mesmo orquestrador,
        # modelo Haiku (VOICE_MODEL). Endpoint síncrono (threadpool) → inline.
        emit_usage_event(
            client_id=current_user["client_id"],
            user_id=current_user["user_id"],
            session_id=request.session_id,
            endpoint="/chat/voice",
            provider="anthropic",
            model=VOICE_MODEL,
            input_tokens=result.total_input_tokens,
            output_tokens=result.total_output_tokens,
            cache_read_tokens=result.total_cache_read_tokens,
            cache_write_tokens=result.total_cache_write_tokens,
            latency_ms=result.total_latency_ms,
            iteration_count=len(result.iterations),
            status="error" if result.error else "success",
        )

        return {
            "status": "success",
            "session_id": request.session_id,
            "answer": result.answer,
        }

    except HTTPException:
        raise
    except PoolTimeout:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/model")
def model_info(current_user: dict = Depends(get_current_user)):
    """Nome, assunto e moeda do modelo semântico activo (para a tela)."""
    model = get_active_model()
    return {
        "status": "success",
        "name": model.MODEL_NAME,
        "description": model.MODEL_DESCRIPTION,
        "subject": model.DATA_SUBJECT,
        "currency": getattr(model, "CURRENCY_CODE", "BRL"),
        "source": "Power BI",
    }


@app.get("/voice/config")
def voice_config(current_user: dict = Depends(get_current_user)):
    """Diz ao frontend que vozes estão ligadas neste ambiente.

    realtime: voz ao vivo da OpenAI (OPENAI_API_KEY).
    classic: gravação + ElevenLabs STT/TTS (ELEVENLABS_API_KEY).
    """
    return {
        "status": "success",
        "realtime": realtime_available(),
        "classic": bool(os.getenv("ELEVENLABS_API_KEY", "").strip()),
    }


@app.post("/voice/realtime/session")
def realtime_session(current_user: dict = Depends(get_current_user)):
    """Abre uma sessão de voz ao vivo: devolve a chave efémera da OpenAI.

    A OPENAI_API_KEY fica no servidor. O browser recebe só o client secret
    (expira em minutos) e liga-se por WebRTC à OpenAI. Os dados continuam a
    vir do /chat/voice, chamado pelo frontend quando o modelo de voz usa a
    ferramenta consultar_dados.
    """
    api_key = realtime_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY não configurada")
    check_rate_limit(current_user["user_id"], "/voice/realtime/session")
    start = time.monotonic()
    try:
        secret = create_client_secret(api_key)
    except RealtimeError as exc:
        print(f"[realtime] erro ao criar a sessão: {exc}")
        raise HTTPException(
            status_code=502, detail="Não foi possível abrir a voz ao vivo agora."
        ) from exc
    latency_ms = int((time.monotonic() - start) * 1000)
    print(f"[realtime] sessão criada model={secret.model} latency={latency_ms}ms")

    emit_usage_event(
        client_id=current_user["client_id"],
        user_id=current_user["user_id"],
        endpoint="/voice/realtime/session",
        provider="openai",
        model=secret.model,
        latency_ms=latency_ms,
        status="success",
    )

    return {
        "status": "success",
        "client_secret": secret.value,
        "expires_at": secret.expires_at,
        "model": secret.model,
    }


@app.post("/suggestions")
def get_suggestions(
    request: SuggestionsRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Returns 6 starter suggestions for the active semantic model. Dates are
    computed in Python; the dynamic placeholders of the model's templates are
    resolved via a single lightweight DAX query against the Power BI model.
    Failure leaves those templates out — the endpoint never returns 5xx for
    context resolution issues.
    """
    now = now_in_model_timezone()
    rows = None
    context_error: Optional[str] = None

    try:
        fabric = _get_fabric_client()
        # FabricClient normalizes qualified names ("Tabela[Coluna]" → "Coluna").
        result = fabric.execute_query(FABRIC_DATASET_ID, build_context_dax(now))
        rows = result.rows
    except (FabricAPIError, FabricAuthError, FabricConfigError) as exc:
        context_error = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        context_error = f"unexpected: {type(exc).__name__}: {exc}"

    context = build_context(rows, now)
    suggestions = render_templates(context)

    response: Dict[str, Any] = {
        "status": "success",
        "module": MODULE,
        "language": request.language or "pt",
        "suggestions": suggestions,
        "context": context,
    }
    if context_error:
        # Surface the issue without 500'ing — frontend can log this.
        response["context_warning"] = context_error
    return response


@app.post("/stt")
async def speech_to_text(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Converte áudio em texto via ElevenLabs Speech-to-Text.
    Aceita audio/webm, audio/mp4, audio/wav, audio/ogg.
    Funciona no iPhone via MediaRecorder API.
    """
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ELEVENLABS_API_KEY não configurada")

    # Lê o body do áudio directamente
    audio_data = await request.body()
    content_type = request.headers.get("content-type", "audio/webm")

    if not audio_data:
        raise HTTPException(status_code=400, detail="Áudio não recebido")

    # Determina a extensão pelo content-type
    ext_map = {
        "audio/webm": "webm",
        "audio/mp4": "mp4",
        "audio/wav": "wav",
        "audio/ogg": "ogg",
        "audio/mpeg": "mp3",
    }
    ext = ext_map.get(content_type.split(";")[0].strip(), "webm")

    url = "https://api.elevenlabs.io/v1/speech-to-text"
    headers = {"xi-api-key": api_key}

    try:
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            response = await http_client.post(
                url,
                headers=headers,
                files={"file": (f"audio.{ext}", audio_data, content_type)},
                data={"model_id": "scribe_v1"},
            )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"ElevenLabs STT erro: {response.text}"
            )

        result = response.json()
        text = result.get("text", "").strip()

        if not text:
            raise HTTPException(status_code=400, detail="Não foi possível transcrever o áudio")

        # Instrumentação de consumo (O.1): endpoint async → emitir via
        # run_in_threadpool DEPOIS da resposta pronta, nunca no event loop (F.13).
        # Proxy de uso: chars do transcrito + bytes do áudio de entrada.
        # TODO(O.x follow-up): a unidade de faturação real do STT é a DURAÇÃO do
        # áudio (minutos), não chars — capturar a duração fica para um follow-up.
        await run_in_threadpool(
            emit_usage_event,
            client_id=current_user["client_id"],
            user_id=current_user["user_id"],
            endpoint="/stt",
            provider="elevenlabs",
            model="scribe_v1",
            char_count=len(text),
            audio_bytes=len(audio_data),
            status="success",
        )

        return {"status": "ok", "text": text}

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout na transcrição")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tts")
async def text_to_speech(
    request: TTSRequest,
    current_user: dict = Depends(get_current_user),
):
    """Converte texto em áudio via ElevenLabs."""
    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = request.voice_id or os.getenv("ELEVENLABS_VOICE_ID")

    if not api_key:
        raise HTTPException(status_code=500, detail="ELEVENLABS_API_KEY não configurada")
    if not voice_id:
        raise HTTPException(status_code=500, detail="ELEVENLABS_VOICE_ID não configurado")

    # Limpa o texto — remove markdown antes de enviar para o TTS
    text = request.text
    text = re.sub(r'[*]{1,2}(.+?)[*]{1,2}', r'\1', text)
    text = re.sub(r'#{1,6}\s+', '', text)
    text = re.sub(r'[|][^\r\n]+[|]', '', text)
    text = re.sub(r'[-]\s+', '', text)
    text = re.sub(r'\n+', ' ', text).strip()

    # Limita o texto a 2500 caracteres para não gastar créditos em excesso
    if len(text) > 2500:
        text = text[:2500]

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            response = await http_client.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"ElevenLabs erro: {response.text}"
            )

        # Instrumentação de consumo (O.1): endpoint async → emitir via
        # run_in_threadpool DEPOIS da resposta pronta, nunca no event loop (F.13).
        # char_count = len(text) já limpo e truncado (≤2500) — os chars
        # realmente enviados ao ElevenLabs, que é a unidade de faturação do TTS.
        await run_in_threadpool(
            emit_usage_event,
            client_id=current_user["client_id"],
            user_id=current_user["user_id"],
            endpoint="/tts",
            provider="elevenlabs",
            model="eleven_multilingual_v2",
            char_count=len(text),
            status="success",
        )

        return Response(
            content=response.content,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=response.mp3"},
        )

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout na geração de áudio")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Canal do WhatsApp (WhatsApp Cloud API, oficial da Meta)
# ---------------------------------------------------------------------------
# Liga só com WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_VERIFY_TOKEN e
# WHATSAPP_APP_SECRET. Sem elas, as rotas /whatsapp/* respondem 404.
# Só respondem os números de WHATSAPP_ALLOWED_NUMBERS (numero=email), cada um
# ligado a um usuário ativo de auth.users. Ver api/whatsapp.py.

WHATSAPP_CONFIG: Optional[WhatsAppConfig] = WhatsAppConfig.from_env()
WHATSAPP_MODEL = os.getenv("WHATSAPP_MODEL", "").strip() or MODEL
OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
# Voz da resposta quando a pergunta veio em áudio: openai (padrão) ou elevenlabs.
WHATSAPP_TTS_PROVIDER = (os.getenv("WHATSAPP_TTS_PROVIDER", "openai").strip() or "openai").lower()
WHATSAPP_TTS_MODEL = os.getenv("WHATSAPP_TTS_MODEL", "").strip()
WHATSAPP_TTS_VOICE = os.getenv("WHATSAPP_TTS_VOICE", "").strip()

if WHATSAPP_CONFIG is not None:
    run_whatsapp_migrations()

WHATSAPP_TEXTS = {
    "erro": "Não consegui responder agora. Tente de novo em alguns minutos.",
    "limite": "Recebi muitas perguntas seguidas. Aguarde um minuto e pergunte de novo.",
    "tipo": "Por enquanto eu respondo a mensagens de texto e de áudio.",
    "audio_off": "Por enquanto eu respondo só a mensagens de texto.",
    "audio_vazio": "Não consegui entender o áudio. Pode escrever a pergunta?",
    "vazio": "Mande a sua pergunta sobre os dados.",
    "novo": "Pronto, comecei uma conversa nova. Qual é a sua pergunta?",
}


def _build_whatsapp_orchestrator() -> DAXConversationOrchestrator:
    return DAXConversationOrchestrator(
        anthropic_client=anthropic_client,
        fabric_client=_get_fabric_client(),
        dataset_id=FABRIC_DATASET_ID,
        model=WHATSAPP_MODEL,
        max_tokens=MAX_TOKENS,
    )


def _whatsapp_question(config: WhatsAppConfig, message: InboundMessage) -> Optional[str]:
    """Texto da pergunta. Para áudio, transcreve. None quando já respondeu."""
    if message.type == "text":
        if not message.text:
            send_text(config, message.from_phone, WHATSAPP_TEXTS["vazio"])
            return None
        return message.text
    if message.type == "audio":
        openai_key = realtime_api_key()
        if not openai_key or not message.media_id:
            send_text(config, message.from_phone, WHATSAPP_TEXTS["audio_off"])
            return None
        audio, mime_type = download_media(config, message.media_id)
        text = transcribe_audio(audio, mime_type, openai_key, OPENAI_TRANSCRIBE_MODEL)
        if not text:
            send_text(config, message.from_phone, WHATSAPP_TEXTS["audio_vazio"])
            return None
        return text
    send_text(config, message.from_phone, WHATSAPP_TEXTS["tipo"])
    return None


def _reply_with_audio(config: WhatsAppConfig, to_phone: str, answer: str) -> Optional[str]:
    """Responde em mensagem de voz. Devolve "provedor/modelo" da voz usada, ou
    None quando não deu (o chamador manda a resposta em texto)."""
    spoken = text_for_speech(answer)
    if not spoken:
        return None
    try:
        if WHATSAPP_TTS_PROVIDER == "elevenlabs":
            api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
            voice_id = WHATSAPP_TTS_VOICE or os.getenv("ELEVENLABS_VOICE_ID", "").strip()
            if not api_key or not voice_id:
                print("[whatsapp] voz ElevenLabs sem ELEVENLABS_API_KEY ou voz: resposta em texto")
                return None
            mp3, tts_model = synthesize_speech_elevenlabs(
                spoken, api_key, voice_id, WHATSAPP_TTS_MODEL or DEFAULT_ELEVENLABS_TTS_MODEL
            )
            used = f"elevenlabs/{tts_model}"
        else:
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                print("[whatsapp] voz sem OPENAI_API_KEY: resposta em texto")
                return None
            tts_model = WHATSAPP_TTS_MODEL or DEFAULT_OPENAI_TTS_MODEL
            mp3 = synthesize_speech_openai(
                spoken, api_key, WHATSAPP_TTS_VOICE or DEFAULT_OPENAI_TTS_VOICE, tts_model
            )
            used = f"openai/{tts_model}"
        media_id = upload_media(config, to_ogg_opus(mp3), "audio/ogg", "resposta.ogg")
        if not send_audio(config, to_phone, media_id):
            return None
        print(f"[whatsapp] resposta em áudio enviada ({used})")
        return used
    except Exception as exc:  # noqa: BLE001 - cai para a resposta em texto
        print(f"[whatsapp] resposta em áudio falhou, vai em texto: {exc}")
        return None


def handle_whatsapp_message(message: InboundMessage) -> None:
    """Responde uma mensagem do WhatsApp. Roda em segundo plano.

    O webhook já devolveu 200 à Meta, então nenhum erro daqui sobe: tudo vira
    log e, quando dá, uma resposta curta para a pessoa.
    """
    config = WHATSAPP_CONFIG
    if config is None:
        return

    email = allowed_numbers_from_env().get(message.from_phone)
    if not email:
        print(f"[whatsapp] número fora da lista ignorado: ...{message.from_phone[-4:]}")
        return

    try:
        if not claim_message(message.message_id, message.from_phone):
            print(f"[whatsapp] mensagem repetida ignorada: {message.message_id}")
            return

        user = find_active_user(email)
        if user is None:
            print(f"[whatsapp] número sem usuário ativo no app: ...{message.from_phone[-4:]}")
            return

        try:
            check_rate_limit(user["user_id"], "/whatsapp/webhook")
        except HTTPException:
            send_text(config, message.from_phone, WHATSAPP_TEXTS["limite"])
            return

        question = _whatsapp_question(config, message)
        if question is None:
            return

        session_id = session_id_for(message.from_phone)
        conversation_store.ensure_session(session_id, module=MODULE, user_id=user["user_id"])
        if not conversation_store.check_session_owner(
            session_id, user["user_id"], user["client_id"], module=MODULE
        ):
            print(f"[whatsapp] conversa de outro usuário: {session_id}")
            return

        if is_reset_command(question):
            conversation_store.clear(session_id, module=MODULE)
            send_text(config, message.from_phone, WHATSAPP_TEXTS["novo"])
            return

        stored_history = conversation_store.get_history(session_id, module=MODULE)
        conversation_store.append_user_message(session_id, question, module=MODULE)

        model = get_active_model()
        # Áudio usa o mesmo modelo do texto: o bloco de voz só muda o formato.
        voice = message.type == "audio"
        system_blocks = [build_whatsapp_system_block(ASSISTANT_NAME, model.DATA_SUBJECT)]
        if voice:
            system_blocks.append(build_voice_system_block())
        result = _build_whatsapp_orchestrator().run(
            user_message=question,
            conversation_history=history_for_model(stored_history[-12:]),
            extra_system_blocks=system_blocks,
        )
        answer = to_whatsapp_format(unwrap_answer(result.answer)) or WHATSAPP_TEXTS["erro"]

        conversation_store.append_assistant_message(
            session_id,
            {"message_type": "whatsapp_response", "answer": answer},
            module=MODULE,
        )
        emit_usage_event(
            client_id=user["client_id"],
            user_id=user["user_id"],
            session_id=session_id,
            endpoint="/whatsapp/webhook",
            provider="anthropic",
            model=WHATSAPP_MODEL,
            input_tokens=result.total_input_tokens,
            output_tokens=result.total_output_tokens,
            cache_read_tokens=result.total_cache_read_tokens,
            cache_write_tokens=result.total_cache_write_tokens,
            latency_ms=result.total_latency_ms,
            iteration_count=len(result.iterations),
            status="error" if result.error else "success",
        )
        tts_used = _reply_with_audio(config, message.from_phone, answer) if voice else None
        if tts_used:
            provider, _, tts_model = tts_used.partition("/")
            emit_usage_event(
                client_id=user["client_id"],
                user_id=user["user_id"],
                session_id=session_id,
                endpoint="/whatsapp/webhook",
                provider=provider,
                model=tts_model,
                char_count=len(text_for_speech(answer)),
                status="success",
            )
            return
        send_text(config, message.from_phone, answer)
        print(f"[whatsapp] resposta em texto enviada para ...{message.from_phone[-4:]}")
    except Exception as exc:  # noqa: BLE001 - nada pode derrubar a tarefa
        print(f"[whatsapp] erro ao responder {message.message_id}: {exc}")
        try:
            send_text(config, message.from_phone, WHATSAPP_TEXTS["erro"])
        except Exception as send_exc:  # noqa: BLE001
            print(f"[whatsapp] erro ao avisar do erro: {send_exc}")


@app.get("/whatsapp/webhook")
def whatsapp_verify(request: Request):
    """Verificação do webhook pela Meta (hub.mode, hub.verify_token, hub.challenge)."""
    if WHATSAPP_CONFIG is None:
        raise HTTPException(status_code=404, detail="Canal do WhatsApp desligado")
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == WHATSAPP_CONFIG.verify_token
    ):
        return PlainTextResponse(params.get("hub.challenge", ""))
    raise HTTPException(status_code=403, detail="Token de verificação inválido")


@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    """Recebe as mensagens da Meta. Responde 200 logo e trata em segundo plano."""
    if WHATSAPP_CONFIG is None:
        raise HTTPException(status_code=404, detail="Canal do WhatsApp desligado")
    body = await request.body()
    if not verify_signature(
        WHATSAPP_CONFIG.app_secret, body, request.headers.get("X-Hub-Signature-256")
    ):
        raise HTTPException(status_code=401, detail="Assinatura inválida")
    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        raise HTTPException(status_code=400, detail="JSON inválido")
    for message in parse_inbound(payload):
        background_tasks.add_task(handle_whatsapp_message, message)
    return {"status": "ok"}
