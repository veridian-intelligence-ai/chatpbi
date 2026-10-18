"""Canal do WhatsApp: perguntas ao modelo semântico pela WhatsApp Cloud API.

Usa só a API oficial da Meta (WhatsApp Business Platform, Cloud API). A Meta
entrega cada mensagem recebida no webhook `/whatsapp/webhook` da API; a
resposta volta pelo endpoint `/{phone_number_id}/messages` da Graph API.

Quem pode perguntar: só os números da lista `WHATSAPP_ALLOWED_NUMBERS`, cada
um ligado ao e-mail de um usuário ativo do app (`auth.users`). Número fora da
lista é ignorado em silêncio. As permissões são as do app: o service principal
consulta o modelo inteiro, então este canal só serve para modelos sem RLS.

Áudio: a mensagem de voz recebida é transcrita pela OpenAI e, quando a
pergunta veio em áudio, a resposta volta em áudio (OpenAI por padrão, ou
ElevenLabs), convertida para OGG/Opus com o ffmpeg.

Este módulo não toca no FastAPI: tem a configuração, a assinatura do webhook,
a leitura do payload, o envio, o áudio e as tabelas. As rotas ficam em main.py.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx
from conversation_store import get_connection, release_connection

GRAPH_BASE_URL = "https://graph.facebook.com"
DEFAULT_GRAPH_VERSION = "v25.0"
OPENAI_TRANSCRIBE_URL = "https://api.openai.com/v1/audio/transcriptions"
OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"
# Voz da resposta em áudio: OpenAI por padrão (a mesma chave da voz ao vivo).
DEFAULT_OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_OPENAI_TTS_VOICE = "coral"
OPENAI_TTS_INSTRUCTIONS = (
    "Fale em português do Brasil, num tom natural de conversa, como um colega "
    "explicando um número: calmo, claro e sem pressa."
)
# Alternativa: ElevenLabs, quando WHATSAPP_TTS_PROVIDER=elevenlabs.
ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
DEFAULT_ELEVENLABS_TTS_MODEL = "eleven_v4"
FALLBACK_ELEVENLABS_TTS_MODEL = "eleven_multilingual_v2"
# Teto de caracteres falados por resposta em áudio (custo da voz).
MAX_TTS_CHARS = 1200

# Limite de caracteres de uma mensagem de texto do WhatsApp.
MAX_TEXT_LENGTH = 4096
# Limite de tamanho do áudio aceito para transcrição (16 MB, o teto da Meta
# para áudio).
MAX_AUDIO_BYTES = 16 * 1024 * 1024
HTTP_TIMEOUT_SECONDS = 30.0

# Palavras que limpam o histórico da conversa no WhatsApp.
RESET_COMMANDS = {"novo", "nova conversa", "/novo", "reset", "/reset"}


@dataclass(frozen=True)
class WhatsAppConfig:
    """Configuração do canal, lida das variáveis de ambiente."""

    token: str
    phone_number_id: str
    verify_token: str
    app_secret: str
    graph_version: str = DEFAULT_GRAPH_VERSION

    @classmethod
    def from_env(cls) -> Optional["WhatsAppConfig"]:
        """Devolve a configuração, ou None quando o canal está desligado.

        O canal só liga com as quatro variáveis obrigatórias. Sem
        `WHATSAPP_APP_SECRET` não há como conferir a assinatura do webhook,
        então o canal fica desligado.
        """
        token = os.getenv("WHATSAPP_TOKEN", "").strip()
        phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
        verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip()
        app_secret = os.getenv("WHATSAPP_APP_SECRET", "").strip()
        if not (token and phone_number_id and verify_token and app_secret):
            return None
        graph_version = (
            os.getenv("WHATSAPP_GRAPH_VERSION", "").strip() or DEFAULT_GRAPH_VERSION
        )
        return cls(
            token=token,
            phone_number_id=phone_number_id,
            verify_token=verify_token,
            app_secret=app_secret,
            graph_version=graph_version,
        )

    @property
    def messages_url(self) -> str:
        return f"{GRAPH_BASE_URL}/{self.graph_version}/{self.phone_number_id}/messages"

    @property
    def upload_url(self) -> str:
        return f"{GRAPH_BASE_URL}/{self.graph_version}/{self.phone_number_id}/media"

    def media_url(self, media_id: str) -> str:
        return f"{GRAPH_BASE_URL}/{self.graph_version}/{media_id}"


@dataclass(frozen=True)
class InboundMessage:
    """Uma mensagem recebida, já tirada do payload do webhook."""

    message_id: str
    from_phone: str
    type: str
    text: str = ""
    media_id: str = ""
    mime_type: str = ""


# ---------------------------------------------------------------------------
# Números autorizados
# ---------------------------------------------------------------------------

def normalize_phone(raw: str) -> str:
    """Deixa só os dígitos (formato da Meta: código do país + número)."""
    return re.sub(r"\D", "", raw or "")


def parse_allowed_numbers(raw: Optional[str]) -> Dict[str, str]:
    """Lê `WHATSAPP_ALLOWED_NUMBERS`: pares `numero=email` separados por vírgula.

    Exemplo: `351912345678=ana@empresa.com, 5511987654321=joao@empresa.com`.
    Par sem número ou sem e-mail é ignorado.
    """
    allowed: Dict[str, str] = {}
    for item in (raw or "").split(","):
        if "=" not in item:
            continue
        phone_part, email_part = item.split("=", 1)
        phone = normalize_phone(phone_part)
        email = email_part.strip().lower()
        if phone and email:
            allowed[phone] = email
    return allowed


def allowed_numbers_from_env() -> Dict[str, str]:
    return parse_allowed_numbers(os.getenv("WHATSAPP_ALLOWED_NUMBERS"))


# ---------------------------------------------------------------------------
# Webhook: assinatura e payload
# ---------------------------------------------------------------------------

def verify_signature(app_secret: str, body: bytes, header: Optional[str]) -> bool:
    """Confere o cabeçalho `X-Hub-Signature-256` (HMAC-SHA256 do corpo cru)."""
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):].strip())


def parse_inbound(payload: Dict[str, Any]) -> List[InboundMessage]:
    """Tira as mensagens do payload do webhook.

    Ignora os eventos de status (entregue, lido) e tudo o que não for do
    objeto `whatsapp_business_account`.
    """
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        return []
    messages: List[InboundMessage] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for msg in value.get("messages") or []:
                message_id = str(msg.get("id") or "")
                from_phone = normalize_phone(str(msg.get("from") or ""))
                msg_type = str(msg.get("type") or "")
                if not message_id or not from_phone:
                    continue
                if msg_type == "text":
                    body = ((msg.get("text") or {}).get("body") or "").strip()
                    messages.append(InboundMessage(message_id, from_phone, "text", text=body))
                elif msg_type == "audio":
                    audio = msg.get("audio") or {}
                    messages.append(
                        InboundMessage(
                            message_id,
                            from_phone,
                            "audio",
                            media_id=str(audio.get("id") or ""),
                            mime_type=str(audio.get("mime_type") or ""),
                        )
                    )
                else:
                    messages.append(InboundMessage(message_id, from_phone, msg_type))
    return messages


def is_reset_command(text: str) -> bool:
    return text.strip().lower() in RESET_COMMANDS


# ---------------------------------------------------------------------------
# Texto da resposta
# ---------------------------------------------------------------------------

def to_whatsapp_format(text: str) -> str:
    """Passa o markdown da resposta para a formatação do WhatsApp.

    WhatsApp usa *negrito* e _itálico_, sem títulos nem tabelas. Converte
    **negrito** em *negrito*, tira os # dos títulos e as linhas de separação
    de tabela, e junta linhas em branco repetidas.
    """
    out = text or ""
    out = re.sub(r"\*\*(.+?)\*\*", r"*\1*", out)
    out = re.sub(r"__(.+?)__", r"*\1*", out)
    out = re.sub(r"^\s{0,3}#{1,6}\s*", "", out, flags=re.MULTILINE)
    out = re.sub(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$", "", out, flags=re.MULTILINE)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def unwrap_answer(text: str) -> str:
    """Tira o texto da resposta quando ele vem embrulhado no JSON salvo.

    As respostas ficam no banco como `{"message_type": ..., "answer": ...}`.
    Se o modelo copiar esse formato do histórico, a pessoa recebe o JSON cru
    no WhatsApp. Abre o JSON (mesmo aninhado) e devolve só o `answer`.
    """
    current = (text or "").strip()
    for _ in range(3):
        if not (current.startswith("{") and current.endswith("}")):
            break
        try:
            data = json.loads(current)
        except ValueError:
            break
        if not isinstance(data, dict) or not isinstance(data.get("answer"), str):
            break
        current = data["answer"].strip()
    return current


def history_for_model(history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Histórico com só o texto de cada resposta, sem o JSON salvo no banco."""
    clean: List[Dict[str, str]] = []
    for item in history or []:
        role = item.get("role")
        content = str(item.get("content") or "")
        if role == "assistant":
            content = unwrap_answer(content)
        if role in {"user", "assistant"} and content:
            clean.append({"role": role, "content": content})
    return clean


