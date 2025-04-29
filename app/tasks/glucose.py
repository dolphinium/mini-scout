"""
Celery tasks for fetching glucose data.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any

from celery import Task

from app.celery_app import celery_app
from app.services.librelinkup import llu_service
from app.services.database import db_service

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GlucoseTask(Task):
    """Base class for glucose-related tasks with error handling."""
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure by logging the error."""
        logger.error(f"Task {task_id} failed: {exc}")
        super().on_failure(exc, task_id, args, kwargs, einfo)


@celery_app.task(bind=True, base=GlucoseTask, max_retries=3, default_retry_delay=60)
def fetch_glucose_data(self) -> Dict[str, Any]:
    """
    Fetch glucose data from LibreLink Up and store in database.
    
    Returns:
        Dict: Summary of the operation results
    """
    try:
        logger.info("Starting task to fetch glucose data")
        task_start_time = datetime.utcnow()
        
        # Fetch data from LibreLink Up
        latest_reading, historical_readings = llu_service.fetch_and_process_data()
        
        if not latest_reading:
            logger.error("Failed to fetch valid glucose data")
            return {
                "success": False,
                "timestamp": datetime.utcnow().isoformat(),
                "error": "Failed to fetch glucose data",
                "inserted_count": 0
            }
        
        # Store latest reading
        latest_inserted = db_service.insert_entry(latest_reading)
        
        # Only process historical readings if we have them
        if historical_readings:
            historical_inserted = db_service.insert_entries(historical_readings)
        else:
            historical_inserted = 0
        
        # Prepare result
        total_inserted = (1 if latest_inserted else 0) + historical_inserted
        result = {
            "success": True,
            "timestamp": datetime.utcnow().isoformat(),
            "latest_reading": {
                "timestamp": latest_reading["device_timestamp"].isoformat(),
                "sgv": latest_reading["sgv"],
                "direction": latest_reading["direction"],
                "inserted": latest_inserted
            },
            "historical_count": len(historical_readings),
            "inserted_count": total_inserted,
            "execution_time_seconds": (datetime.utcnow() - task_start_time).total_seconds()
        }
        
        logger.info(f"Glucose data fetch completed: {total_inserted} new entries added")
        return result
        
    except Exception as e:
        logger.error(f"Error in fetch_glucose_data task: {e}")
        # Retry the task with exponential backoff
        retry_count = self.request.retries
        self.retry(exc=e, countdown=60 * (2 ** retry_count))
        
        return {
            "success": False,
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e),
            "retry_count": retry_count
        }