from fastapi import APIRouter
from piphi_runtime_kit_python import (
    IntegrationEventIngestResponse,
    IntegrationEventListResponse,
    IntegrationEventRequest,
    build_event_ingest_response,
    build_event_list_response,
    format_event_log,
)

from com_piphi_await_element.lib.logging import log_event
from com_piphi_await_element.lib.store import append_event, registry

router = APIRouter(tags=["events"])


@router.get('/events')
async def get_events() -> IntegrationEventListResponse:
    log_event("events_list", count=len(registry.recent_events))
    return build_event_list_response(registry.recent_events)


@router.post('/events')
async def ingest_event(payload: IntegrationEventRequest) -> IntegrationEventIngestResponse:
    event = append_event(payload.model_dump())
    log_event("event_ingested", message=format_event_log(payload))
    return build_event_ingest_response(event)