def split_text(text: str, limit: int = MAX_TEXT_LENGTH) -> List[str]:
    """Divide um texto longo em partes de até `limit` caracteres.

    Corta de preferência numa quebra de parágrafo, depois numa quebra de
    linha, depois num espaço.
    """
    text = (text or "").strip()
    if not text:
        return []
    parts: List[str] = []
    while len(text) > limit:
        cut = text.rfind("\n\n", 0, limit)
        if cut <= 0:
            cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = text.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        parts.append(text)
    return parts


def build_whatsapp_system_block(assistant_name: str, data_subject: str) -> Dict[str, Any]:
    """Instruções do canal WhatsApp, somadas ao prompt do modelo."""
    return {
        "type": "text",
        "text": (
            "INSTRUÇÃO CRÍTICA - CANAL WHATSAPP\n\n"
            "Esta pergunta chegou pelo WhatsApp. A resposta vai ser lida no "
            "celular, numa conversa.\n\n"
            f"Você é o {assistant_name} e responde só sobre {data_subject}, "
            "com os dados do modelo semântico. Se a pergunta não for sobre "
            "esses dados, diga em uma frase que só responde sobre eles e dê "
            "um exemplo de pergunta que você responde.\n\n"
            "Continuidade: a conversa anterior está no histórico. Pergunta "
            "curta ou de seguimento (\"e no ano passado?\", \"quanto disso "
            "é de X?\", \"nisso\", \"sim\") se refere ao assunto, período "
            "e filtros da resposta anterior: mantenha esse contexto e consulte "
            "o modelo, sem pedir esclarecimento. A pergunta pode vir de um "
            "áudio transcrito, com palavras trocadas ou repetidas: leia pelo "
            "sentido e procure no modelo o nome mais parecido.\n\n"
            "Qualidade da análise:\n"
            "- Toda observação sai dos números consultados: variação contra "
            "outro período, peso no total, posição no ranking, concentração, "
            "ou o que mais puxou a subida ou a queda. Se precisar, faça mais "
            "uma consulta para ter essa comparação.\n"
            "- Proibido o óbvio e a especulação: nada de frase condicional "
            "que vale para qualquer métrica (\"se voltar a investir, a "
            "receita pode subir\", \"se não fizer nada, não vai crescer\"), "
            "nada de causa que os dados não mostram e nada de conselho "
            "genérico de negócio.\n"
            "- Sem observação concreta tirada dos dados, dê só o número e a "
            "comparação, sem enfeite.\n\n"
            "Formato:\n"
            "- Texto simples, curto: no máximo 6 linhas.\n"
            "- Comece pelo número ou pela resposta principal.\n"
            "- Para destacar, use *negrito* com um asterisco de cada lado.\n"
            "- Sem títulos, sem tabelas e sem blocos de código.\n"
            "- Lista só quando houver vários itens, com no máximo 5 itens, "
            "um por linha, começando com •.\n"
            "- Não gere visualizações nem o bloco [next_step_suggestions].\n"
            "- Termine, quando fizer sentido, com uma sugestão curta de "
            "pergunta seguinte."
        ),
    }


