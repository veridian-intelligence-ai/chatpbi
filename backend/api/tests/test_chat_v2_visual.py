"""Observability test for the /chat/v2 visual gate.

Drives chat_v2() directly (bypassing the FastAPI dependency layer) with the
orchestrator and conversation_store mocked, and asserts the [visual] log line
that records whether a visual was built or — crucially — why it was skipped
(no rows / model omitted the hint / builder returned None).
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

from api.orchestrator import OrchestratorResult  # noqa: E402


def _drive_chat_v2(result: OrchestratorResult) -> str:
    """Run chat_v2() with everything mocked; return captured stdout."""
    orchestrator_mock = MagicMock()
    orchestrator_mock.run.return_value = result

    request = main_module.ChatRequest(session_id="s1", message="Top 10 marcas?")
    current_user = {"user_id": 1, "client_id": 1}

    store = main_module.conversation_store
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with patch.object(main_module, "check_rate_limit"), \
            patch.object(main_module, "emit_usage_event"), \
            patch.object(main_module, "_build_orchestrator", return_value=orchestrator_mock), \
            patch.object(store, "ensure_session"), \
            patch.object(store, "check_session_owner", return_value=True), \
            patch.object(store, "get_history", return_value=[]), \
            patch.object(store, "append_user_message"), \
            patch.object(store, "append_assistant_message"), \
            redirect_stdout(buf):
        main_module.chat_v2(request, current_user=current_user)
    return buf.getvalue()


def test_chat_v2_logs_visual_built_for_ranking() -> None:
    result = OrchestratorResult(
        answer="Top 5 marcas: ...",
        visual_hint={
            "chart_type": "bar",
            "x_field": "Parlamentar",
            "y_field": "Gasto",
            "title": "Top 5 marcas por receita",
            "value_format": "currency",
        },
        dax_rows=[
            {"Parlamentar": "Deputada A", "Gasto": 11827851.0},
            {"Parlamentar": "Deputado B", "Gasto": 7425525.0},
        ],
        dax_columns=["Parlamentar", "Gasto"],
    )
    out = _drive_chat_v2(result)
    assert "[visual] built type=chart/bar" in out
    assert "hint_chart=bar" in out


def test_chat_v2_logs_visual_skipped_when_model_omits_hint() -> None:
    # The Issue 4 symptom: rows exist, but the model emitted no visual_hint.
    result = OrchestratorResult(
        answer="Top 10 marcas: ...",
        visual_hint=None,
        dax_rows=[{"Parlamentar": "Deputada A", "Gasto": 11827851.0}],
        dax_columns=["Parlamentar", "Gasto"],
    )
    out = _drive_chat_v2(result)
    assert "[visual] skipped reason=no_visual_hint_from_model" in out
    # cols= must surface the real DAX column names for phase-2 diagnosis.
    assert "cols=['Parlamentar', 'Gasto']" in out


def test_chat_v2_logs_visual_skipped_when_builder_returns_none() -> None:
    # Hint present but unbuildable (x/y fields do not match the columns).
    result = OrchestratorResult(
        answer="...",
        visual_hint={"chart_type": "bar", "x_field": "x", "y_field": "y"},
        dax_rows=[{"foo": "a"}, {"foo": "b"}],
        dax_columns=["foo"],
    )
    out = _drive_chat_v2(result)
    assert "[visual] skipped reason=builder_returned_none" in out
    assert "hint_chart=bar" in out
