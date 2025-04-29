"""
MongoDB service module for interacting with the database.
Provides functions for storing and retrieving glucose data.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from app.config import get_config

# Get configuration
config = get_config()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MongoDBService:
    """Service for interacting with MongoDB to store and retrieve glucose readings."""
    
    def __init__(self):
        self.client: MongoClient = None
        self.db: Database = None
        self.entries_collection: Collection = None
        self.connect()
    
    def connect(self) -> None:
        """Establish connection to MongoDB."""
        try:
            self.client = MongoClient(config["mongo_uri"])
            self.db = self.client[config["mongo_db"]]
            self.entries_collection = self.db["entries"]
            
            # Create indexes for efficient queries
            self.entries_collection.create_index("device_timestamp", unique=True)
            self.entries_collection.create_index("timestamp")
            
            logger.info(f"Connected to MongoDB: {config['mongo_uri']}")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
    
    def insert_entry(self, entry: Dict[str, Any]) -> bool:
        """
        Insert a new glucose entry into the database.
        
        Args:
            entry: A dictionary containing glucose reading data
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check if entry already exists
            existing = self.entries_collection.find_one({
                "device_timestamp": entry["device_timestamp"]
            })
            
            if existing:
                logger.debug(f"Entry already exists for timestamp: {entry['device_timestamp']}")
                return False
            
            result = self.entries_collection.insert_one(entry)
            logger.debug(f"Inserted new entry with ID: {result.inserted_id}")
            return True
        except Exception as e:
            logger.error(f"Error inserting entry: {e}")
            return False
    
    def insert_entries(self, entries: List[Dict[str, Any]]) -> int:
        """
        Insert multiple glucose entries, skipping duplicates.
        
        Args:
            entries: List of entry dictionaries
            
        Returns:
            int: Number of entries successfully inserted
        """
        if not entries:
            return 0
            
        inserted_count = 0
        for entry in entries:
            if self.insert_entry(entry):
                inserted_count += 1
                
        logger.info(f"Inserted {inserted_count} new entries out of {len(entries)}")
        return inserted_count
    
    def get_latest_entry(self) -> Optional[Dict[str, Any]]:
        """
        Retrieve the most recent glucose entry.
        
        Returns:
            Dict or None: The most recent glucose entry or None if no entries exist
        """
        try:
            return self.entries_collection.find_one(
                sort=[("timestamp", -1)]  # Sort by timestamp descending
            )
        except Exception as e:
            logger.error(f"Error fetching latest entry: {e}")
            return None
    
    def get_latest_timestamp(self) -> Optional[datetime]:
        """
        Get the timestamp of the most recent entry.
        
        Returns:
            datetime or None: Timestamp of the most recent entry or None if no entries exist
        """
        latest = self.get_latest_entry()
        return latest.get("timestamp") if latest else None
    
    def get_entries_since(self, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Retrieve entries from the past specified hours.
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            List: Glucose entries within the specified timeframe
        """
        try:
            since = datetime.utcnow() - timedelta(hours=hours)
            cursor = self.entries_collection.find(
                {"timestamp": {"$gte": since}},
                sort=[("timestamp", 1)]  # Sort by timestamp ascending
            )
            return list(cursor)
        except Exception as e:
            logger.error(f"Error fetching entries for past {hours} hours: {e}")
            return []
    
    def close(self) -> None:
        """Close the database connection."""
        if self.client:
            self.client.close()
            logger.info("Closed MongoDB connection")


# Create a singleton instance
db_service = MongoDBService()