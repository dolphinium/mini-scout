import requests
import logging
import json
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple

from app.config import config

# Configure logging
logging.basicConfig(
    level=getattr(logging, config['log_level'], logging.INFO),
    format='[%(levelname)s][%(asctime)s]: %(message)s'
)
logger = logging.getLogger(__name__)

# Global state for auth
class LLUAuthState:
    auth_token: Optional[str] = None
    user_id: Optional[str] = None
    token_expires_at: Optional[datetime] = None

    @classmethod
    def is_token_valid(cls) -> bool:
        """Checks if the current auth token exists and hasn't expired."""
        if not cls.auth_token or not cls.token_expires_at:
            return False
        # Add a small buffer (e.g., 60 seconds) to be safe
        return datetime.now(timezone.utc) < (cls.token_expires_at - timedelta(seconds=60))
    
    @classmethod
    def clear_auth(cls) -> None:
        """Clear authentication data."""
        cls.auth_token = None
        cls.user_id = None
        cls.token_expires_at = None
    
    @classmethod
    def update_auth(cls, token: str, user_id: str, expires_at: Optional[datetime] = None) -> None:
        """Update authentication data."""
        cls.auth_token = token
        cls.user_id = user_id
        cls.token_expires_at = expires_at


def get_default_headers() -> Dict[str, str]:
    """Returns the default headers required for LLU API calls."""
    return {
        "User-Agent": config["user_agent"],
        "Content-Type": "application/json;charset=UTF-8",
        "version": config["llu_version"],
        "product": config["llu_product"],
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Accept": "application/json",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
    }


def get_authenticated_headers() -> Optional[Dict[str, str]]:
    """Returns headers required for authenticated LLU API calls."""
    if not LLUAuthState.auth_token or not LLUAuthState.user_id:
        logger.error("Cannot get authenticated headers: not logged in.")
        return None

    headers = get_default_headers()
    headers["Authorization"] = f"Bearer {LLUAuthState.auth_token}"
    
    # Add SHA-256 hashed account-id
    try:
        hashed_user_id = hashlib.sha256(LLUAuthState.user_id.encode()).hexdigest()
        headers["account-id"] = hashed_user_id
    except Exception as e:
        logger.error(f"Error hashing user ID: {e}")
        return None
    
    logger.debug(f"Authenticated Headers: {headers}")
    return headers


def login(session: Optional[requests.Session] = None) -> bool:
    """Logs into LibreLink Up and stores the auth token and user ID."""
    if session is None:
        session = requests.Session()
    
    url = f"{config['api_base_url']}/llu/auth/login"
    headers = get_default_headers()
    payload = {
        "email": config['username'],
        "password": config['password'],
    }

    try:
        logger.info("Attempting LibreLink Up login...")
        response = session.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        data = response.json()
        logger.debug(f"Login Response Raw Data: {json.dumps(data, indent=2)}")

        if data.get('status') != 0:
            logger.error(f"LibreLink Up Login - Non-zero status code: {json.dumps(data)}")
            # Check for region redirect suggestion
            if data.get('data', {}).get('redirect') is True and data.get('data', {}).get('region'):
                correct_region = data['data']['region'].upper()
                logger.error(f"LibreLink Up - Logged in to the wrong region. Your region might be '{correct_region}'. Update LINK_UP_REGION environment variable.")
            return False

        auth_ticket = data.get('data', {}).get('authTicket')
        user = data.get('data', {}).get('user')

        if not auth_ticket or not user or 'token' not in auth_ticket or 'id' not in user:
            logger.error("Login response missing expected data (authTicket/token or user/id).")
            return False

        token = auth_ticket['token']
        user_id = user['id']
        expires_timestamp = auth_ticket.get('expires', 0)  # Unix timestamp (seconds)
        duration = auth_ticket.get('duration', 0)  # Duration in seconds
        
        expires_at = None
        if expires_timestamp > 0:
            expires_at = datetime.fromtimestamp(expires_timestamp, tz=timezone.utc)
            logger.info(f"Login successful. Token expires at: {expires_at}")
        elif duration > 0:
            # Estimate expiry if 'expires' isn't present but 'duration' is
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=duration)
            logger.info(f"Login successful. Token duration: {duration}s. Estimated expiry: {expires_at}")
        else:
            logger.warning("Login successful, but token expiry time could not be determined.")

        # Update authentication state
        LLUAuthState.update_auth(token, user_id, expires_at)
        logger.info(f"Logged in to LibreLink Up. User ID: {user_id}")
        return True

    except requests.exceptions.RequestException as e:
        logger.error(f"Error during login request: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status code: {e.response.status_code}")
            logger.error(f"Response text: {e.response.text}")
        return False
    except json.JSONDecodeError:
        logger.error("Failed to decode JSON response from login.")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during login: {e}")
        return False


