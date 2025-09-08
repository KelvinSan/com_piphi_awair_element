
from fastapi import APIRouter


config_router = APIRouter(tags=['config'])

@config_router.post('/config')
async def config():
    return


