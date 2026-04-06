from fastapi import APIRouter
from piphi_runtime_kit_python import (
    RuntimeDiagnosticsResponse,
    RuntimeHealthResponse,
    build_runtime_diagnostics_response,
    build_runtime_health_response,
)
from com_piphi_await_element.lib.manifest import load_manifest
from com_piphi_await_element.lib.store import get_runtime_context, registry


router = APIRouter(tags=['health'])
runtime_context = get_runtime_context()


@router.get('/health')
async def health_report() -> RuntimeHealthResponse:
    manifest = load_manifest()
    return build_runtime_health_response(
        runtime_context,
        integration={
            "id": manifest["id"],
            "name": manifest["name"],
            "version": manifest["version"],
        },
        metadata={
            "devices_configured": len(registry.entries),
            "devices_with_state": len(registry.state_snapshots),
        },
    )


@router.get("/diagnostics")
async def diagnostics_report() -> RuntimeDiagnosticsResponse:
    manifest = load_manifest()
    return build_runtime_diagnostics_response(
        runtime_context,
        integration={
            "id": manifest["id"],
            "name": manifest["name"],
            "version": manifest["version"],
        },
        diagnostics={
            "configured_device_ids": sorted(registry.entries.keys()),
            "devices_with_state": sorted(registry.state_snapshots.keys()),
        },
    )
