"""Testes do canal do WhatsApp (api/whatsapp.py e as rotas em main.py).

Não chamam a Meta, o Claude, a OpenAI nem o Power BI de verdade: o HTTP é
simulado com pytest-httpx e o orquestrador e o banco são substituídos.
"""

import hashlib
import hmac
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from pytest_httpx import HTTPXMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("FABRIC_DEFAULT_DATASET_ID", "test-dataset")
os.environ.setdefault("FABRIC_TENANT_ID", "test-tenant")
os.environ.setdefault("FABRIC_CLIENT_ID", "test-client")
os.environ.setdefault("FABRIC_CLIENT_SECRET", "test-secret")
os.environ.setdefault("FABRIC_WORKSPACE_ID", "test-workspace")

with patch("conversation_store.run_migrations"):
    import main as main_module  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from api import whatsapp as wa  # noqa: E402
from api.orchestrator import OrchestratorResult  # noqa: E402

CONFIG = wa.WhatsAppConfig(
    token="token-falso",
    phone_number_id="1234567890",
    verify_token="verifica-123",
    app_secret="segredo-do-app",
    graph_version="v25.0",
)
PHONE = "351912345678"


def _signed(body: bytes, secret: str = CONFIG.app_secret) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _text_payload(text: str, message_id: str = "wamid.1", phone: str = PHONE) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "from": phone,
                                    "id": message_id,
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ]
            }
        ],
    }


# ---------------------------------------------------------------------------
# Configuração e números
# ---------------------------------------------------------------------------

def test_config_desligada_sem_variaveis(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "WHATSAPP_TOKEN",
        "WHATSAPP_PHONE_NUMBER_ID",
        "WHATSAPP_VERIFY_TOKEN",
        "WHATSAPP_APP_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    assert wa.WhatsAppConfig.from_env() is None


def test_config_exige_o_segredo_do_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHATSAPP_TOKEN", "t")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "1")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "v")
    monkeypatch.delenv("WHATSAPP_APP_SECRET", raising=False)
    assert wa.WhatsAppConfig.from_env() is None
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "s")
    config = wa.WhatsAppConfig.from_env()
    assert config is not None
    assert config.messages_url == "https://graph.facebook.com/v25.0/1/messages"


def test_parse_allowed_numbers() -> None:
    allowed = wa.parse_allowed_numbers(
        "+351 912 345 678=Ana@Empresa.com, 5511987654321 = joao@empresa.com, ruim, =x@y.com"
    )
    assert allowed == {
        "351912345678": "ana@empresa.com",
        "5511987654321": "joao@empresa.com",
    }
    assert wa.parse_allowed_numbers(None) == {}


# ---------------------------------------------------------------------------
# Webhook: assinatura e payload
# ---------------------------------------------------------------------------

def test_verify_signature() -> None:
    body = b'{"a": 1}'
    assert wa.verify_signature(CONFIG.app_secret, body, _signed(body))
    assert not wa.verify_signature(CONFIG.app_secret, body, _signed(body, "outro"))
    assert not wa.verify_signature(CONFIG.app_secret, body, None)
    assert not wa.verify_signature(CONFIG.app_secret, body, "md5=abc")


def test_parse_inbound_texto_audio_e_status() -> None:
    payload = _text_payload("  Quanto gastamos em 2025?  ")
    value = payload["entry"][0]["changes"][0]["value"]
    value["messages"].append(
        {
            "from": PHONE,
            "id": "wamid.2",
            "type": "audio",
            "audio": {"id": "media-1", "mime_type": "audio/ogg; codecs=opus"},
        }
    )
    value["messages"].append({"from": PHONE, "id": "wamid.3", "type": "image", "image": {}})
    value["statuses"] = [{"id": "wamid.0", "status": "read"}]

    messages = wa.parse_inbound(payload)
    assert [m.type for m in messages] == ["text", "audio", "image"]
    assert messages[0].text == "Quanto gastamos em 2025?"
    assert messages[1].media_id == "media-1"
    assert wa.parse_inbound({"object": "page"}) == []


