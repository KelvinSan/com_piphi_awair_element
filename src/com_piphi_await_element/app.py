


import json
import multiprocessing
from pathlib import Path
import aiofiles
from fastapi import FastAPI
from com_piphi_await_element.contract.health.router import router as health_router
import uvicorn
from com_piphi_await_element.contract.discovery.discovery import  discovery_router
from com_piphi_await_element.contract.ui_schema.router import router as ui_schema
from com_piphi_await_element.contract.config.routes import  config_router
from com_piphi_await_element.lib.lifespan import lifespan

app = FastAPI(lifespan=lifespan)

app.include_router(health_router)

app.include_router(discovery_router)

app.include_router(router=ui_schema)

app.include_router(router=config_router)

@app.get("/manifest.json")
async def display_manifest():
    path = Path(__file__).parent.parent / "manifest.json"
    async with aiofiles.open(path) as f:
        return json.loads(await f.read())

if __name__ == "__main__":
    config = {
        "version": 1,
        "formatters": {"default": {"format": "%(asctime)s [%(levelname)s] %(message)s"}},
        "handlers": {"default": {"class": "logging.StreamHandler", "formatter": "default"}},
        "root": {"handlers": ["default"], "level": "INFO"},
    }
    multiprocessing.freeze_support()
    uvicorn.run(app, host="0.0.0.0", port=3665, log_config=config)