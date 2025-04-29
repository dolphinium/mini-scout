"""
Configuration module for the mini_nightscout application.
Loads settings from environment variables.
"""

import os
from typing import Dict, Any

# Map regions to their API base URLs
LLU_API_ENDPOINTS = {
    "AE": "api-ae.libreview.io",
    "AP": "api-ap.libreview.io",
    "AU": "api-au.libreview.io",
    "CA": "api-ca.libreview.io",
    "DE": "api-de.libreview.io",
    "EU": "api-eu.libreview.io",
    "EU2": "api-eu2.libreview.io",
    "FR": "api-fr.libreview.io",
    "JP": "api-jp.libreview.io",
    "US": "api-us.libreview.io",
    "LA": "api-la.libreview.io",
    "RU": "api.libreview.ru",
    "CN": "api-cn.myfreestyle.cn"
}

# API constants
LIBRE_LINK_UP_VERSION = "4.12.0"
LIBRE_LINK_UP_PRODUCT = "llu.ios"
USER_AGENT = "Mozilla/5.0 (iPhone; CPU OS 17_4.1 like Mac OS X) AppleWebKit/536.26 (KHTML, like Gecko) Version/17.4.1 Mobile/10A5355d Safari/8536.25"


def get_config() -> Dict[str, Any]:
    """Load and validate application configuration from environment variables."""
    
    # Get LLU credentials
    username = os.getenv('LINK_UP_USERNAME')
    password = os.getenv('LINK_UP_PASSWORD')
    region = os.getenv('LINK_UP_REGION', 'EU').upper()
    
    # Validate region
    if region not in LLU_API_ENDPOINTS:
        valid_regions = ", ".join(LLU_API_ENDPOINTS.keys())
        raise ValueError(f"Invalid LINK_UP_REGION: {region}. Must be one of: {valid_regions}")
    
    # MongoDB configuration
    mongo_uri = os.getenv('MONGO_URI', 'mongodb://mongo:27017/')
    mongo_db = os.getenv('MONGO_DB', 'mini_nightscout')
    
    # Redis/Celery configuration
    redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
    
    # Fetch interval in seconds (default: 60 seconds)
    fetch_interval = int(os.getenv('FETCH_INTERVAL', '60'))
    
    # Optional: Specific connection patient ID
    connection_patient_id = os.getenv('LINK_UP_CONNECTION')
    
    return {
        "username": username,
        "password": password,
        "region": region,
        "connection_patient_id": connection_patient_id,
        "mongo_uri": mongo_uri,
        "mongo_db": mongo_db,
        "redis_url": redis_url,
        "fetch_interval": fetch_interval,
        "base_url": f"https://{LLU_API_ENDPOINTS[region]}",
        "default_headers": {
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json;charset=UTF-8",
            "version": LIBRE_LINK_UP_VERSION,
            "product": LIBRE_LINK_UP_PRODUCT,
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Accept": "application/json",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
        }
    }