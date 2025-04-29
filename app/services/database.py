import logging
import json
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


def parse_timestamp(timestamp_str: str) -> Optional[datetime]:
    """Parse timestamp string from various formats to datetime object.
    
    Args:
        timestamp_str: Timestamp string to parse
        
    Returns:
        datetime object or None if parsing fails
    """
    if not timestamp_str:
        return None
        
    # Try different formats
    formats = [
        # ISO format with Z
        lambda ts: datetime.fromisoformat(ts.replace('Z', '+00:00')),
        # US format MM/DD/YYYY HH:MM:SS AM/PM
        lambda ts: datetime.strptime(ts, '%m/%d/%Y %I:%M:%S %p'),
        # US format without seconds
        lambda ts: datetime.strptime(ts, '%m/%d/%Y %I:%M %p'),
        # EU format DD/MM/YYYY HH:MM:SS
        lambda ts: datetime.strptime(ts, '%d/%m/%Y %H:%M:%S'),
        # EU format without seconds
        lambda ts: datetime.strptime(ts, '%d/%m/%Y %H:%M'),
    ]
    
    for parse_func in formats:
        try:
            dt = parse_func(timestamp_str)
            # Ensure timezone awareness
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            continue
            
    logger.warning(f"Could not parse timestamp: {timestamp_str}")
    return None


def save_glucose_data(glucose_data: Dict[str, Any]) -> bool:
    """Save glucose data to MongoDB.
    
    Args:
        glucose_data: Dictionary containing 'latest' and 'history' fields
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Validate input data
        if not isinstance(glucose_data, dict):
            logger.error(f"Invalid glucose data type: {type(glucose_data)}")
            return False
            
        logger.info(f"Saving glucose data: {json.dumps(glucose_data, default=str)[:200]}...")
        
        # Get the collections
        latest_collection = get_collection('latest_readings')
        history_collection = get_collection('glucose_history')
        
        # Save latest reading
        latest_reading = glucose_data.get('latest', {})
        if latest_reading:
            logger.info(f"Processing latest reading: {json.dumps(latest_reading, default=str)}")
            
            # Add server timestamp
            latest_reading['serverTimestamp'] = datetime.now(timezone.utc)
            
            # Extract timestamp from the reading
            timestamp_str = latest_reading.get('Timestamp', '')
            if timestamp_str:
                parsed_timestamp = parse_timestamp(timestamp_str)
                if parsed_timestamp:
                    latest_reading['parsedTimestamp'] = parsed_timestamp
            
            # Insert or update latest reading
            result = latest_collection.replace_one(
                {'_id': 'latest'},  # Use a fixed ID for the latest reading
                {'_id': 'latest', 'data': latest_reading},
                upsert=True
            )
            
            logger.info(f"Saved latest reading: {latest_reading.get('ValueInMgPerDl')} mg/dL. " +
                      f"Modified: {result.modified_count}, Upserted: {result.upserted_id is not None}")
        
        # Save historical data
        history_points = glucose_data.get('history', [])
        if history_points:
            # Process and save each history point
            for point in history_points:
                # Parse timestamp
                timestamp_str = point.get('Timestamp', '')
                if not timestamp_str:
                    continue
                
                parsed_timestamp = parse_timestamp(timestamp_str)
                if parsed_timestamp:
                    point['parsedTimestamp'] = parsed_timestamp
                    
                    # Create a unique ID from timestamp
                    point_id = f"{parsed_timestamp.strftime('%Y%m%d%H%M%S')}"
                    
                    try:
                        # Save each point individually instead of bulk operation
                        history_collection.replace_one(
                            {'_id': point_id},
                            {'_id': point_id, 'data': point},
                            upsert=True
                        )
                    except PyMongoError as e:
                        logger.error(f"Error saving history point {point_id}: {e}")
            
            logger.info(f"Saved {len(history_points)} history points")
        
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