# ---------------------------------------------------------------------------
# Graph API: envio e mídia
# ---------------------------------------------------------------------------

def _auth_headers(config: WhatsAppConfig) -> Dict[str, str]:
    return {"Authorization": f"Bearer {config.token}"}


def send_text(
    config: WhatsAppConfig,
    to_phone: str,
    body: str,
    client: Optional[httpx.Client] = None,
) -> int:
    """Envia a resposta, em partes se passar do limite. Devolve quantas foram."""
    parts = split_text(body)
    owns_client = client is None
    http = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    sent = 0
    try:
        for part in parts:
            response = http.post(
                config.messages_url,
                headers=_auth_headers(config),
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": to_phone,
                    "type": "text",
                    "text": {"preview_url": False, "body": part},
                },
            )
            if response.status_code >= 400:
                print(
                    f"[whatsapp] envio falhou: status={response.status_code} "
                    f"corpo={response.text[:500]}"
                )
                break
            sent += 1
    finally:
        if owns_client:
            http.close()
    return sent


def download_media(
    config: WhatsAppConfig,
    media_id: str,
    client: Optional[httpx.Client] = None,
) -> Tuple[bytes, str]:
    """Baixa um arquivo recebido (áudio). Devolve (conteúdo, mime type)."""
    owns_client = client is None
    http = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    try:
        meta = http.get(config.media_url(media_id), headers=_auth_headers(config))
        meta.raise_for_status()
        info = meta.json()
        url = info.get("url")
        if not url:
            raise ValueError("A Meta não devolveu o endereço da mídia.")
        size = int(info.get("file_size") or 0)
        if size > MAX_AUDIO_BYTES:
            raise ValueError("Áudio grande demais.")
        content = http.get(url, headers=_auth_headers(config))
        content.raise_for_status()
        if len(content.content) > MAX_AUDIO_BYTES:
            raise ValueError("Áudio grande demais.")
        return content.content, str(info.get("mime_type") or "audio/ogg")
    finally:
        if owns_client:
            http.close()


