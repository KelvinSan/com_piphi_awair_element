import asyncio
import contextlib
import json
from pathlib import Path
from typing import Dict, Optional
from fastapi import FastAPI
from zeroconf import ServiceListener, DNSQuestion, DNSQuestionType
from zeroconf.asyncio import AsyncZeroconf, AsyncServiceBrowser, AsyncServiceInfo
from httpx import AsyncClient
config = {}


config = {}


class ZeroConfGlobalListener(ServiceListener):
    def __init__(self, aiozc: AsyncZeroconf):
        self.aiozc = aiozc

    def update_service(self, zc: AsyncZeroconf, type_: str, name: str) -> None:
        print(f"Service {name} updated")
        asyncio.create_task(self._handle_service(type_, name))

    def remove_service(self, zc: AsyncZeroconf, type_: str, name: str) -> None:
        print(f"Service {name} removed")
        if name in config:
            del config[name]

    def add_service(self, zc: AsyncZeroconf, type_: str, name: str) -> None:
        asyncio.create_task(self._handle_service(type_, name))

    async def _handle_service(self, type_: str, name: str) -> None:
        """Async method to fetch and store service info"""
        info = AsyncServiceInfo(type_, name)
        await info.async_request(self.aiozc.zeroconf, 3000)

        if info and info.addresses:
            addresses = [addr for addr in info.parsed_addresses()]
            props = {
                k.decode("utf-8", errors="ignore"): v.decode("utf-8", errors="ignore")
                for k, v in info.properties.items()
            }
            config[name] = {
                "name": name,
                "type": type_,
                "addresses": addresses,
                "port": info.port,
                "meta": props,
            }


async def query_specific_awair(
    service_name: str, service_type: str = "_http._tcp.local."
) -> Optional[Dict]:
    """Query for a specific Awair device by exact name"""
    aiozc = AsyncZeroconf()

    full_name = (
        f"{service_name}.{service_type}"
        if not service_name.endswith(service_type)
        else service_name
    )
    info = AsyncServiceInfo(service_type, full_name)

    print(f"🔍 Querying for specific device: {full_name}")
    success = await info.async_request(aiozc.zeroconf, 3000)

    result = None
    if success and info.addresses:
        addresses = [addr for addr in info.parsed_addresses()]
        props = {
            k.decode("utf-8", errors="ignore"): v.decode("utf-8", errors="ignore")
            for k, v in info.properties.items()
        }
        result = {
            "name": full_name,
            "type": service_type,
            "addresses": addresses,
            "port": info.port,
            "meta": props,
        }
        print(f"✓ Found: {full_name} at {addresses[0]}:{info.port}")
    else:
        print(f"✗ Device not found: {full_name}")

    await aiozc.async_close()
    return result


async def discover_awair_actively(timeout: int = 10) -> Dict[str, Dict]:
    """Active discovery of Awair devices using PTR queries"""
    aiozc = AsyncZeroconf()
    listener = ZeroConfGlobalListener(aiozc)

    service_types = [
        "_http._tcp.local.",
        "_awair._tcp.local.",
        "_hap._tcp.local.",
    ]

    # Start browsers
    browsers = []
    for service_type in service_types:
        browser = AsyncServiceBrowser(aiozc.zeroconf, service_type, listener)
        browsers.append(browser)

    # Send PTR queries to force immediate responses
    print("🔍 Sending PTR queries for active Awair discovery...")
    for service_type in service_types:
        aiozc.zeroconf.send_question(
            DNSQuestion(service_type, DNSQuestionType.PTR, DNSQuestionType.IN)
        )
        print(f"  → Querying: {service_type}")

    # Wait for responses
    print(f"Listening for responses ({timeout}s)...")
    await asyncio.sleep(timeout)

    # Filter for Awair devices
    awair_devices = {
        name: info for name, info in config.items() if "awair" in name.lower()
    }

    # Cleanup
    for browser in browsers:
        await browser.async_cancel()
    await aiozc.async_close()

    if awair_devices:
        print(f"\n{'='*60}")
        print(f"✓ Found {len(awair_devices)} Awair device(s):")
        print(f"{'='*60}")
        for name, info in awair_devices.items():
            print(f"\n📡 {name}")
            print(f"   IP: {info['addresses'][0] if info['addresses'] else 'unknown'}")
            print(f"   Port: {info['port']}")
            print(f"   Type: {info['type']}")
            if info["meta"]:
                print(f"   Properties: {info['meta']}")
    else:
        print("\n❌ No Awair devices found")

    return awair_devices


async def find_awair_with_retry(
    max_attempts: int = 3, timeout: int = 8
) -> Dict[str, Dict]:
    """Retry active discovery multiple times"""
    for attempt in range(1, max_attempts + 1):
        print(f"\n{'='*60}")
        print(f"Attempt {attempt}/{max_attempts}")
        print(f"{'='*60}")

        # Clear previous results
        config.clear()

        devices = await discover_awair_actively(timeout)

        if devices:
            return devices

        if attempt < max_attempts:
            print(f"\nNo devices found, retrying in 2 seconds...")
            await asyncio.sleep(2)

    return {}

async def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

async def call_core_for_devices(container_id: str):
    async with AsyncClient() as client:
        response = await client.get("http://127.0.0.1:31419/api/v2/integrations/config/fetch/all/by/container", params={"container_id": container_id})
        data  = response.json()
        if len(data) == 0:
            print("No device has been configured for this container")
            
        # TODO: Handle case where there are multiple devices, start polling on start up

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    aiozc = AsyncZeroconf()
    listener = ZeroConfGlobalListener(aiozc)

    # Monitor multiple service types for Awair
    service_types = ["_http._tcp.local.", "_awair._tcp.local.", "_hap._tcp.local."]
    browsers = [
        AsyncServiceBrowser(aiozc.zeroconf, service_type, listener)
        for service_type in service_types
    ]

    # Initial discovery
    print("🚀 Starting Awair device monitoring...")
    await asyncio.sleep(5)

    awair_devices = {k: v for k, v in config.items() if "awair" in k.lower()}
    if awair_devices:
        print(f"✓ Found {len(awair_devices)} Awair device(s) on startup")
    config_file = await load_config()
    await call_core_for_devices(container_id=config_file["container_id"])
    yield

    print("🛑 Shutting down Awair discovery...")
    for browser in browsers:
        await browser.async_cancel()
    await aiozc.async_close()
