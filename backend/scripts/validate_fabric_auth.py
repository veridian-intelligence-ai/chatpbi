"""Runtime validation script for the Fabric adapter.

Usage:
    python scripts/validate_fabric_auth.py

Reads FABRIC_TENANT_ID, FABRIC_CLIENT_ID, FABRIC_CLIENT_SECRET,
FABRIC_WORKSPACE_ID and (optional) FABRIC_DEFAULT_DATASET_ID from `.env`
at the project root, instantiates the real FabricClient and runs:

    1. health_check()                          — confirms API reachability
    2. list_models()                           — enumerates semantic models
    3. execute_query(DEFAULT_DATASET_ID, ...)  — runs a trivial DAX query
       (skipped with a warning if FABRIC_DEFAULT_DATASET_ID is unset)

Exits 0 on success, 1 on failure.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

load_dotenv(_PROJECT_ROOT / ".env")

from api.adapters.fabric import (  # noqa: E402
    FabricAPIError,
    FabricAuthenticator,
    FabricAuthError,
    FabricClient,
    FabricConfigError,
)


def _mask(value: str, keep: int = 8) -> str:
    """Return a short, non-sensitive prefix of a credential value."""
    if not value:
        return "<not set>"
    if len(value) <= keep:
        return "***"
    return f"{value[:keep]}..."


def _print_header() -> None:
    bar = "=" * 60
    print(bar)
    print("Fabric adapter — runtime validation")
    print(bar)


def _run_health_check(client: FabricClient) -> bool:
    print("→ Running health_check()...")
    start = time.monotonic()
    try:
        success = client.health_check()
    except FabricAuthError as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        print(f"❌ Auth error after {elapsed_ms}ms: {exc}")
        return False
    except Exception as exc:  # noqa: BLE001 — surface any unexpected failure
        elapsed_ms = int((time.monotonic() - start) * 1000)
        print(
            f"❌ Unexpected error after {elapsed_ms}ms: "
            f"{type(exc).__name__}: {exc}"
        )
        return False

    elapsed_ms = int((time.monotonic() - start) * 1000)
    if success:
        print(f"✅ health_check OK ({elapsed_ms}ms)")
        return True

    print(f"❌ Fabric health check returned False after {elapsed_ms}ms")
    print()
    print("Possible causes:")
    print("  • Service Principal not added as Member of the workspace")
    print("  • Service Principal missing Power BI API permissions")
    print("  • Network issue reaching api.powerbi.com")
    return False


def _run_list_models(client: FabricClient) -> bool:
    print()
    print("→ Running list_models()...")
    start = time.monotonic()
    try:
        models = client.list_models()
    except (FabricAuthError, FabricAPIError, FabricConfigError) as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        print(f"❌ list_models failed after {elapsed_ms}ms: {exc}")
        return False
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.monotonic() - start) * 1000)
        print(
            f"❌ Unexpected error after {elapsed_ms}ms: "
            f"{type(exc).__name__}: {exc}"
        )
        return False

    elapsed_ms = int((time.monotonic() - start) * 1000)
    print(f"✅ list_models returned {len(models)} models ({elapsed_ms}ms)")

    if not models:
        print("❌ Expected at least one semantic model in the workspace.")
        return False

    print("  First models:")
    for model in models[:5]:
        print(f"   • {model.id}  {model.name}")
    return True


def _run_execute_query(client: FabricClient, dataset_id: str) -> bool:
    print()
    print(f"→ Running execute_query(dataset_id={_mask(dataset_id)})...")
    dax = 'EVALUATE ROW("test", 1)'
    start = time.monotonic()
    try:
        result = client.execute_query(dataset_id, dax)
    except (FabricAuthError, FabricAPIError, FabricConfigError) as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        print(f"❌ execute_query failed after {elapsed_ms}ms: {exc}")
        if getattr(exc, "context", None):
            status = exc.context.get("status_code")
            if status is not None:
                print(f"   status_code: {status}")
        return False
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.monotonic() - start) * 1000)
        print(
            f"❌ Unexpected error after {elapsed_ms}ms: "
            f"{type(exc).__name__}: {exc}"
        )
        return False

    elapsed_ms = int((time.monotonic() - start) * 1000)
    print(
        f"✅ execute_query returned {result.row_count} rows ({elapsed_ms}ms)"
    )
    print(f"   columns: {result.columns}")
    if result.rows:
        print(f"   first row: {result.rows[0]}")
    return True


def main() -> int:
    _print_header()

    tenant_id = os.getenv("FABRIC_TENANT_ID", "")
    client_id = os.getenv("FABRIC_CLIENT_ID", "")
    client_secret = os.getenv("FABRIC_CLIENT_SECRET", "")
    workspace_id = os.getenv("FABRIC_WORKSPACE_ID", "")
    default_dataset_id = os.getenv("FABRIC_DEFAULT_DATASET_ID", "")

    print(f"  Tenant:        {_mask(tenant_id)}")
    print(f"  Client ID:     {_mask(client_id)}")
    print(f"  Client secret: {_mask(client_secret)}")
    print(f"  Workspace:     {workspace_id or '<not set>'}")
    print(f"  Default DSet:  {_mask(default_dataset_id)}")
    print()

    try:
        authenticator = FabricAuthenticator()
    except FabricConfigError as exc:
        print(f"❌ Configuration error: {exc}")
        return 1

    client = FabricClient(authenticator)

    if not _run_health_check(client):
        return 1

    if not _run_list_models(client):
        return 1

    if default_dataset_id.strip():
        if not _run_execute_query(client, default_dataset_id.strip()):
            return 1
    else:
        print()
        print(
            "⚠️  FABRIC_DEFAULT_DATASET_ID not set — skipping execute_query test."
        )
        print(
            "    Set it in .env to validate DAX execution against a real dataset."
        )

    print()
    print("✅ Fabric adapter is functionally complete.")
    print()
    print("Next steps:")
    print("  • F.4 — cache semantic model metadata")
    print("  • F.5 — wire FabricClient into /chat/v2 endpoint")
    return 0


if __name__ == "__main__":
    sys.exit(main())
