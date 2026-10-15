"""Voz ao vivo com a OpenAI Realtime API (WebRTC no browser).

O backend nunca entrega a OPENAI_API_KEY ao browser: pede à OpenAI uma chave
efémera (client secret) já com a sessão configurada — modelo, voz, instruções
e a ferramenta `consultar_dados` — e devolve só essa chave, que expira em
poucos minutos. O browser liga-se por WebRTC a /v1/realtime/calls com ela.

Os números nunca saem do modelo de voz: quando a pessoa pergunta sobre os
dados, o modelo chama `consultar_dados`; o frontend passa a pergunta ao
/chat/voice (Claude + DAX no modelo semântico) e devolve a resposta como
resultado da ferramenta, que o modelo de voz lê em voz alta.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from api.semantic_models import get_active_model

_MODEL = get_active_model()

# Mesmo nome do chat (api/prompts_fabric.py): variável ASSISTANT_NAME.
ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "").strip() or "ChatPBI"

CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"
REALTIME_TOOL_NAME = "consultar_dados"

DEFAULT_REALTIME_MODEL = "gpt-realtime"
DEFAULT_REALTIME_VOICE = "marin"
DEFAULT_TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"


class RealtimeError(Exception):
    """Falha ao criar a sessão na OpenAI (sem segredos na mensagem)."""


@dataclass(frozen=True)
class RealtimeSecret:
    value: str
    expires_at: Optional[int]
    model: str


def realtime_api_key() -> str:
    return os.getenv("OPENAI_API_KEY", "").strip()


def realtime_available() -> bool:
    return bool(realtime_api_key())


def realtime_model() -> str:
    return os.getenv("OPENAI_REALTIME_MODEL", "").strip() or DEFAULT_REALTIME_MODEL


def realtime_voice() -> str:
    return os.getenv("OPENAI_REALTIME_VOICE", "").strip() or DEFAULT_REALTIME_VOICE


def transcribe_model() -> str:
    return os.getenv("OPENAI_TRANSCRIBE_MODEL", "").strip() or DEFAULT_TRANSCRIBE_MODEL


def build_realtime_instructions() -> str:
    """Instruções do modelo de voz: conversa natural, números só da ferramenta."""
    return (
        f"Você é o {ASSISTANT_NAME}, o assistente de voz de um app que conversa com os "
        f"dados do modelo semântico {_MODEL.MODEL_NAME} do Power BI "
        f"({_MODEL.DATA_SUBJECT}).\n\n"
        "Como conversar:\n"
        f"- Fale em {_MODEL.DEFAULT_LANGUAGE}, com calma e naturalidade, em "
        "frases curtas. Se a pessoa falar em inglês, responda em inglês.\n"
        "- Toda pergunta sobre os dados (valores, totais, rankings, "
        "comparações, evolução, quem, quanto, quando) passa pela ferramenta "
        f"{REALTIME_TOOL_NAME}. Chame a ferramenta antes de dizer qualquer "
        "número.\n"
        f"- Mande para {REALTIME_TOOL_NAME} a pergunta completa, em "
        "português, com o contexto da conversa. Se a pessoa disser \"e no ano "
        "anterior?\", mande a pergunta inteira com o assunto e o ano, não só "
        "o pedaço que ela falou.\n"
        "- Enquanto a ferramenta trabalha, diga só uma frase curta, como "
        "\"Deixa eu ver\" ou \"Um instante\".\n"
        "- Quando a ferramenta responder, fale a resposta dela com "
        "naturalidade. Pode encurtar, mas não mude os números e não "
        "acrescente número, porcentagem, data, nome ou conclusão que não "
        "estejam na resposta da ferramenta.\n"
        f"- Os valores em dinheiro estão em {_MODEL.CURRENCY_LABEL}.\n"
        "- Se a ferramenta devolver erro, diga que não conseguiu consultar "
        "os dados agora e peça para a pessoa tentar de novo.\n"
        "- Se a pergunta não for sobre os dados, responda em uma ou duas "
        f"frases e lembre que você responde sobre {_MODEL.DATA_SUBJECT}.\n"
        "- Nunca invente números, nomes ou datas."
    )


def build_realtime_tool() -> Dict[str, Any]:
    return {
        "type": "function",
        "name": REALTIME_TOOL_NAME,
        "description": (
            f"Consulta o modelo semântico {_MODEL.MODEL_NAME} do Power BI e "
            "devolve a resposta em texto, com os números da consulta. Use "
            "para toda pergunta sobre os dados."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pergunta": {
                    "type": "string",
                    "description": (
                        "A pergunta completa, em português, com o contexto da "
                        "conversa (assunto, período, filtros e nomes)."
                    ),
                },
            },
            "required": ["pergunta"],
        },
    }


def build_client_secret_request() -> Dict[str, Any]:
    """Corpo do POST /v1/realtime/client_secrets (sessão já configurada)."""
    return {
        "session": {
            "type": "realtime",
            "model": realtime_model(),
            "instructions": build_realtime_instructions(),
            "audio": {
                "input": {
                    "transcription": {"model": transcribe_model(), "language": "pt"},
                    "turn_detection": {"type": "semantic_vad"},
                },
                "output": {"voice": realtime_voice()},
            },
            "tools": [build_realtime_tool()],
            "tool_choice": "auto",
        },
    }


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:300]
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or error)[:300]
    return str(payload)[:300]


def create_client_secret(
    api_key: str,
    *,
    timeout: float = 15.0,
    client: Optional[httpx.Client] = None,
) -> RealtimeSecret:
    """Cria a chave efémera da sessão. Levanta RealtimeError se falhar."""
    body = build_client_secret_request()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout)
    try:
        response = http.post(CLIENT_SECRETS_URL, headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise RealtimeError(f"falha de rede: {type(exc).__name__}") from exc
    finally:
        if owns_client:
            http.close()

    if response.status_code != 200:
        raise RealtimeError(
            f"OpenAI respondeu {response.status_code}: {_error_detail(response)}"
        )

    data = response.json()
    value = data.get("value") if isinstance(data, dict) else None
    if not value and isinstance(data, dict):
        # Formato antigo (beta): {"client_secret": {"value", "expires_at"}}.
        legacy = data.get("client_secret")
        if isinstance(legacy, dict):
            value = legacy.get("value")
            data = {**data, "expires_at": legacy.get("expires_at")}
    if not value:
        raise RealtimeError("resposta da OpenAI sem a chave da sessão")

    expires_at = data.get("expires_at")
    return RealtimeSecret(
        value=str(value),
        expires_at=int(expires_at) if isinstance(expires_at, (int, float)) else None,
        model=realtime_model(),
    )
