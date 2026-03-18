from fastapi import APIRouter, HTTPException, Query
from com_piphi_await_element.contract.config.routes import trigger_refresh
from com_piphi_await_element.lib.store import devices, get_primary_device, latest_states


router = APIRouter(tags=['state'])


@router.get('/state')
async def get_state(device_id: str | None = Query(default=None)):
    resolved_device_id = device_id
    if resolved_device_id is None:
        primary_device = get_primary_device()
        if primary_device is None:
            raise HTTPException(status_code=404, detail='No configured device found')
        resolved_device_id = primary_device['device_id']
    if resolved_device_id not in latest_states and resolved_device_id in devices:
        await trigger_refresh(resolved_device_id)
    latest_state = latest_states.get(resolved_device_id)
    if latest_state is None:
        raise HTTPException(status_code=404, detail=f"No state available for device '{resolved_device_id}'")
    return latest_state
