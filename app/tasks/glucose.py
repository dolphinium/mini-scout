import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.celery_app import celery_app
from app.services import librelinkup, database
from app.config import config

# Configure logging
logging.basicConfig(
    level=getattr(logging, config['log_level'], logging.INFO),
    format='[%(levelname)s][%(asctime)s][%(name)s]: %(message)s'
)
logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def fetch_glucose_data(self) -> Optional[Dict[str, Any]]:
    """Celery task to fetch glucose data from LibreLink Up and save to MongoDB.
    
    This task:
    1. Fetches glucose data from LibreLink Up API
    2. Normalizes and processes the data
    3. Saves it to MongoDB
    
    Returns:
        Dictionary with metadata about the fetch operation
    """
    start_time = datetime.now(timezone.utc)
    logger.info(f"Starting glucose data fetch task at {start_time}")
    
    try:
        # Fetch glucose data from LibreLink Up
        glucose_data = librelinkup.fetch_glucose_data_with_retry()
        
        if not glucose_data:
            logger.error("Failed to fetch glucose data")
            # Retry the task
            self.retry(exc=Exception("Failed to fetch glucose data"))
            return None
        
        # Save data to MongoDB
        save_success = database.save_glucose_data(glucose_data)
        
        if not save_success:
            logger.error("Failed to save glucose data to MongoDB")
            # Retry the task
            self.retry(exc=Exception("Failed to save glucose data to MongoDB"))
            return None
        
        # Calculate task stats
        end_time = datetime.now(timezone.utc)
        execution_time = (end_time - start_time).total_seconds()
        
        # Get stats for return value
        latest_reading = glucose_data.get('latest', {})
        history_count = len(glucose_data.get('history', []))
        
        result = {
            'success': True,
            'timestamp': end_time,
            'execution_time_seconds': execution_time,
            'latest_value': latest_reading.get('ValueInMgPerDl'),
            'latest_trend': latest_reading.get('TrendArrow'),
            'history_count': history_count
        }
        
        logger.info(f"Glucose data fetch task completed successfully in {execution_time:.2f} seconds")
        logger.info(f"Latest glucose value: {result['latest_value']} mg/dL, Trend: {result['latest_trend']}")
        
        return result
    
    except Exception as e:
        logger.exception(f"Error in glucose data fetch task: {e}")
        # Retry the task
        self.retry(exc=e)
        return None