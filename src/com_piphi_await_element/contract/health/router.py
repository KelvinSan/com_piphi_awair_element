from fastapi import APIRouter
from com_piphi_await_element.lib.manifest import load_manifest
from com_piphi_await_element.lib.store import devices, latest_states


router = APIRouter(tags=['health'])


@router.get('/health')
async def health_report():
    manifest = load_manifest()
    return {
        "status": "ok",
        "integration": {
            "id": manifest["id"],
            "name": manifest["name"],
            "version": manifest["version"],
        },
        "devices_configured": len(devices),
        "devices_with_state": len(latest_states),
    }