def transcribe_audio(
    audio: bytes,
    mime_type: str,
    api_key: str,
    model: str,
    client: Optional[httpx.Client] = None,
) -> str:
    """Transcreve o áudio pela API de transcrição da OpenAI."""
    extension = "ogg"
    if "mpeg" in mime_type or "mp3" in mime_type:
        extension = "mp3"
    elif "mp4" in mime_type or "m4a" in mime_type or "aac" in mime_type:
        extension = "m4a"
    elif "amr" in mime_type:
        extension = "amr"
    owns_client = client is None
    http = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS * 2)
    try:
        response = http.post(
            OPENAI_TRANSCRIBE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            data={"model": model, "language": "pt"},
            files={"file": (f"audio.{extension}", audio, mime_type or "audio/ogg")},
        )
        response.raise_for_status()
        return str(response.json().get("text") or "").strip()
    finally:
        if owns_client:
            http.close()


def text_for_speech(text: str, limit: int = MAX_TTS_CHARS) -> str:
    """Limpa a resposta para ser falada: sem asteriscos, marcadores e quebras."""
    out = unwrap_answer(text)
    out = re.sub(r"[*_]{1,2}(.+?)[*_]{1,2}", r"\1", out)
    out = re.sub(r"^\s*[•\-]\s*", "", out, flags=re.MULTILINE)
    out = re.sub(r"#{1,6}\s*", "", out)
    out = re.sub(r"\s*\n+\s*", " ", out).strip()
    if len(out) > limit:
        cut = out.rfind(". ", 0, limit)
        out = out[: cut + 1] if cut > 0 else out[:limit]
    return out


def synthesize_speech_openai(
    text: str,
    api_key: str,
    voice: str = DEFAULT_OPENAI_TTS_VOICE,
    model: str = DEFAULT_OPENAI_TTS_MODEL,
    client: Optional[httpx.Client] = None,
) -> bytes:
    """Gera o áudio da resposta (MP3) pela OpenAI, com a chave da voz ao vivo."""
    owns_client = client is None
    http = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS * 2)
    try:
        response = http.post(
            OPENAI_TTS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "voice": voice,
                "input": text,
                "instructions": OPENAI_TTS_INSTRUCTIONS,
                "response_format": "mp3",
            },
        )
        response.raise_for_status()
        return response.content
    finally:
        if owns_client:
            http.close()


def _elevenlabs_payload(text: str, model_id: str) -> Dict[str, Any]:
    if model_id == FALLBACK_ELEVENLABS_TTS_MODEL:
        settings: Dict[str, Any] = {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        }
    else:
        settings = {"stability": 0.5, "similarity_boost": 0.75}
    return {"text": text, "model_id": model_id, "voice_settings": settings}


