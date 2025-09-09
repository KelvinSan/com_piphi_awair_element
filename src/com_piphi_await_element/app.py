


import json
import multiprocessing
from pathlib import Path
import aiofiles
from fastapi import FastAPI
from com_piphi_await_element.contract.health.router import router as health_router
import uvicorn

app = FastAPI()

app.include_router(health_router)

@app.get("/manifest.json")
async def display_manifest():
    path = Path(__file__).parent.parent / "manifest.json"
    async with aiofiles.open(path) as f:
        return json.loads(await f.read())

if __name__ == "__main__":
    multiprocessing.freeze_support()
    uvicorn.run("piphi:app", host="0.0.0.0", port=1598, reload=True)