def test_formato_whatsapp_e_divisao() -> None:
    texto = "## Resumo\n\n**R$ 1,2 milhão** em 2025\n\n| a | b |\n|---|---|\n| 1 | 2 |"
    out = wa.to_whatsapp_format(texto)
    assert "##" not in out and "**" not in out and "---" not in out
    assert "*R$ 1,2 milhão*" in out

    partes = wa.split_text("palavra " * 1500, limit=1000)
    assert len(partes) > 1
    assert all(len(p) <= 1000 for p in partes)
    assert wa.split_text("   ") == []


def test_comando_novo() -> None:
    assert wa.is_reset_command(" Novo ")
    assert not wa.is_reset_command("novo relatório de gastos")


# ---------------------------------------------------------------------------
# Graph API
# ---------------------------------------------------------------------------

def test_send_text_envia_para_a_graph_api(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=CONFIG.messages_url, json={"messages": [{"id": "x"}]})
    assert wa.send_text(CONFIG, PHONE, "Olá") == 1
    [request] = httpx_mock.get_requests()
    assert request.headers["Authorization"] == "Bearer token-falso"
    body = json.loads(request.content)
    assert body["to"] == PHONE
    assert body["type"] == "text"
    assert body["text"]["body"] == "Olá"


def test_send_text_para_na_primeira_falha(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=CONFIG.messages_url, status_code=400, json={"error": {}})
    assert wa.send_text(CONFIG, PHONE, ("x " * 3000).strip()) == 0
    assert len(httpx_mock.get_requests()) == 1


def test_download_media_e_transcricao(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=CONFIG.media_url("media-1"),
        json={"url": "https://lookaside.example/media-1", "mime_type": "audio/ogg", "file_size": 10},
    )
    httpx_mock.add_response(url="https://lookaside.example/media-1", content=b"OggS-audio")
    httpx_mock.add_response(url=wa.OPENAI_TRANSCRIBE_URL, json={"text": " Quanto gastamos? "})

    audio, mime = wa.download_media(CONFIG, "media-1")
    assert audio == b"OggS-audio" and mime == "audio/ogg"
    assert wa.transcribe_audio(audio, mime, "sk-falsa", "gpt-4o-mini-transcribe") == "Quanto gastamos?"


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

@pytest.fixture
def client_ligado():
    with patch.object(main_module, "WHATSAPP_CONFIG", CONFIG):
        yield TestClient(main_module.app)


def test_rotas_desligadas_sem_config() -> None:
    with patch.object(main_module, "WHATSAPP_CONFIG", None):
        client = TestClient(main_module.app)
        assert client.get("/whatsapp/webhook").status_code == 404
        assert client.post("/whatsapp/webhook", content=b"{}").status_code == 404


def test_verificacao_do_webhook(client_ligado: TestClient) -> None:
    ok = client_ligado.get(
        "/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "verifica-123", "hub.challenge": "42"},
    )
    assert ok.status_code == 200 and ok.text == "42"
    ruim = client_ligado.get(
        "/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "errado", "hub.challenge": "42"},
    )
    assert ruim.status_code == 403


def test_webhook_recusa_assinatura_invalida(client_ligado: TestClient) -> None:
    body = json.dumps(_text_payload("oi")).encode()
    response = client_ligado.post(
        "/whatsapp/webhook", content=body, headers={"X-Hub-Signature-256": _signed(body, "outro")}
    )
    assert response.status_code == 401


def test_webhook_agenda_cada_mensagem(client_ligado: TestClient) -> None:
    body = json.dumps(_text_payload("Quanto gastamos?")).encode()
    with patch.object(main_module, "handle_whatsapp_message") as handler:
        response = client_ligado.post(
            "/whatsapp/webhook", content=body, headers={"X-Hub-Signature-256": _signed(body)}
        )
    assert response.status_code == 200
    [call] = handler.call_args_list
    assert call.args[0].text == "Quanto gastamos?"


# ---------------------------------------------------------------------------
# Tratamento de uma mensagem
# ---------------------------------------------------------------------------

USER = {"user_id": 7, "email": "ana@empresa.com", "client_id": 3}


