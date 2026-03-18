from fastapi import APIRouter, HTTPException
from com_piphi_await_element.contract.config.routes import trigger_refresh
from com_piphi_await_element.lib.manifest import load_manifest
from com_piphi_await_element.lib.schemas import CommandRequest
from com_piphi_await_element.lib.store import get_primary_device


router = APIRouter(tags=['command'])


@router.post('/command')
async def execute_command(payload: CommandRequest):
    manifest = load_manifest()
    commands = manifest.get('commands', {})
    if payload.command not in commands:
        raise HTTPException(status_code=404, detail=f"Unknown command '{payload.command}'")
    if payload.command != 'refresh':
        raise HTTPException(status_code=400, detail=f"Command '{payload.command}' is not implemented")
    device_id = payload.device_id
    if device_id is None:
        primary_device = get_primary_device()
        if primary_device is None:
            raise HTTPException(status_code=404, detail='No configured device found')
        device_id = primary_device['device_id']
    refreshed_state = await trigger_refresh(device_id)
    return {
        'status': 'ok',
        'command': payload.command,
        'device_id': device_id,
        'result': refreshed_state,
    }
