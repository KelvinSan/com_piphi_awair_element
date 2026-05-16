from fastapi import APIRouter, HTTPException
import httpx

from com_piphi_await_element.contract.config.routes import trigger_refresh
from com_piphi_await_element.lib.manifest import load_manifest
from com_piphi_await_element.lib.schemas import CommandRequest
from com_piphi_await_element.lib.store import get_primary_device, registry


router = APIRouter(tags=['command'])

COMMAND_ALIASES = {
    'refresh_readings': 'refresh',
    'device.refresh': 'refresh',
}
IMPLEMENTED_COMMANDS = {'refresh', 'notify', 'discord_webhook'}
DISCORD_WEBHOOK_PREFIXES = (
    'https://discord.com/api/webhooks/',
    'https://discordapp.com/api/webhooks/',
)


def _command_name(payload: CommandRequest) -> str:
    return COMMAND_ALIASES.get(payload.command.strip(), payload.command.strip())


def _structured_error(status_code: int, code: str, message: str):
    raise HTTPException(
        status_code=status_code,
        detail={
            'ok': False,
            'error': code,
            'message': message,
        },
    )


def _target_value(payload: CommandRequest, key: str) -> str | None:
    value = payload.target.get(key)
    return str(value).strip() if value is not None and str(value).strip() else None


def _resolve_device_id(payload: CommandRequest) -> str:
    device_id = payload.device_id or _target_value(payload, 'device_id')
    if device_id:
        return device_id
    config_id = payload.config_id or _target_value(payload, 'config_id')
    if config_id:
        configured = registry.get(config_id)
        if configured is not None:
            return configured['device_id']
    primary_device = get_primary_device()
    if primary_device is None:
        _structured_error(404, 'missing_target', 'No configured Awair Element device found')
    return primary_device['device_id']


def _validate_capability(payload: CommandRequest) -> None:
    requested = {item for item in [payload.capability, *payload.capability_requirements] if item}
    unsupported = requested - {
        'device.refresh',
        'refresh',
        'air_quality.readings',
        'notification.send',
        'notification.discord_webhook',
    }
    if unsupported:
        unsupported_text = sorted(unsupported)[0]
        _structured_error(
            400,
            'unsupported_capability',
            f"Awair Element does not support capability '{unsupported_text}'",
        )


def _command_params(payload: CommandRequest) -> dict:
    return payload.params or payload.args or {}


def _discord_webhook_url(params: dict) -> str:
    webhook_url = str(params.get('webhook_url') or params.get('webhookUrl') or '').strip()
    if not webhook_url:
        _structured_error(400, 'missing_webhook_url', 'Discord webhook URL is required')
    if not webhook_url.startswith(DISCORD_WEBHOOK_PREFIXES):
        _structured_error(400, 'invalid_webhook_url', 'Discord webhook URL must be a Discord webhook URL')
    return webhook_url


async def _send_discord_webhook(params: dict) -> dict:
    webhook_url = _discord_webhook_url(params)
    message = str(params.get('message') or 'Awair Element alert').strip() or 'Awair Element alert'
    username = str(params.get('username') or 'PiPhi Network').strip() or 'PiPhi Network'
    payload = {'content': message, 'username': username}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(webhook_url, json=payload)
    if response.status_code >= 400:
        _structured_error(
            502,
            'discord_webhook_failed',
            f'Discord webhook returned HTTP {response.status_code}',
        )
    return {
        'delivered': True,
        'channel': 'discord',
        'message': message,
    }


@router.post('/command')
async def execute_command(payload: CommandRequest):
    manifest = load_manifest()
    commands = manifest.get('commands', {})
    command = _command_name(payload)
    if command not in commands and command not in IMPLEMENTED_COMMANDS:
        _structured_error(400, 'unsupported_command', f"Unsupported command: {payload.command}")
    _validate_capability(payload)
    params = _command_params(payload)
    if command == 'discord_webhook':
        result = await _send_discord_webhook(params)
        return {
            'ok': True,
            'status': 'ok',
            'command': command,
            'contract_version': payload.contract_version,
            'device_id': payload.device_id or _target_value(payload, 'device_id'),
            'target': payload.target,
            'params': params,
            'result': result,
        }
    if command == 'notify':
        return {
            'ok': True,
            'status': 'ok',
            'command': command,
            'contract_version': payload.contract_version,
            'device_id': payload.device_id or _target_value(payload, 'device_id'),
            'target': payload.target,
            'params': params,
            'result': {
                'delivered': True,
                'channel': params.get('channel', 'in_app'),
                'message': params.get('message', ''),
            },
        }
    device_id = _resolve_device_id(payload)
    refreshed_state = await trigger_refresh(device_id)
    return {
        'ok': True,
        'status': 'ok',
        'command': command,
        'contract_version': payload.contract_version,
        'device_id': device_id,
        'target': payload.target,
        'params': params,
        'result': refreshed_state,
    }
