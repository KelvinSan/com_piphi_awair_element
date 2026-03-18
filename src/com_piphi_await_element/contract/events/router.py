from fastapi import APIRouter
from com_piphi_await_element.lib.schemas import EventRequest
from com_piphi_await_element.lib.store import append_event, recent_events


router = APIRouter(tags=['events'])


@router.get('/events')
async def get_events():
    return {
        'events': recent_events,
    }


@router.post('/events')
async def ingest_event(payload: EventRequest):
    event = append_event(payload.model_dump())
    return {
        'status': 'accepted',
        'event': event,
    }
