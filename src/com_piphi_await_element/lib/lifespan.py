import asyncio
import contextlib
from typing import Any, Dict, Optional

from fastapi import FastAPI
from piphi_runtime_kit_python import (
    rehydrate_runtime_configs,
    resolve_core_base_url,
    runtime_lifespan,
)
from zeroconf import DNSQuestion, DNSQuestionType, ServiceListener
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

from com_piphi_await_element.contract.config.routes import (
    apply_runtime_config_snapshot,
)
from com_piphi_await_element.lib.logging import log_event
from com_piphi_await_element.lib.schemas import AwairElement, RuntimeConfigSnapshot
from com_piphi_await_element.lib.store import get_runtime_context

DISCOVERY_SERVICE_TYPES = ["_http._tcp.local.", "_awair._tcp.local.", "_hap._tcp.local."]
CORE_BASE_URL = resolve_core_base_url("http://127.0.0.1:31419")
CORE_REQUEST_TIMEOUT_SECONDS = 10.0

config: Dict[str, Dict[str, Any]] = {}
runtime_context = get_runtime_context()


class ZeroConfGlobalListener(ServiceListener):
    def __init__(self, aiozc: AsyncZeroconf):
        self.aiozc = aiozc

    def update_service(self, zc: AsyncZeroconf, type_: str, name: str) -> None:
        log_event("service_updated", name=name, type=type_)
        asyncio.create_task(self._handle_service(type_, name))

    def remove_service(self, zc: AsyncZeroconf, type_: str, name: str) -> None:
        log_event("service_removed", name=name, type=type_)
        config.pop(name, None)

    def add_service(self, zc: AsyncZeroconf, type_: str, name: str) -> None:
        log_event("service_discovered", name=name, type=type_)
        asyncio.create_task(self._handle_service(type_, name))

    async def _handle_service(self, type_: str, name: str) -> None:
        info = AsyncServiceInfo(type_, name)
        await info.async_request(self.aiozc.zeroconf, 3000)

        if info and info.addresses:
            addresses = list(info.parsed_addresses())
            config[name] = {
                "name": name,
                "type": type_,
                "addresses": addresses,
                "port": info.port,
                "meta": {
                    key.decode("utf-8", errors="ignore"): value.decode("utf-8", errors="ignore")
                    for key, value in info.properties.items()
                },
            }
            if "awair" in name.lower():
                log_event(
                    "awair_discovered",
                    name=name,
                    type=type_,
                    ip=addresses[0] if addresses else "n/a",
                    port=info.port,
                )


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
    log_event("query_specific_device", name=full_name)
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
        log_event("query_specific_device_found", name=full_name, ip=addresses[0], port=info.port)
    else:
        log_event("query_specific_device_not_found", level="warning", name=full_name)

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

    log_event("awair_discovery_start")
    for service_type in DISCOVERY_SERVICE_TYPES:
        aiozc.zeroconf.send_question(
            DNSQuestion(service_type, DNSQuestionType.PTR, DNSQuestionType.IN)
        )
        log_event("awair_discovery_query", level="debug", service_type=service_type)

    await asyncio.sleep(timeout)

    awair_devices = {
        name: info for name, info in config.items() if "awair" in name.lower()
    }
    for name, info in awair_devices.items():
        addresses = info.get("addresses") or []
        log_event(
            "awair_discovery_result",
            name=name,
            ip=addresses[0] if addresses else "n/a",
            port=info.get("port"),
        )

    for browser in browsers:
        await browser.async_cancel()
    await aiozc.async_close()

    log_event("awair_discovery_complete", count=len(awair_devices))
    return awair_devices


async def find_awair_with_retry(
    max_attempts: int = 3,
    timeout: int = 8,
) -> Dict[str, Dict[str, Any]]:
    for attempt in range(1, max_attempts + 1):
        log_event("awair_discovery_attempt", current=attempt, total=max_attempts)

        config.clear()
        discovered = await discover_awair_actively(timeout)

        if discovered:
            return discovered

        if attempt < max_attempts:
            await asyncio.sleep(2)

    return {}


async def startup_sync(runtime, client) -> None:
    result = await rehydrate_runtime_configs(
        runtime_context=runtime,
        client=client,
        apply_snapshot=apply_runtime_config_snapshot,
        config_model=AwairElement,
        snapshot_model=RuntimeConfigSnapshot,
        core_base_url=CORE_BASE_URL,
        timeout_seconds=CORE_REQUEST_TIMEOUT_SECONDS,
    )

    if result.snapshot_applied:
        log_event(
            "awair_startup_rehydrate_complete",
            loaded=result.snapshot_config_count,
            generation=result.snapshot_generation,
            source="snapshot",
        )
    else:
        log_event("awair_startup_snapshot_rehydrate_skipped", reason="missing_snapshot")

    if result.core_applied:
        log_event(
            "awair_startup_rehydrate_complete",
            loaded=result.core_config_count,
            generation=result.core_generation,
            source="core",
        )
        return

    if result.core_error:
        log_event(
            "awair_startup_core_rehydrate_failed",
            level="warning",
            error=result.core_error,
        )
    elif result.missing_runtime_auth:
        log_event("awair_startup_rehydrate_skipped", reason="missing_runtime_auth")
    elif result.core_attempted:
        log_event("awair_startup_rehydrate_no_configs", source="core")

    if result.snapshot_applied:
        log_event("awair_startup_rehydrate_using_snapshot", reason="core_unavailable")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    aiozc = AsyncZeroconf()
    listener = ZeroConfGlobalListener(aiozc)

    browsers = [
        AsyncServiceBrowser(aiozc.zeroconf, service_type, listener)
        for service_type in DISCOVERY_SERVICE_TYPES
    ]

    log_event("awair_lifespan_start")
    await asyncio.sleep(5)

    awair_devices = {name: info for name, info in config.items() if "awair" in name.lower()}
    if awair_devices:
        log_event("awair_startup_discovery_cached", count=len(awair_devices))

    async with runtime_lifespan(
        runtime_context,
        on_startup=startup_sync,
        core_client_timeout_seconds=CORE_REQUEST_TIMEOUT_SECONDS,
    ):
        try:
            yield
        finally:
            for browser in browsers:
                await browser.async_cancel()
            await aiozc.async_close()
            log_event("awair_lifespan_shutdown")
