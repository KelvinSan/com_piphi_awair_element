import asyncio
import contextlib
import os
from typing import Any, Dict, Optional

from fastapi import FastAPI
from httpx import AsyncClient
from zeroconf import DNSQuestion, DNSQuestionType, ServiceListener
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

from com_piphi_await_element.contract.config.routes import (
    apply_device_config,
    apply_runtime_config_snapshot,
)
from com_piphi_await_element.lib.logging import logger
from com_piphi_await_element.lib.schemas import AwairElement, RuntimeConfigSnapshot
from com_piphi_await_element.lib.store import set_runtime_auth_context

DISCOVERY_SERVICE_TYPES = ["_http._tcp.local.", "_awair._tcp.local.", "_hap._tcp.local."]
CORE_BASE_URL = "http://127.0.0.1:31419"
RUNTIME_CONTAINER_ID_ENV_NAME = "PIPHI_CONTAINER_ID"
RUNTIME_INTERNAL_TOKEN_ENV_NAME = "PIPHI_INTEGRATION_INTERNAL_TOKEN"

config: Dict[str, Dict[str, Any]] = {}


class ZeroConfGlobalListener(ServiceListener):
    def __init__(self, aiozc: AsyncZeroconf):
        self.aiozc = aiozc

    def update_service(self, zc: AsyncZeroconf, type_: str, name: str) -> None:
        logger.info(f"service_updated name={name}")
        asyncio.create_task(self._handle_service(type_, name))

    def remove_service(self, zc: AsyncZeroconf, type_: str, name: str) -> None:
        logger.info(f"service_removed name={name}")
        config.pop(name, None)

    def add_service(self, zc: AsyncZeroconf, type_: str, name: str) -> None:
        asyncio.create_task(self._handle_service(type_, name))

    async def _handle_service(self, type_: str, name: str) -> None:
        info = AsyncServiceInfo(type_, name)
        await info.async_request(self.aiozc.zeroconf, 3000)

        if info and info.addresses:
            config[name] = {
                "name": name,
                "type": type_,
                "addresses": list(info.parsed_addresses()),
                "port": info.port,
                "meta": {
                    key.decode("utf-8", errors="ignore"): value.decode("utf-8", errors="ignore")
                    for key, value in info.properties.items()
                },
            }


async def query_specific_awair(
    service_name: str,
    service_type: str = "_http._tcp.local.",
) -> Optional[Dict[str, Any]]:
    """Query for one specific Awair service name."""
    aiozc = AsyncZeroconf()

    full_name = (
        f"{service_name}.{service_type}"
        if not service_name.endswith(service_type)
        else service_name
    )

    info = AsyncServiceInfo(service_type, full_name)
    logger.info(f"query_specific_device name={full_name}")
    success = await info.async_request(aiozc.zeroconf, 3000)

    result: Optional[Dict[str, Any]] = None
    if success and info.addresses:
        addresses = list(info.parsed_addresses())
        result = {
            "name": full_name,
            "type": service_type,
            "addresses": addresses,
            "port": info.port,
            "meta": {
                key.decode("utf-8", errors="ignore"): value.decode("utf-8", errors="ignore")
                for key, value in info.properties.items()
            },
        }
        logger.info(f"query_specific_device_found name={full_name} ip={addresses[0]} port={info.port}")
    else:
        logger.warning(f"query_specific_device_not_found name={full_name}")

    await aiozc.async_close()
    return result


async def discover_awair_actively(timeout: int = 10) -> Dict[str, Dict[str, Any]]:
    """Active discovery of Awair devices via PTR queries."""
    aiozc = AsyncZeroconf()
    listener = ZeroConfGlobalListener(aiozc)

    browsers = [
        AsyncServiceBrowser(aiozc.zeroconf, service_type, listener)
        for service_type in DISCOVERY_SERVICE_TYPES
    ]

    logger.info("awair_discovery_start")
    for service_type in DISCOVERY_SERVICE_TYPES:
        aiozc.zeroconf.send_question(
            DNSQuestion(service_type, DNSQuestionType.PTR, DNSQuestionType.IN)
        )
        logger.debug(f"awair_discovery_query service_type={service_type}")

    await asyncio.sleep(timeout)

    awair_devices = {
        name: info for name, info in config.items() if "awair" in name.lower()
    }

    for browser in browsers:
        await browser.async_cancel()
    await aiozc.async_close()

    logger.info(f"awair_discovery_complete count={len(awair_devices)}")
    return awair_devices


