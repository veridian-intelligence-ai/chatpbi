"""Voz ao vivo (OpenAI Realtime): chave efémera e endpoints /voice/*.

Sem rede: a OpenAI é simulada com pytest-httpx e os endpoints são chamados
directamente, com o rate limit e a instrumentação substituídos.
"""

import json
import os
import sys
from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException
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

from api import realtime_voice  # noqa: E402

_USER = {"user_id": 1, "client_id": 7, "email": "teste@example.com"}
_FAKE_KEY = "sk-teste-nao-real"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_REALTIME_MODEL",
        "OPENAI_REALTIME_VOICE",
        "OPENAI_TRANSCRIBE_MODEL",
        "ELEVENLABS_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


# ─────────────────────────────────────────────
# Configuração da sessão
# ─────────────────────────────────────────────

def test_session_request_has_model_voice_and_data_tool():
    body = realtime_voice.build_client_secret_request()
    session = body["session"]
    assert session["type"] == "realtime"
    assert session["model"] == "gpt-realtime"
    assert session["audio"]["output"]["voice"] == "marin"
    assert session["audio"]["input"]["transcription"]["model"] == "gpt-4o-mini-transcribe"
    assert session["tool_choice"] == "auto"
    [tool] = session["tools"]
    assert tool["type"] == "function"
    assert tool["name"] == "consultar_dados"
    assert tool["parameters"]["required"] == ["pergunta"]


def test_session_request_follows_env_overrides(monkeypatch):
    monkeypatch.setenv("OPENAI_REALTIME_MODEL", "gpt-realtime-mini")
    monkeypatch.setenv("OPENAI_REALTIME_VOICE", "cedar")
    monkeypatch.setenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
    session = realtime_voice.build_client_secret_request()["session"]
    assert session["model"] == "gpt-realtime-mini"
    assert session["audio"]["output"]["voice"] == "cedar"
    assert session["audio"]["input"]["transcription"]["model"] == "gpt-4o-transcribe"


def test_instructions_keep_numbers_in_the_tool():
    text = realtime_voice.build_realtime_instructions()
    assert "Cota parlamentar" in text
    assert "consultar_dados" in text
    assert "Nunca invente" in text
    assert "Power BI" in text


# ─────────────────────────────────────────────
# create_client_secret
# ─────────────────────────────────────────────

def test_create_client_secret_returns_value(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=realtime_voice.CLIENT_SECRETS_URL,
        method="POST",
        json={"value": "ek_teste", "expires_at": 1760000000, "session": {}},
    )
    secret = realtime_voice.create_client_secret(_FAKE_KEY)
    assert secret.value == "ek_teste"
    assert secret.expires_at == 1760000000
    assert secret.model == "gpt-realtime"

    [request] = httpx_mock.get_requests()
    assert request.headers["Authorization"] == f"Bearer {_FAKE_KEY}"
    sent = json.loads(request.content)
    assert sent["session"]["tools"][0]["name"] == "consultar_dados"


def test_create_client_secret_accepts_legacy_shape(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=realtime_voice.CLIENT_SECRETS_URL,
        method="POST",
        json={"client_secret": {"value": "ek_antigo", "expires_at": 123}},
    )
    secret = realtime_voice.create_client_secret(_FAKE_KEY)
    assert secret.value == "ek_antigo"
    assert secret.expires_at == 123


def test_create_client_secret_error_has_message_without_key(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=realtime_voice.CLIENT_SECRETS_URL,
        method="POST",
        status_code=400,
        json={"error": {"message": "Unknown parameter: 'session.foo'."}},
    )
    with pytest.raises(realtime_voice.RealtimeError) as excinfo:
        realtime_voice.create_client_secret(_FAKE_KEY)
    message = str(excinfo.value)
    assert "400" in message
    assert "Unknown parameter" in message
    assert _FAKE_KEY not in message


def test_create_client_secret_network_error(httpx_mock: HTTPXMock):
    httpx_mock.add_exception(httpx.ConnectTimeout("timeout"))
    with pytest.raises(realtime_voice.RealtimeError):
        realtime_voice.create_client_secret(_FAKE_KEY)


def test_create_client_secret_without_value_fails(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=realtime_voice.CLIENT_SECRETS_URL, method="POST", json={"session": {}}
    )
    with pytest.raises(realtime_voice.RealtimeError):
        realtime_voice.create_client_secret(_FAKE_KEY)


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

def test_voice_config_reports_available_voices(monkeypatch):
    assert main_module.voice_config(current_user=_USER) == {
        "status": "success",
        "realtime": False,
        "classic": False,
    }
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE_KEY)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "xi-teste")
    config = main_module.voice_config(current_user=_USER)
    assert config["realtime"] is True
    assert config["classic"] is True


def test_realtime_session_without_key_returns_503():
    with patch.object(main_module, "check_rate_limit") as rate_limit:
        with pytest.raises(HTTPException) as excinfo:
            main_module.realtime_session(current_user=_USER)
    assert excinfo.value.status_code == 503
    rate_limit.assert_not_called()


def test_realtime_session_returns_client_secret(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE_KEY)
    secret = realtime_voice.RealtimeSecret(
        value="ek_teste", expires_at=1760000000, model="gpt-realtime"
    )
    with patch.object(main_module, "check_rate_limit") as rate_limit, \
            patch.object(main_module, "create_client_secret", return_value=secret) as create, \
            patch.object(main_module, "emit_usage_event") as emit:
        payload = main_module.realtime_session(current_user=_USER)

    rate_limit.assert_called_once_with(1, "/voice/realtime/session")
    create.assert_called_once_with(_FAKE_KEY)
    assert payload == {
        "status": "success",
        "client_secret": "ek_teste",
        "expires_at": 1760000000,
        "model": "gpt-realtime",
    }
    assert emit.call_args.kwargs["provider"] == "openai"
    assert emit.call_args.kwargs["endpoint"] == "/voice/realtime/session"


def test_realtime_session_openai_error_returns_502(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE_KEY)
    with patch.object(main_module, "check_rate_limit"), \
            patch.object(
                main_module,
                "create_client_secret",
                side_effect=realtime_voice.RealtimeError("OpenAI respondeu 401: bad key"),
            ), \
            patch.object(main_module, "emit_usage_event") as emit:
        with pytest.raises(HTTPException) as excinfo:
            main_module.realtime_session(current_user=_USER)

    assert excinfo.value.status_code == 502
    emit.assert_not_called()
    assert "OpenAI respondeu 401" in capsys.readouterr().out


# ─────────────────────────────────────────────
# /model
# ─────────────────────────────────────────────

def test_model_info_returns_active_model():
    info = main_module.model_info(current_user=_USER)
    assert info["status"] == "success"
    assert info["name"] == "Cota parlamentar"
    assert info["currency"] == "BRL"
    assert info["source"] == "Power BI"
    assert info["subject"]
