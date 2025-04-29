"""
FastAPI router for glucose entry endpoints.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from app.services.database import db_service
from app.tasks.glucose import fetch_glucose_data

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/entries", tags=["entries"])


# Define Pydantic models for request/response validation
class GlucoseReading(BaseModel):
    """Model representing a glucose reading."""
    device: str
    timestamp: datetime
    device_timestamp: datetime
    sgv: int
    direction: str
    type: str
    glucose_units: str


class LatestReadingResponse(BaseModel):
    """Response model for the latest reading endpoint."""
    reading: Optional[GlucoseReading] = None
    time_ago_seconds: Optional[int] = None
    success: bool
    message: str


class EntriesListResponse(BaseModel):
    """Response model for the entries list endpoint."""
    entries: List[GlucoseReading]
    count: int
    success: bool
    message: str


# API Endpoints
@router.get("/latest", response_model=LatestReadingResponse)
async def get_latest_entry() -> Dict[str, Any]:
    """
    Get the most recent glucose reading.
    
    Returns:
        Dict: The latest reading with time since reading
    """
    try:
        latest = db_service.get_latest_entry()
        
        if not latest:
            return {
                "reading": None,
                "time_ago_seconds": None,
                "success": False,
                "message": "No glucose readings found in database"
            }
        
        # Calculate time since reading
        now = datetime.utcnow()
        time_ago = (now - latest["timestamp"]).total_seconds()
        
        return {
            "reading": latest,
            "time_ago_seconds": int(time_ago),
            "success": True,
            "message": "Latest reading retrieved successfully"
        }
    except Exception as e:
        logger.error(f"Error fetching latest entry: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("", response_model=EntriesListResponse)
async def get_entries(hours: int = Query(24, ge=1, le=168)) -> Dict[str, Any]:
    """
    Get glucose readings from the past specified hours.
    
    Args:
        hours: Number of hours to look back (1-168, default: 24)
        
    Returns:
        Dict: List of entries with count
    """
    try:
        entries = db_service.get_entries_since(hours)
        
        return {
            "entries": entries,
            "count": len(entries),
            "success": True,
            "message": f"Retrieved {len(entries)} entries from the past {hours} hours"
        }
    except Exception as e:
        logger.error(f"Error fetching entries: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.post("/refresh", status_code=202)
async def refresh_data() -> Dict[str, Any]:
    """
    Manually trigger a refresh of glucose data.
    
    Returns:
        Dict: Status of the refresh request
    """
    try:
        # Call the Celery task synchronously for immediate response
        # In a production app, you might want to use task.delay() instead
        task = fetch_glucose_data.apply_async(countdown=1)
        
        return {
            "success": True,
            "message": "Refresh task scheduled",
            "task_id": task.id
        }
    except Exception as e:
        logger.error(f"Error scheduling refresh task: {e}")
        raise HTTPException(status_code=500, detail=f"Error scheduling refresh: {str(e)}")