async def find_awair_with_retry(
    max_attempts: int = 3,
    timeout: int = 8,
) -> Dict[str, Dict[str, Any]]:
    for attempt in range(1, max_attempts + 1):
        logger.info(f"awair_discovery_attempt current={attempt} total={max_attempts}")

        config.clear()
        discovered = await discover_awair_actively(timeout)

        if discovered:
            return discovered

        if attempt < max_attempts:
            await asyncio.sleep(2)

    return {}


async def bootstrap_devices_from_discovery(container_id: str | None = None) -> None:
    awair_devices = {name: info for name, info in config.items() if "awair" in name.lower()}
    if not awair_devices:
        awair_devices = await discover_awair_actively(timeout=3)

    if not awair_devices:
        logger.info("awair_local_bootstrap_no_devices")
        return

    applied = 0
    for info in awair_devices.values():
        addresses = info.get("addresses") or []
        if not addresses:
            continue

        device_ip = str(addresses[0]).strip()
        if not device_ip:
            continue

        meta = info.get("meta") or {}
        device_mac = meta.get("mac") or meta.get("id") or meta.get("serial")
        device_id = f"awair-{device_ip.replace('.', '-')}"

        await apply_device_config(
            AwairElement(
                id=device_id,
                device_ip=device_ip,
                container_id=container_id or None,
                device_mac=device_mac,
            )
        )
        applied += 1

    logger.info(f"awair_local_bootstrap_complete applied={applied}")


async def call_core_for_devices(container_id: str, internal_token: str) -> None:
    async with AsyncClient() as client:
        response = await client.get(
            f"{CORE_BASE_URL}/api/v2/integrations/config/fetch/all/by/container/internal",
            params={"container_id": container_id},
            headers={
                "X-Container-Id": container_id,
                "X-PiPhi-Integration-Token": internal_token,
            },
        )
        response.raise_for_status()

    data = response.json()
    if not data:
        logger.info("awair_startup_rehydrate_no_configs")
        return

    snapshot = RuntimeConfigSnapshot(
        container_id=container_id,
        reason="startup_rehydrate",
        configs=[AwairElement(**item["config_data"], container_id=container_id) for item in data],
    )
    await apply_runtime_config_snapshot(snapshot)
    logger.info(f"awair_startup_rehydrate_complete loaded={len(data)}")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    aiozc = AsyncZeroconf()
    listener = ZeroConfGlobalListener(aiozc)

    browsers = [
        AsyncServiceBrowser(aiozc.zeroconf, service_type, listener)
        for service_type in DISCOVERY_SERVICE_TYPES
    ]

    logger.info("awair_lifespan_start")
    await asyncio.sleep(5)

    awair_devices = {name: info for name, info in config.items() if "awair" in name.lower()}
    if awair_devices:
        logger.info(f"awair_startup_discovery_cached count={len(awair_devices)}")

    container_id = (os.getenv(RUNTIME_CONTAINER_ID_ENV_NAME) or "").strip()
    internal_token = (os.getenv(RUNTIME_INTERNAL_TOKEN_ENV_NAME) or "").strip()

    set_runtime_auth_context(
        container_id=container_id,
        internal_token=internal_token,
    )

    if internal_token and container_id:
        await call_core_for_devices(
            container_id=container_id,
            internal_token=internal_token,
        )
        await bootstrap_devices_from_discovery(container_id=container_id)
    else:
        logger.warning(
            "awair_startup_missing_runtime_credentials "
            "skipping_core_rehydrate_and_local_bootstrap=true"
        )

    yield

    logger.info("awair_lifespan_shutdown")
    for browser in browsers:
        await browser.async_cancel()
    await aiozc.async_close()
