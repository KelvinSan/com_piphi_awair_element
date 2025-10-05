from fastapi import APIRouter, HTTPException


router = APIRouter(tags=['health'])


@router.get('/health')
async def health_report():
    return 
    # raise HTTPException(status_code=500)