def get_connections(session: Optional[requests.Session] = None) -> Optional[List[Dict[str, Any]]]:
    """Fetches the list of available connections (patients)."""
    if session is None:
        session = requests.Session()
    
    # Ensure we have valid authentication
    if not LLUAuthState.is_token_valid():
        logger.warning("Auth token invalid or expired. Attempting login...")
        if not login(session):
            return None
    
    headers = get_authenticated_headers()
    if not headers:
        return None

    url = f"{config['api_base_url']}/llu/connections"

    try:
        logger.info("Fetching LibreLink Up connections...")
        response = session.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        logger.debug(f"Connections Response Raw Data: {json.dumps(data, indent=2)}")

        if data.get('status') != 0:
            logger.error(f"LibreLink Up Connections - Non-zero status code: {json.dumps(data)}")
            # Check for auth ticket renewal - the API often sends a new one
            new_ticket = data.get('ticket')
            if new_ticket and new_ticket.get('token'):
                logger.info("Received renewed auth ticket from connections endpoint.")
                expires_timestamp = new_ticket.get('expires', 0)
                expires_at = None
                if expires_timestamp > 0:
                    expires_at = datetime.fromtimestamp(expires_timestamp, tz=timezone.utc)
                    logger.info(f"Token expiry updated to: {expires_at}")
                
                LLUAuthState.update_auth(new_ticket['token'], LLUAuthState.user_id, expires_at)
            return None  # Indicate error despite potential token renewal

        connections_data = data.get('data')
        if not isinstance(connections_data, list):
            logger.error("Connections response 'data' field is not a list.")
            return None

        return connections_data

    except requests.exceptions.RequestException as e:
        logger.error(f"Error during get_connections request: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status code: {e.response.status_code}")
            logger.error(f"Response text: {e.response.text}")
        # If it's an auth error (like 401), invalidate the token
        if hasattr(e, 'response') and e.response is not None and e.response.status_code in [401, 403]:
            logger.warning("Authentication error fetching connections. Invalidating token.")
            LLUAuthState.clear_auth()
        return None
    except json.JSONDecodeError:
        logger.error("Failed to decode JSON response from connections.")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred fetching connections: {e}")
        return None


def select_connection(connections: List[Dict[str, Any]]) -> Optional[str]:
    """Selects the patient ID based on configuration or defaults."""
    if not connections:
        logger.error("No LibreLink Up connections found.")
        return None

    logger.info(f"Found {len(connections)} LibreLink Up connection(s):")
    for i, conn in enumerate(connections):
        logger.info(f"  [{i+1}] {conn.get('firstName', 'N/A')} {conn.get('lastName', 'N/A')} (Patient-ID: {conn.get('patientId', 'N/A')})")

    target_patient_id = config.get('connection_patient_id')

    if target_patient_id:
        for conn in connections:
            if conn.get('patientId') == target_patient_id:
                logger.info(f"Using specified connection: {conn.get('firstName')} {conn.get('lastName')} (Patient-ID: {target_patient_id})")
                return target_patient_id
        logger.error(f"Specified Patient-ID '{target_patient_id}' not found in the list of connections.")
        return None
    else:
        # Default to the first connection if none is specified
        selected_conn = connections[0]
        patient_id = selected_conn.get('patientId')
        logger.warning("LINK_UP_CONNECTION not specified. Using the first connection found.")
        logger.info(f"-> Using connection: {selected_conn.get('firstName')} {selected_conn.get('lastName')} (Patient-ID: {patient_id})")
        return patient_id


