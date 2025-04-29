import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Union

from pymongo import MongoClient, DESCENDING
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.config import config

# Configure logging
logging.basicConfig(
    level=getattr(logging, config['log_level'], logging.INFO),
    format='[%(levelname)s][%(asctime)s]: %(message)s'
)
logger = logging.getLogger(__name__)

# MongoDB connection
_client: Optional[MongoClient] = None
_db: Optional[Database] = None


def get_database() -> Database:
    """Get the MongoDB database instance, creating connection if needed."""
    global _client, _db
    
    if _db is None:
        try:
            logger.info(f"Connecting to MongoDB: {config['mongo_uri']}")
            _client = MongoClient(config['mongo_uri'])
            # Extract database name from MongoDB URI
            db_name = config['mongo_uri'].split('/')[-1]
            if '?' in db_name:
                db_name = db_name.split('?')[0]
            _db = _client[db_name]
            logger.info(f"Connected to MongoDB database: {db_name}")
        except PyMongoError as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
    
    return _db


def get_collection(collection_name: str) -> Collection:
    """Get a MongoDB collection by name."""
    db = get_database()
    return db[collection_name]


def close_connection() -> None:
    """Close the MongoDB connection."""
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db = None
        logger.info("Closed MongoDB connection")


def save_glucose_data(glucose_data: Dict[str, Any]) -> bool:
    """Save glucose data to MongoDB.
    
    Args:
        glucose_data: Dictionary containing 'latest' and 'history' fields
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get the collections
        latest_collection = get_collection('latest_readings')
        history_collection = get_collection('glucose_history')
        
        # Save latest reading
        latest_reading = glucose_data.get('latest', {})
        if latest_reading:
            # Add server timestamp
            latest_reading['serverTimestamp'] = datetime.now(timezone.utc)
            
            # Extract timestamp from the reading
            timestamp_str = latest_reading.get('Timestamp', '')
            if timestamp_str:
                try:
                    # Parse timestamp - format may vary
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    latest_reading['parsedTimestamp'] = timestamp
                except ValueError:
                    logger.warning(f"Could not parse timestamp: {timestamp_str}")
            
            # Insert or update latest reading
            latest_collection.replace_one(
                {'_id': 'latest'},  # Use a fixed ID for the latest reading
                {'_id': 'latest', 'data': latest_reading},
                upsert=True
            )
            
            logger.info(f"Saved latest reading: {latest_reading.get('ValueInMgPerDl')} mg/dL")
        
        # Save historical data
        history_points = glucose_data.get('history', [])
        if history_points:
            # Process and save each history point
            bulk_ops = []
            for point in history_points:
                # Generate a unique ID using the timestamp
                timestamp_str = point.get('Timestamp', '')
                if not timestamp_str:
                    continue
                
                try:
                    # Parse timestamp
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    point['parsedTimestamp'] = timestamp
                    
                    # Create a unique ID from timestamp
                    point_id = f"{timestamp.strftime('%Y%m%d%H%M%S')}"
                    
                    # Add to bulk operations (upsert to avoid duplicates)
                    bulk_ops.append({
                        'replaceOne': {
                            'filter': {'_id': point_id},
                            'replacement': {'_id': point_id, 'data': point},
                            'upsert': True
                        }
                    })
                except ValueError:
                    logger.warning(f"Could not parse timestamp for history point: {timestamp_str}")
            
            # Execute bulk operation if there are any operations
            if bulk_ops:
                history_collection.bulk_write(bulk_ops)
                logger.info(f"Saved {len(bulk_ops)} history points")
        
        return True
    
    except PyMongoError as e:
        logger.error(f"MongoDB error while saving glucose data: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error while saving glucose data: {e}")
        return False


def get_latest_reading() -> Optional[Dict[str, Any]]:
    """Get the latest glucose reading from MongoDB."""
    try:
        latest_collection = get_collection('latest_readings')
        latest_doc = latest_collection.find_one({'_id': 'latest'})
        
        if latest_doc and 'data' in latest_doc:
            return latest_doc['data']
        return None
    
    except PyMongoError as e:
        logger.error(f"MongoDB error while getting latest reading: {e}")
        return None


def get_glucose_history(hours: int = 24) -> List[Dict[str, Any]]:
    """Get glucose history for the specified number of hours.
    
    Args:
        hours: Number of hours to look back
        
    Returns:
        List of glucose readings
    """
    try:
        # Calculate start time
        start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        history_collection = get_collection('glucose_history')
        
        # Query for records after start time
        cursor = history_collection.find(
            {"data.parsedTimestamp": {"$gte": start_time}}
        ).sort("data.parsedTimestamp", DESCENDING)
        
        # Extract the data field from each document
        result = [doc['data'] for doc in cursor]
        logger.info(f"Retrieved {len(result)} glucose history records for the past {hours} hours")
        
        return result
    
    except PyMongoError as e:
        logger.error(f"MongoDB error while getting glucose history: {e}")
        return []


def get_last_timestamp() -> Optional[datetime]:
    """Get the timestamp of the most recent glucose reading.
    
    Returns:
        datetime or None if no readings found
    """
    try:
        history_collection = get_collection('glucose_history')
        
        # Find the most recent record by parsedTimestamp
        latest_doc = history_collection.find_one(
            {"data.parsedTimestamp": {"$exists": True}},
            sort=[("data.parsedTimestamp", DESCENDING)]
        )
        
        if latest_doc and 'data' in latest_doc and 'parsedTimestamp' in latest_doc['data']:
            return latest_doc['data']['parsedTimestamp']
        
        return None
    
    except PyMongoError as e:
        logger.error(f"MongoDB error while getting last timestamp: {e}")
        return None