def _message(text: str = "Quanto gastamos em 2025?") -> wa.InboundMessage:
    return wa.InboundMessage("wamid.9", PHONE, "text", text=text)


@pytest.fixture
def ambiente(monkeypatch: pytest.MonkeyPatch):
    """Canal ligado, número autorizado, banco e envio substituídos."""
    monkeypatch.setenv("WHATSAPP_ALLOWED_NUMBERS", f"{PHONE}=ana@empresa.com")
    store = main_module.conversation_store
    orchestrator = MagicMock()
    orchestrator.run.return_value = OrchestratorResult(answer="**R$ 10 mil** em 2025.")
    with patch.object(main_module, "WHATSAPP_CONFIG", CONFIG), \
            patch.object(main_module, "claim_message", return_value=True) as claim, \
            patch.object(main_module, "find_active_user", return_value=USER), \
            patch.object(main_module, "check_rate_limit") as rate_limit, \
            patch.object(main_module, "emit_usage_event"), \
            patch.object(main_module, "send_text") as send, \
            patch.object(main_module, "_build_whatsapp_orchestrator", return_value=orchestrator), \
            patch.object(store, "ensure_session"), \
            patch.object(store, "check_session_owner", return_value=True), \
            patch.object(store, "get_history", return_value=[]), \
            patch.object(store, "append_user_message"), \
            patch.object(store, "append_assistant_message"), \
            patch.object(store, "clear") as clear:
        yield {
            "send": send,
            "orchestrator": orchestrator,
            "claim": claim,
            "rate_limit": rate_limit,
            "clear": clear,
        }


def test_responde_numero_autorizado(ambiente) -> None:
    main_module.handle_whatsapp_message(_message())
    ambiente["orchestrator"].run.assert_called_once()
    kwargs = ambiente["orchestrator"].run.call_args.kwargs
    assert kwargs["user_message"] == "Quanto gastamos em 2025?"
    assert "CANAL WHATSAPP" in kwargs["extra_system_blocks"][0]["text"]
    ambiente["send"].assert_called_once_with(CONFIG, PHONE, "*R$ 10 mil* em 2025.")


