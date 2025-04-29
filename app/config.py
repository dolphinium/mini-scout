import os
from dotenv import load_dotenv
from typing import Dict, Any

# Load environment variables from .env file
load_dotenv()

# LibreLink Up API Endpoints
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

# Constants
LIBRE_LINK_UP_VERSION = "4.12.0"
LIBRE_LINK_UP_PRODUCT = "llu.ios"
USER_AGENT = "Mozilla/5.0 (iPhone; CPU OS 17_4.1 like Mac OS X) AppleWebKit/536.26 (KHTML, like Gecko) Version/17.4.1 Mobile/10A5355d Safari/8536.25"

def get_config() -> Dict[str, Any]:
    """Get application configuration from environment variables."""
    # Get the region and check if it's valid
    region = os.getenv('LINK_UP_REGION', 'EU').upper()
    if region not in LLU_API_ENDPOINTS:
        raise ValueError(f"LINK_UP_REGION should be one of {list(LLU_API_ENDPOINTS.keys())}, but got {region}")
    
    # Get MongoDB URI
    mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/mini_nightscout')
    
    # Get Redis URL
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    return {
        "username": os.getenv('LINK_UP_USERNAME', ""),
        "password": os.getenv('LINK_UP_PASSWORD', ""),
        "region": region,
        "connection_patient_id": os.getenv('LINK_UP_CONNECTION'),  # Optional: Specific patient ID
        "log_level": os.getenv('LOG_LEVEL', 'INFO').upper(),
        "mongo_uri": mongo_uri,
        "redis_url": redis_url,
        "glucose_fetch_interval": int(os.getenv('GLUCOSE_FETCH_INTERVAL', '60')),  # In seconds
        "api_base_url": f"https://{LLU_API_ENDPOINTS[region]}",
        "llu_version": LIBRE_LINK_UP_VERSION,
        "llu_product": LIBRE_LINK_UP_PRODUCT,
        "user_agent": USER_AGENT,
    }

# Create a config dictionary
config = get_config()