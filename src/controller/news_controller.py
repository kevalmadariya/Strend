from fastapi import APIRouter, HTTPException
from src.tools.utils.pulse_scraper import extract_pulse_news
from typing import Optional

router = APIRouter()

@router.get("/news/pulse")
async def get_pulse_news(domain: Optional[str] = None):
    """
    Get Pulse news.
    Optional query param 'domain' to filter results (e.g. ?domain=ipo).
    """
    try:
        data = await extract_pulse_news(domain)
        if isinstance(data, dict) and "error" in data:
             raise HTTPException(status_code=500, detail=data["error"])
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
