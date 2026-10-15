"""Timing-summary log test for the /chat/v2 endpoint.

Drives chat_v2() directly (bypassing the FastAPI dependency layer) with the
orchestrator and conversation_store mocked, and asserts the [timing] line that
breaks the request wall-clock into Anthropic / Fabric / other slices.
"""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Env vars required for `main` to import successfully (CORS + Fabric fail-fast).
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("FABRIC_DEFAULT_DATASET_ID", "test-dataset")
os.environ.setdefault("FABRIC_TENANT_ID", "test-tenant")
os.environ.setdefault("FABRIC_CLIENT_ID", "test-client")
os.environ.setdefault("FABRIC_CLIENT_SECRET", "test-secret")
os.environ.setdefault("FABRIC_WORKSPACE_ID", "test-workspace")

# `main` calls run_migrations() at import time, which would hit Postgres.
with patch("conversation_store.run_migrations"):
    import main as main_module  # noqa: E402

from api.orchestrator import IterationLog, OrchestratorResult  # noqa: E402


def test_chat_v2_logs_timing_summary(capsys) -> None:
    # Two anthropic iterations (59242ms total) and one fabric query (957ms).
    result = OrchestratorResult(
        answer="resposta",
        total_latency_ms=59242,
        iterations=[
            IterationLog(
                iteration=1, latency_ms=50000, stop_reason="tool_use",
                input_tokens=200, output_tokens=150,
                cache_write_tokens=34500, cache_read_tokens=0,
                dax_latency_ms=957, dax_call_count=1,
            ),
            IterationLog(
                iteration=2, latency_ms=9242, stop_reason="end_turn",
                input_tokens=250, output_tokens=30,
                cache_write_tokens=0, cache_read_tokens=34500,
            ),
        ],
    )

    orchestrator_mock = MagicMock()
    orchestrator_mock.run.return_value = result

    request = main_module.ChatRequest(session_id="s1", message="Quanto foi gasto?")
    current_user = {"user_id": 1, "client_id": 1}

    store = main_module.conversation_store
    with patch.object(main_module, "check_rate_limit"), \
            patch.object(main_module, "emit_usage_event"), \
            patch.object(main_module, "_build_orchestrator", return_value=orchestrator_mock), \
            patch.object(store, "ensure_session"), \
            patch.object(store, "check_session_owner", return_value=True), \
            patch.object(store, "get_history", return_value=[]), \
            patch.object(store, "append_user_message"), \
            patch.object(store, "append_assistant_message"):
        main_module.chat_v2(request, current_user=current_user)

    out = capsys.readouterr().out
    assert "[timing] /chat/v2 total=" in out
    assert "anthropic=59242ms (2 iterations)" in out
    assert "fabric=957ms (1 query)" in out
    assert "other=" in out
