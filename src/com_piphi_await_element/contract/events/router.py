from fastapi import APIRouter

from com_piphi_await_element.lib.logging import log_event
from com_piphi_await_element.lib.schemas import EventRequest
from com_piphi_await_element.lib.store import append_event, recent_events

router = APIRouter(tags=["events"])


@router.get('/events')
async def get_events():
    log_event("events_list", count=len(recent_events))
    return {
        'events': recent_events,
    }


@router.post('/events')
async def ingest_event(payload: EventRequest):
    event = append_event(payload.model_dump())
    log_event("event_ingested", event_type=payload.event_type, source=payload.source or "unknown")
    return {
        'status': 'accepted',
        'event': event,
    }