def get_glucose_data(session: Optional[requests.Session] = None, patient_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetches the glucose graph data for a specific patient ID.
    
    If patient_id is None, it will be automatically selected from available connections.
    """
    if session is None:
        session = requests.Session()
    
    # Ensure we have valid authentication
    if not LLUAuthState.is_token_valid():
        logger.warning("Auth token invalid or expired. Attempting login...")
        if not login(session):
            return None
    
    # Get patient ID if not provided
    if patient_id is None:
        connections = get_connections(session)
        if not connections:
            # Try login and get connections again
            if not login(session):
                logger.error("Login failed.")
                return None
            connections = get_connections(session)
            if not connections:
                logger.error("Still unable to get connections after login.")
                return None
        
        patient_id = select_connection(connections)
        if not patient_id:
            return None
    
    headers = get_authenticated_headers()
    if not headers:
        return None

    url = f"{config['api_base_url']}/llu/connections/{patient_id}/graph"

    try:
        logger.info(f"Fetching glucose data for Patient-ID: {patient_id}...")
        response = session.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        logger.debug(f"Graph Response Raw Data: {json.dumps(data, indent=2)}")

        if data.get('status') != 0:
            logger.error(f"LibreLink Up Graph Data - Non-zero status code: {json.dumps(data)}")
            # Check for auth ticket renewal
            new_ticket = data.get('ticket')
            if new_ticket and new_ticket.get('token'):
                logger.info("Received renewed auth ticket from graph endpoint.")
                expires_timestamp = new_ticket.get('expires', 0)
                expires_at = None
                if expires_timestamp > 0:
                    expires_at = datetime.fromtimestamp(expires_timestamp, tz=timezone.utc)
                    logger.info(f"Token expiry updated to: {expires_at}")
                
                LLUAuthState.update_auth(new_ticket['token'], LLUAuthState.user_id, expires_at)
            return None  # Indicate error despite potential token renewal

        graph_data = data.get('data')
        if not isinstance(graph_data, dict):
            logger.error("Graph response 'data' field is not a dictionary.")
            return None

        # Extract information
        latest_measurement = graph_data.get('connection', {}).get('glucoseMeasurement', {})
        history = graph_data.get('graphData', [])

        logger.info(f"Successfully fetched glucose data. Latest measurement value: {latest_measurement.get('ValueInMgPerDl')}. History points: {len(history)}")
        
        # Normalize data for MongoDB storage if needed
        normalized_data = {
            "timestamp": datetime.now(timezone.utc),
            "latest": latest_measurement,
            "history": history
        }
        
        return normalized_data

    except requests.exceptions.RequestException as e:
        logger.error(f"Error during get_glucose_data request: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status code: {e.response.status_code}")
            logger.error(f"Response text: {e.response.text}")
        # If it's an auth error (like 401), invalidate the token
        if hasattr(e, 'response') and e.response is not None and e.response.status_code in [401, 403]:
            logger.warning("Authentication error fetching glucose data. Invalidating token.")
            LLUAuthState.clear_auth()
        return None
    except json.JSONDecodeError:
        logger.error("Failed to decode JSON response from graph.")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred fetching glucose data: {e}")
        return None


# Function to fetch data with retry logic - for use in tasks
def fetch_glucose_data_with_retry(max_retries: int = 3) -> Optional[Dict[str, Any]]:
    """Fetch glucose data with retry logic for use in tasks."""
    session = requests.Session()
    
    for attempt in range(1, max_retries + 1):
        logger.info(f"Glucose data fetch attempt {attempt}/{max_retries}")
        
        # Try to get glucose data
        glucose_data = get_glucose_data(session)
        
        if glucose_data:
            return glucose_data
        
        # If failed and we have more attempts, try login again
        if attempt < max_retries:
            logger.warning(f"Fetch attempt {attempt} failed. Trying login again...")
            login(session)
    
    logger.error(f"Failed to fetch glucose data after {max_retries} attempts")
    return None