def synthesize_speech_elevenlabs(
    text: str,
    api_key: str,
    voice_id: str,
    model_id: str = DEFAULT_ELEVENLABS_TTS_MODEL,
    client: Optional[httpx.Client] = None,
) -> Tuple[bytes, str]:
    """Gera o áudio (MP3) pela ElevenLabs. Devolve (mp3, modelo usado).

    Se o modelo pedido falhar, tenta uma vez com eleven_multilingual_v2.
    """
    owns_client = client is None
    http = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS * 2)
    models = [model_id]
    if model_id != FALLBACK_ELEVENLABS_TTS_MODEL:
        models.append(FALLBACK_ELEVENLABS_TTS_MODEL)
    try:
        last_error: Optional[Exception] = None
        for model in models:
            try:
                response = http.post(
                    ELEVENLABS_TTS_URL.format(voice_id=voice_id),
                    headers={
                        "xi-api-key": api_key,
                        "Content-Type": "application/json",
                        "Accept": "audio/mpeg",
                    },
                    json=_elevenlabs_payload(text, model),
                )
                response.raise_for_status()
                return response.content, model
            except httpx.HTTPError as exc:
                print(f"[whatsapp] voz com {model} falhou: {exc}")
                last_error = exc
        assert last_error is not None
        raise last_error
    finally:
        if owns_client:
            http.close()


def to_ogg_opus(mp3: bytes) -> bytes:
    """Converte MP3 em OGG/Opus, o formato da mensagem de voz do WhatsApp.

    Sem a conversão, o WhatsApp mostra o áudio como arquivo de música e não
    como mensagem de voz. Usa o ffmpeg instalado na imagem (Dockerfile).
    """
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.mp3")
        dst = os.path.join(tmp, "out.ogg")
        with open(src, "wb") as handle:
            handle.write(mp3)
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-i", src,
             "-ac", "1", "-c:a", "libopus", "-b:a", "32k", dst],
            check=True,
            timeout=60,
        )
        with open(dst, "rb") as handle:
            return handle.read()


def upload_media(
    config: WhatsAppConfig,
    content: bytes,
    mime_type: str,
    filename: str,
    client: Optional[httpx.Client] = None,
) -> str:
    """Sobe um arquivo para a Meta e devolve o id da mídia."""
    owns_client = client is None
    http = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    try:
        response = http.post(
            config.upload_url,
            headers=_auth_headers(config),
            data={"messaging_product": "whatsapp", "type": mime_type},
            files={"file": (filename, content, mime_type)},
        )
        response.raise_for_status()
        media_id = str(response.json().get("id") or "")
        if not media_id:
            raise ValueError("A Meta não devolveu o id da mídia.")
        return media_id
    finally:
        if owns_client:
            http.close()


def send_audio(
    config: WhatsAppConfig,
    to_phone: str,
    media_id: str,
    client: Optional[httpx.Client] = None,
) -> bool:
    """Envia a mensagem de voz já carregada na Meta."""
    owns_client = client is None
    http = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    try:
        response = http.post(
            config.messages_url,
            headers=_auth_headers(config),
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to_phone,
                "type": "audio",
                "audio": {"id": media_id},
            },
        )
        if response.status_code >= 400:
            print(
                f"[whatsapp] envio do áudio falhou: status={response.status_code} "
                f"corpo={response.text[:500]}"
            )
            return False
        return True
    finally:
        if owns_client:
            http.close()


# ---------------------------------------------------------------------------
# Banco: mensagens já tratadas e usuário do número
# ---------------------------------------------------------------------------

def run_whatsapp_migrations() -> None:
    """Cria a tabela que evita responder duas vezes à mesma mensagem.

    A Meta reenvia o webhook quando não recebe 200 a tempo, então a mesma
    mensagem pode chegar mais de uma vez.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ai.whatsapp_inbound (
                message_id   TEXT PRIMARY KEY,
                from_phone   TEXT NOT NULL,
                received_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        conn.commit()
    finally:
        release_connection(conn)


def claim_message(message_id: str, from_phone: str) -> bool:
    """Marca a mensagem como tratada. False se ela já tinha chegado antes."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ai.whatsapp_inbound (message_id, from_phone)
            VALUES (%s, %s)
            ON CONFLICT (message_id) DO NOTHING
            """,
            (message_id, from_phone),
        )
        claimed = cursor.rowcount == 1
        conn.commit()
        return claimed
    finally:
        release_connection(conn)


def find_active_user(email: str) -> Optional[Dict[str, Any]]:
    """Usuário ativo, de cliente ativo, com esse e-mail. None se não houver."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT u.id, u.email, c.id
            FROM auth.users u
            JOIN auth.clients c ON c.id = u.client_id
            WHERE LOWER(u.email) = LOWER(%s)
              AND u.status = 'active'
              AND c.status = 'active'
            """,
            (email,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {"user_id": row[0], "email": row[1], "client_id": row[2]}
    finally:
        release_connection(conn)


def session_id_for(phone: str) -> str:
    """Uma conversa por número, separada das conversas do app."""
    return f"wa-{phone}"[:64]
