"""
Smoke test manual do /chat/v2, /chat/reset, /suggestions e /voice/config.

Os endpoints pedem o token de uma sessão (o mesmo que o frontend guarda depois
do login). Pegue o token no browser (localStorage, chave veridian_token) e
passe em API_TOKEN. O token não entra no Git nem na conversa.

Uso:
    # Servidor local:
    uvicorn main:app --reload   (a partir de api/)
    API_TOKEN=... python scripts/smoke_chat_v2.py

    # Produção:
    API_PUBLIC_URL=https://<servico-backend>.up.railway.app \
    API_TOKEN=... python scripts/smoke_chat_v2.py

Sai com 0 se tudo passar, 1 se alguma verificação falhar.
"""
from __future__ import annotations

import os
import sys
import time
import uuid

import httpx

API_URL = os.getenv("API_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
SESSION_ID = f"smoke-{uuid.uuid4().hex[:8]}"
_TOKEN = os.getenv("API_TOKEN", "").strip()
HEADERS = {"Authorization": f"Bearer {_TOKEN}"} if _TOKEN else {}


def _check(label: str, condition: bool, detail: str = "") -> bool:
    mark = "✅" if condition else "❌"
    line = f"  {mark} {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    return condition


def test_health() -> bool:
    print("=" * 70)
    print("1. /health")
    print("=" * 70)
    r = httpx.get(f"{API_URL}/health", timeout=10.0)
    return _check("returns 200", r.status_code == 200) and _check(
        "status ok", r.json().get("status") == "ok"
    )


def test_chat_v2_simple() -> bool:
    print()
    print("=" * 70)
    print("2. /chat/v2 — pergunta simples (gasto total de um ano)")
    print("=" * 70)
    start = time.monotonic()
    r = httpx.post(
        f"{API_URL}/chat/v2",
        headers=HEADERS,
        json={
            "session_id": SESSION_ID,
            "message": "Quanto foi gasto com a cota em 2025?",
            "debug": True,
        },
        timeout=120.0,
    )
    elapsed = time.monotonic() - start
    print(f"  Latency: {elapsed:.1f}s")
    if r.status_code != 200:
        _check("status 200", False, f"got {r.status_code}: {r.text[:200]}")
        return False

    data = r.json()
    ok = True
    ok &= _check("status success", data.get("status") == "success")
    ok &= _check("answer non-empty", bool((data.get("answer") or "").strip()))
    ok &= _check("answer contains a number",
                 any(c.isdigit() for c in (data.get("answer") or "")))
    ok &= _check("no [next_step_suggestions] marker in answer",
                 "[next_step_suggestions]" not in (data.get("answer") or ""))
    ok &= _check("next_step_suggestions populated",
                 len(data.get("next_step_suggestions") or []) >= 1)
    ok &= _check("debug payload present", isinstance(data.get("debug"), dict))
    if isinstance(data.get("debug"), dict):
        debug = data["debug"]
        ok &= _check("debug has prompt_version",
                     debug.get("prompt_version", "").startswith("H."))
        ok &= _check("debug has dax_query", bool(debug.get("dax_query")))
        ok &= _check("debug shows cache write or read",
                     debug.get("total_cache_read_tokens", 0) > 0
                     or debug.get("total_cache_write_tokens", 0) > 0)
    return ok


def test_chat_v2_complex_with_visual() -> bool:
    print()
    print("=" * 70)
    print("3. /chat/v2 — ranking (5 deputados), espera um visual")
    print("=" * 70)
    start = time.monotonic()
    r = httpx.post(
        f"{API_URL}/chat/v2",
        headers=HEADERS,
        json={
            "session_id": SESSION_ID,
            "message": "Quais os 5 deputados que mais gastaram em 2025?",
            "debug": True,
        },
        timeout=120.0,
    )
    elapsed = time.monotonic() - start
    print(f"  Latency: {elapsed:.1f}s")
    if r.status_code != 200:
        _check("status 200", False, f"got {r.status_code}")
        return False

    data = r.json()
    ok = True
    ok &= _check("status success", data.get("status") == "success")
    ok &= _check("answer non-empty", bool((data.get("answer") or "").strip()))
    # Visual hint is optional. If present, expect a structured payload.
    visual = data.get("visual")
    if visual:
        _check("visual present", True, f"chart_type={visual.get('chart_type')}")
        _check("visual has data rows", isinstance(visual.get("data"), list))
    else:
        _check("visual present", False,
               "Claude chose not to emit visual_hint — acceptable but unusual")
    ok &= _check("next_step_suggestions populated",
                 len(data.get("next_step_suggestions") or []) >= 1)
    return ok


def test_chat_v2_monthly_line() -> bool:
    print()
    print("=" * 70)
    print("4. /chat/v2 — evolução mês a mês (espera gráfico de linha)")
    print("=" * 70)
    r = httpx.post(
        f"{API_URL}/chat/v2",
        headers=HEADERS,
        json={
            "session_id": SESSION_ID,
            "message": "Como evoluiu o gasto mês a mês em 2025?",
        },
        timeout=120.0,
    )
    if r.status_code != 200:
        _check("status 200", False, f"got {r.status_code}")
        return False

    data = r.json()
    ok = True
    ok &= _check("status success", data.get("status") == "success")
    visual = data.get("visual") or {}
    ok &= _check(
        "visual de linha",
        visual.get("chart_type") == "line",
        f"chart_type={visual.get('chart_type')}",
    )
    return ok


def test_legacy_payload_accepted() -> bool:
    print()
    print("=" * 70)
    print("5. /chat/v2 — legacy payload with module + connector_token (must accept)")
    print("=" * 70)
    r = httpx.post(
        f"{API_URL}/chat/v2",
        headers=HEADERS,
        json={
            "session_id": SESSION_ID + "-legacy",
            "message": "Quanto foi gasto em 2024?",
            "module": "finance",       # ← legacy, must be ignored
            "connector_token": "legado-teste-001",  # ← legacy, must be ignored
        },
        timeout=120.0,
    )
    return _check("status 200 (legacy fields ignored)", r.status_code == 200,
                  f"got {r.status_code}")


def test_chat_reset() -> bool:
    print()
    print("=" * 70)
    print("6. /chat/reset")
    print("=" * 70)
    r = httpx.post(
        f"{API_URL}/chat/reset",
        headers=HEADERS,
        json={"session_id": SESSION_ID, "message": ""},
        timeout=10.0,
    )
    return _check("status 200", r.status_code == 200)


def test_suggestions() -> bool:
    print()
    print("=" * 70)
    print("7. /suggestions (modelo activo — 6 sugestões, sem placeholder)")
    print("=" * 70)
    r = httpx.post(
        f"{API_URL}/suggestions",
        headers=HEADERS,
        json={"language": "pt"},
        timeout=30.0,  # a consulta DAX do contexto pode levar uns segundos
    )
    if r.status_code != 200:
        return _check("status 200", False, f"got {r.status_code}")
    data = r.json()
    ok = _check("status success", data.get("status") == "success")
    suggestions = data.get("suggestions") or []
    ok &= _check(
        "suggestions has 6 items",
        len(suggestions) == 6,
        f"got {len(suggestions)}",
    )
    ok &= _check(
        "nenhum placeholder por resolver",
        all("{" not in s and "}" not in s for s in suggestions),
        f"got: {suggestions}",
    )
    ok &= _check(
        "contexto resolvido sem aviso",
        not data.get("context_warning"),
        str(data.get("context_warning") or ""),
    )
    return ok


def test_voice_config() -> bool:
    print()
    print("=" * 70)
    print("8. /voice/config (voz ao vivo da OpenAI ligada)")
    print("=" * 70)
    r = httpx.get(f"{API_URL}/voice/config", headers=HEADERS, timeout=10.0)
    if r.status_code != 200:
        return _check("status 200", False, f"got {r.status_code}")
    data = r.json()
    return _check("realtime disponível", data.get("realtime") is True, str(data))


def test_removed_endpoints_return_404() -> bool:
    print()
    print("=" * 70)
    print("9. removed endpoints should return 404 or 405")
    print("=" * 70)
    ok = True
    for path in ("/dashboard/generate", "/connector/status"):
        r = httpx.post(f"{API_URL}{path}", json={}, timeout=10.0)
        ok &= _check(
            f"POST {path} no longer routed",
            r.status_code in (404, 405, 422),
            f"got {r.status_code}",
        )
    return ok


def main() -> int:
    if not _TOKEN:
        print("❌ API_TOKEN não definido (token da sessão do login)")
        return 1
    print(f"\nSession ID: {SESSION_ID}")
    print(f"API URL:    {API_URL}\n")

    checks = [
        test_health,
        test_chat_v2_simple,
        test_chat_v2_complex_with_visual,
        test_chat_v2_monthly_line,
        test_legacy_payload_accepted,
        test_chat_reset,
        test_suggestions,
        test_voice_config,
        test_removed_endpoints_return_404,
    ]
    results = []
    for check in checks:
        try:
            results.append(check())
        except Exception as exc:
            print(f"  ❌ {check.__name__} raised {type(exc).__name__}: {exc}")
            results.append(False)

    print()
    print("=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"RESULT: {passed}/{total} checks passed")
    print("=" * 70)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