def test_ignora_numero_fora_da_lista(ambiente, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHATSAPP_ALLOWED_NUMBERS", "5511999999999=outro@empresa.com")
    main_module.handle_whatsapp_message(_message())
    ambiente["claim"].assert_not_called()
    ambiente["orchestrator"].run.assert_not_called()
    ambiente["send"].assert_not_called()


def test_ignora_mensagem_repetida(ambiente) -> None:
    ambiente["claim"].return_value = False
    main_module.handle_whatsapp_message(_message())
    ambiente["orchestrator"].run.assert_not_called()
    ambiente["send"].assert_not_called()


def test_avisa_quando_passa_do_limite(ambiente) -> None:
    ambiente["rate_limit"].side_effect = main_module.HTTPException(status_code=429)
    main_module.handle_whatsapp_message(_message())
    ambiente["orchestrator"].run.assert_not_called()
    ambiente["send"].assert_called_once_with(CONFIG, PHONE, main_module.WHATSAPP_TEXTS["limite"])


def test_comando_novo_limpa_a_conversa(ambiente) -> None:
    main_module.handle_whatsapp_message(_message("novo"))
    ambiente["clear"].assert_called_once()
    ambiente["orchestrator"].run.assert_not_called()
    ambiente["send"].assert_called_once_with(CONFIG, PHONE, main_module.WHATSAPP_TEXTS["novo"])


def test_audio_sem_chave_da_openai(ambiente, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    audio = wa.InboundMessage("wamid.10", PHONE, "audio", media_id="media-1")
    main_module.handle_whatsapp_message(audio)
    ambiente["orchestrator"].run.assert_not_called()
    ambiente["send"].assert_called_once_with(CONFIG, PHONE, main_module.WHATSAPP_TEXTS["audio_off"])


def test_audio_transcrito_vira_pergunta(ambiente, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-falsa")
    audio = wa.InboundMessage("wamid.11", PHONE, "audio", media_id="media-1")
    with patch.object(main_module, "download_media", return_value=(b"x", "audio/ogg")), \
            patch.object(main_module, "transcribe_audio", return_value="Quanto gastamos?"), \
            patch.object(main_module, "_reply_with_audio", return_value=None):
        main_module.handle_whatsapp_message(audio)
    assert ambiente["orchestrator"].run.call_args.kwargs["user_message"] == "Quanto gastamos?"


def test_erro_vira_mensagem_curta(ambiente) -> None:
    ambiente["orchestrator"].run.side_effect = RuntimeError("Power BI fora do ar")
    main_module.handle_whatsapp_message(_message())
    ambiente["send"].assert_called_once_with(CONFIG, PHONE, main_module.WHATSAPP_TEXTS["erro"])


# ---------------------------------------------------------------------------
# Histórico e resposta em JSON
# ---------------------------------------------------------------------------

def test_unwrap_answer_abre_json_aninhado() -> None:
    interno = json.dumps({"message_type": "whatsapp_response", "answer": "Linha 1\nLinha 2"})
    externo = json.dumps({"message_type": "whatsapp_response", "answer": interno})
    assert wa.unwrap_answer(externo) == "Linha 1\nLinha 2"
    assert wa.unwrap_answer("Texto normal") == "Texto normal"
    assert wa.unwrap_answer('{"outra": "coisa"}') == '{"outra": "coisa"}'
    assert wa.unwrap_answer("{não é json}") == "{não é json}"


def test_history_for_model_tira_o_json_das_respostas() -> None:
    historico = [
        {"role": "user", "content": "Olá"},
        {"role": "assistant", "content": json.dumps({"message_type": "x", "answer": "Oi!"})},
        {"role": "assistant", "content": ""},
        {"role": "system", "content": "ignorar"},
    ]
    assert wa.history_for_model(historico) == [
        {"role": "user", "content": "Olá"},
        {"role": "assistant", "content": "Oi!"},
    ]


def test_handler_usa_historico_limpo_e_abre_resposta_em_json(ambiente) -> None:
    salvo = json.dumps({"message_type": "whatsapp_response", "answer": "Resposta antiga"})
    ambiente["orchestrator"].run.return_value = OrchestratorResult(
        answer=json.dumps({"message_type": "whatsapp_response", "answer": "**R$ 5 mil**"})
    )
    with patch.object(
        main_module.conversation_store,
        "get_history",
        return_value=[{"role": "user", "content": "oi"}, {"role": "assistant", "content": salvo}],
    ):
        main_module.handle_whatsapp_message(_message())
    historico = ambiente["orchestrator"].run.call_args.kwargs["conversation_history"]
    assert historico[-1] == {"role": "assistant", "content": "Resposta antiga"}
    ambiente["send"].assert_called_once_with(CONFIG, PHONE, "*R$ 5 mil*")


# ---------------------------------------------------------------------------
# Resposta em áudio
# ---------------------------------------------------------------------------

def _audio_message(message_id: str = "wamid.20") -> "wa.InboundMessage":
    return wa.InboundMessage(message_id, PHONE, "audio", media_id="media-1")


def test_pergunta_em_audio_recebe_audio_pela_openai(ambiente, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-falsa")
    with patch.object(main_module, "download_media", return_value=(b"x", "audio/ogg")), \
            patch.object(main_module, "transcribe_audio", return_value="E no ano passado?"), \
            patch.object(main_module, "synthesize_speech_openai", return_value=b"mp3") as tts, \
            patch.object(main_module, "to_ogg_opus", return_value=b"ogg"), \
            patch.object(main_module, "upload_media", return_value="media-9") as upload, \
            patch.object(main_module, "send_audio", return_value=True) as send_audio:
        main_module.handle_whatsapp_message(_audio_message())
    tts.assert_called_once()
    assert tts.call_args.args[2] == wa.DEFAULT_OPENAI_TTS_VOICE
    upload.assert_called_once_with(CONFIG, b"ogg", "audio/ogg", "resposta.ogg")
    send_audio.assert_called_once_with(CONFIG, PHONE, "media-9")
    ambiente["send"].assert_not_called()
    blocos = ambiente["orchestrator"].run.call_args.kwargs["extra_system_blocks"]
    assert len(blocos) == 2


def test_audio_cai_para_texto_quando_a_voz_falha(ambiente, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-falsa")
    with patch.object(main_module, "download_media", return_value=(b"x", "audio/ogg")), \
            patch.object(main_module, "transcribe_audio", return_value="E no ano passado?"), \
            patch.object(main_module, "synthesize_speech_openai", side_effect=RuntimeError("sem crédito")):
        main_module.handle_whatsapp_message(_audio_message("wamid.21"))
    ambiente["send"].assert_called_once_with(CONFIG, PHONE, "*R$ 10 mil* em 2025.")


def test_audio_pela_elevenlabs(ambiente, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-falsa")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "chave-falsa")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voz-falsa")
    with patch.object(main_module, "WHATSAPP_TTS_PROVIDER", "elevenlabs"), \
            patch.object(main_module, "download_media", return_value=(b"x", "audio/ogg")), \
            patch.object(main_module, "transcribe_audio", return_value="E no ano passado?"), \
            patch.object(main_module, "synthesize_speech_elevenlabs", return_value=(b"mp3", "eleven_v4")) as tts, \
            patch.object(main_module, "to_ogg_opus", return_value=b"ogg"), \
            patch.object(main_module, "upload_media", return_value="media-9"), \
            patch.object(main_module, "send_audio", return_value=True):
        main_module.handle_whatsapp_message(_audio_message("wamid.22"))
    assert tts.call_args.args[2] == "voz-falsa"
    ambiente["send"].assert_not_called()


def test_pergunta_em_texto_nao_vira_audio(ambiente) -> None:
    with patch.object(main_module, "_reply_with_audio") as reply:
        main_module.handle_whatsapp_message(_message())
    reply.assert_not_called()
    assert len(ambiente["orchestrator"].run.call_args.kwargs["extra_system_blocks"]) == 1


def test_tts_openai_pede_mp3_com_a_voz(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=wa.OPENAI_TTS_URL, content=b"mp3")
    assert wa.synthesize_speech_openai("Olá", "sk-falsa", "coral") == b"mp3"
    body = json.loads(httpx_mock.get_requests()[0].content)
    assert body["model"] == "gpt-4o-mini-tts"
    assert body["voice"] == "coral"
    assert body["response_format"] == "mp3"


def test_tts_elevenlabs_cai_para_multilingual(httpx_mock: HTTPXMock) -> None:
    url = wa.ELEVENLABS_TTS_URL.format(voice_id="voz")
    httpx_mock.add_response(url=url, status_code=400)
    httpx_mock.add_response(url=url, content=b"mp3-v2")
    mp3, modelo = wa.synthesize_speech_elevenlabs("Olá", "chave", "voz")
    assert (mp3, modelo) == (b"mp3-v2", "eleven_multilingual_v2")


def test_upload_e_envio_do_audio(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=CONFIG.upload_url, json={"id": "media-9"})
    httpx_mock.add_response(url=CONFIG.messages_url, json={"messages": [{"id": "x"}]})
    media_id = wa.upload_media(CONFIG, b"ogg", "audio/ogg", "resposta.ogg")
    assert media_id == "media-9"
    assert wa.send_audio(CONFIG, PHONE, media_id)
    body = json.loads(httpx_mock.get_requests()[-1].content)
    assert body["type"] == "audio" and body["audio"] == {"id": "media-9"}


def test_text_for_speech_limpa_a_marcacao() -> None:
    assert wa.text_for_speech("*R$ 10 mil* em 2025.\n• Saúde: *R$ 2 mil*") == (
        "R$ 10 mil em 2025. Saúde: R$ 2 mil"
    )


def test_bloco_pede_continuidade_e_analise_dos_dados() -> None:
    texto = wa.build_whatsapp_system_block("ChatPBI", "os dados")["text"]
    assert "Continuidade" in texto
    assert "Proibido o óbvio e a especulação" in texto
