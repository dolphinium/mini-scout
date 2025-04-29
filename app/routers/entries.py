import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks
from pydantic import BaseModel

from app.services import database, librelinkup
from app.services.database import parse_timestamp

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/api/entries",
    tags=["entries"],
    responses={404: {"description": "Not found"}},
)

# Define response models
class GlucoseReading(BaseModel):
    timestamp: str
    value: float
    trend: Optional[str] = None
    
    class Config:
        from_attributes = True

class GlucoseResponse(BaseModel):
    readings: List[GlucoseReading]
    unit: str = "mg/dL"

class LatestReadingResponse(BaseModel):
    timestamp: str
    value: float
    trend: Optional[str] = None
    time_ago_minutes: Optional[float] = None
    unit: str = "mg/dL"


def _format_reading(raw_reading: Dict[str, Any]) -> GlucoseReading:
    """Format a raw glucose reading into a response model."""
    # Extract timestamp
    timestamp_str = raw_reading.get('Timestamp', '')
    # Use parsed timestamp if available, otherwise parse it or use now
    if 'parsedTimestamp' in raw_reading:
        timestamp = raw_reading['parsedTimestamp']
    elif timestamp_str:
        timestamp = parse_timestamp(timestamp_str) or datetime.now(timezone.utc)
    else:
        timestamp = datetime.now(timezone.utc)
    
    # Format as ISO string
    iso_timestamp = timestamp.isoformat()
    
    # Extract glucose value
    value = raw_reading.get('ValueInMgPerDl', 0)
    
    # Extract trend arrow
    trend = raw_reading.get('TrendArrow')
    
    return GlucoseReading(
        timestamp=iso_timestamp,
        value=value,
        trend=trend
    )


@router.get("/latest", response_model=LatestReadingResponse)
async def get_latest_reading():
    """Get the latest glucose reading."""
    # Get latest reading from database
    raw_reading = database.get_latest_reading()
    
    if not raw_reading:
        raise HTTPException(status_code=404, detail="No readings found")
    
    # Format the reading
    reading = _format_reading(raw_reading)
    
    # Calculate time ago
    timestamp = None
    try:
        if 'parsedTimestamp' in raw_reading:
            timestamp = raw_reading['parsedTimestamp']
        elif reading.timestamp:
            timestamp = datetime.fromisoformat(reading.timestamp.replace('Z', '+00:00'))
    except ValueError:
        pass
    
    time_ago_minutes = None
    if timestamp:
        time_ago = datetime.now(timezone.utc) - timestamp
        time_ago_minutes = time_ago.total_seconds() / 60
    
    # Create response
    return LatestReadingResponse(
        timestamp=reading.timestamp,
        value=reading.value,
        trend=reading.trend,
        time_ago_minutes=time_ago_minutes,
        unit="mg/dL"
    )


@router.get("/", response_model=GlucoseResponse)
async def get_glucose_history(hours: int = Query(24, ge=1, le=168)):
    """Get glucose history for a specified number of hours."""
    # Validate hours parameter
    if hours < 1 or hours > 168:  # 1 hour to 7 days
        raise HTTPException(status_code=400, detail="Hours must be between 1 and 168")
    
    # Get history from database
    raw_readings = database.get_glucose_history(hours)
    
    if not raw_readings:
        raise HTTPException(status_code=404, detail="No readings found for the specified time period")
    
    # Format readings
    readings = [_format_reading(raw) for raw in raw_readings]
    
    # Sort readings by timestamp (newest first)
    readings.sort(key=lambda r: r.timestamp, reverse=True)
    
    return GlucoseResponse(readings=readings)


@router.post("/fetch")
async def trigger_fetch():
    """Manually trigger a fetch of glucose data from LibreLink Up."""
    try:
        # Fetch data from LibreLink Up
        glucose_data = librelinkup.fetch_glucose_data_with_retry(max_retries=1)
        
        if not glucose_data:
            raise HTTPException(
                status_code=500,
                detail="Failed to fetch glucose data from LibreLink Up"
            )
        
        # Save data to MongoDB
        save_success = database.save_glucose_data(glucose_data)
        
        if not save_success:
            raise HTTPException(
                status_code=500,
                detail="Failed to save glucose data to MongoDB"
            )
        
        # Return success response
        return {
            "status": "success",
            "message": "Glucose data fetched and stored successfully",
            "latest_value": glucose_data.get('latest', {}).get('ValueInMgPerDl'),
            "history_count": len(glucose_data.get('history', []))
        }
    
    except Exception as e:
        logger.exception(f"Error in manual fetch: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching glucose data: {str(e)}"
        )


@router.get("/stats")
async def get_statistics(hours: int = Query(24, ge=1, le=168)):
    """Get glucose statistics for a specified time period."""
    # Get history from database
    raw_readings = database.get_glucose_history(hours)
    
    if not raw_readings:
        raise HTTPException(status_code=404, detail="No readings found for the specified time period")
    
    # Extract glucose values
    values = [r.get('ValueInMgPerDl', 0) for r in raw_readings if 'ValueInMgPerDl' in r]
    
    if not values:
        raise HTTPException(status_code=404, detail="No glucose values found for the specified time period")
    
    # Calculate statistics
    count = len(values)
    avg = sum(values) / count if count > 0 else 0
    min_val = min(values) if values else 0
    max_val = max(values) if values else 0
    
    # Calculate time in range (70-180 mg/dL)
    in_range = sum(1 for v in values if 70 <= v <= 180)
    time_in_range_percent = (in_range / count) * 100 if count > 0 else 0
    
    # Calculate low and high percentages
    low = sum(1 for v in values if v < 70)
    high = sum(1 for v in values if v > 180)
    low_percent = (low / count) * 100 if count > 0 else 0
    high_percent = (high / count) * 100 if count > 0 else 0
    
    return {
        "period_hours": hours,
        "count": count,
        "average": round(avg, 1),
        "min": min_val,
        "max": max_val,
        "time_in_range_percent": round(time_in_range_percent, 1),
        "low_percent": round(low_percent, 1),
        "high_percent": round(high_percent, 1),
        "unit": "mg/dL"
    }