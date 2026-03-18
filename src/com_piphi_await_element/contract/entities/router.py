from fastapi import APIRouter
from com_piphi_await_element.lib.manifest import load_manifest


router = APIRouter(tags=['entities'])


@router.get('/entities')
async def get_entities():
    manifest = load_manifest()
    return {
        'entities': manifest.get('entities', []),
        'capabilities': manifest.get('capabilities', {}),
        'commands': manifest.get('commands', {}),
    }
