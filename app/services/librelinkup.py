"""
LibreLink Up API client service.
Handles authentication, connection management, and glucose data retrieval.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta  # Ensure timezone is imported
from typing import Dict, List, Optional, Any, Tuple

import requests

from app.config import get_config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get configuration
config = get_config()


class LibreLinkUpService:
    """Service for interacting with the LibreLink Up API."""

    def __init__(self):
        self.session = requests.Session()
        self.auth_token: Optional[str] = None
        self.user_id: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        self.patient_id: Optional[str] = None

    def get_authenticated_headers(self) -> Optional[Dict[str, str]]:
        """
        Returns headers required for authenticated LLU API calls.

        Returns:
            Dict or None: Headers with authentication or None if not logged in
        """
        if not self.auth_token or not self.user_id:
            logger.error("Cannot get authenticated headers: not logged in.")
            return None

        headers = config["default_headers"].copy()
        headers["Authorization"] = f"Bearer {self.auth_token}"

        # Add SHA-256 hashed account-id
        try:
            hashed_user_id = hashlib.sha256(self.user_id.encode()).hexdigest()
            headers["account-id"] = hashed_user_id
        except Exception as e:
            logger.error(f"Error hashing user ID: {e}")
            return None

        logger.debug(f"Authenticated Headers prepared")
        return headers

    def is_token_valid(self) -> bool:
        """
        Checks if the current auth token exists and hasn't expired.

        Returns:
            bool: True if token is valid, False otherwise
        """
        if not self.auth_token or not self.token_expires_at:
            return False
        # Add a small buffer (60 seconds) to be safe
        return datetime.now(timezone.utc) < (self.token_expires_at - timedelta(seconds=60))

    def login(self) -> bool:
        """
        Logs into LibreLink Up and stores the auth token and user ID.

        Returns:
            bool: True if login successful, False otherwise
        """
        url = f"{config['base_url']}/llu/auth/login"
        headers = config["default_headers"].copy()
        payload = {
            "email": config["username"],
            "password": config["password"],
        }

        try:
            logger.info("Attempting LibreLink Up login...")
            response = self.session.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            data = response.json()
            logger.debug(f"Login Response Data: {json.dumps(data, indent=2)}")

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

            self.auth_token = auth_ticket['token']
            self.user_id = user['id']
            expires_timestamp = auth_ticket.get('expires', 0)
            duration = auth_ticket.get('duration', 0)

            if expires_timestamp > 0:
                 # API provides POSIX timestamp (seconds since epoch), assume UTC
                 self.token_expires_at = datetime.fromtimestamp(expires_timestamp, tz=timezone.utc)
                 logger.info(f"Login successful. Token expires at: {self.token_expires_at}")
            elif duration > 0:
                 # Estimate expiry if 'expires' isn't present but 'duration' is
                 self.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=duration)
                 logger.info(f"Login successful. Token duration: {duration}s. Estimated expiry: {self.token_expires_at}")
            else:
                 self.token_expires_at = None
                 logger.warning("Login successful, but token expiry time could not be determined.")

            logger.info(f"Logged in to LibreLink Up. User ID: {self.user_id}")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Error during login request: {e}")
            if e.response is not None:
                logger.error(f"Response status code: {e.response.status_code}")
                logger.error(f"Response text: {e.response.text}")
            return False
        except json.JSONDecodeError:
            logger.error("Failed to decode JSON response from login.")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred during login: {e}")
            return False

    def get_connections(self) -> Optional[List[Dict[str, Any]]]:
        """
        Fetches the list of available connections (patients).

        Returns:
            List or None: List of connection dictionaries or None if error
        """
        headers = self.get_authenticated_headers()
        if not headers:
            return None

        url = f"{config['base_url']}/llu/connections"

        try:
            logger.info("Fetching LibreLink Up connections...")
            response = self.session.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            data = response.json()
            logger.debug(f"Connections Response Data: {json.dumps(data, indent=2)}")

            if data.get('status') != 0:
                 logger.error(f"LibreLink Up Connections - Non-zero status code: {json.dumps(data)}")
                 # Check for auth ticket renewal
                 new_ticket = data.get('ticket')
                 if new_ticket and new_ticket.get('token'):
                      logger.info("Received renewed auth ticket from connections endpoint.")
                      self.auth_token = new_ticket['token']
                      expires_timestamp = new_ticket.get('expires', 0)
                      if expires_timestamp > 0:
                        # API provides POSIX timestamp, assume UTC
                        self.token_expires_at = datetime.fromtimestamp(expires_timestamp, tz=timezone.utc)
                        logger.info(f"Token expiry updated to: {self.token_expires_at}")
                 return None

            connections_data = data.get('data')
            if not isinstance(connections_data, list):
                 logger.error("Connections response 'data' field is not a list.")
                 return None

            return connections_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Error during get_connections request: {e}")
            if e.response is not None:
                logger.error(f"Response status code: {e.response.status_code}")
                logger.error(f"Response text: {e.response.text}")
            # If it's an auth error (like 401), invalidate the token
            if e.response is not None and e.response.status_code in [401, 403]:
                logger.warning("Authentication error fetching connections. Invalidating token.")
                self.auth_token = None
                self.user_id = None
                self.token_expires_at = None
            return None
        except json.JSONDecodeError:
            logger.error("Failed to decode JSON response from connections.")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred fetching connections: {e}")
            return None

    def select_connection(self, connections: List[Dict[str, Any]]) -> Optional[str]:
        """
        Selects the patient ID based on configuration or defaults.

        Args:
            connections: List of connection dictionaries

        Returns:
            str or None: Selected patient ID or None if no valid connection
        """
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

    def get_glucose_data(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetches the glucose graph data for a specific patient ID.

        Args:
            patient_id: The patient ID to fetch data for

        Returns:
            Dict or None: Glucose data dictionary or None if error
        """
        headers = self.get_authenticated_headers()
        if not headers:
            return None

        url = f"{config['base_url']}/llu/connections/{patient_id}/graph"

        try:
            logger.info(f"Fetching glucose data for Patient-ID: {patient_id}...")
            response = self.session.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            data = response.json()
            logger.debug(f"Graph Response Data: {json.dumps(data, indent=2)}")

            if data.get('status') != 0:
                 logger.error(f"LibreLink Up Graph Data - Non-zero status code: {json.dumps(data)}")
                 # Check for auth ticket renewal
                 new_ticket = data.get('ticket')
                 if new_ticket and new_ticket.get('token'):
                      logger.info("Received renewed auth ticket from graph endpoint.")
                      self.auth_token = new_ticket['token']
                      expires_timestamp = new_ticket.get('expires', 0)
                      if expires_timestamp > 0:
                          # API provides POSIX timestamp, assume UTC
                          self.token_expires_at = datetime.fromtimestamp(expires_timestamp, tz=timezone.utc)
                          logger.info(f"Token expiry updated to: {self.token_expires_at}")
                 return None

            graph_data = data.get('data')
            if not isinstance(graph_data, dict):
                logger.error("Graph response 'data' field is not a dictionary.")
                return None

            # Extract basic info to log
            latest_measurement = graph_data.get('connection', {}).get('glucoseMeasurement', {})
            history = graph_data.get('graphData', [])

            logger.info(f"Successfully fetched glucose data. Latest measurement value: {latest_measurement.get('ValueInMgPerDl')}. History points: {len(history)}")
            return graph_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Error during get_glucose_data request: {e}")
            if e.response is not None:
                logger.error(f"Response status code: {e.response.status_code}")
                logger.error(f"Response text: {e.response.text}")
            # If it's an auth error, invalidate the token
            if e.response is not None and e.response.status_code in [401, 403]:
                logger.warning("Authentication error fetching glucose data. Invalidating token.")
                self.auth_token = None
                self.user_id = None
                self.token_expires_at = None
            return None
        except json.JSONDecodeError:
            logger.error("Failed to decode JSON response from graph.")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred fetching glucose data: {e}")
            return None

    def fetch_and_process_data(self) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Complete workflow to fetch glucose data:
        1. Login if needed
        2. Get connections
        3. Select a connection
        4. Fetch glucose data

        Returns:
            Tuple: (latest_reading, historical_readings) or (None, []) if error
        """
        # Check if we need to login
        if not self.is_token_valid():
            if not self.login():
                logger.error("Failed to login to LibreLink Up")
                return None, []

        # Get connections
        connections = self.get_connections()
        if not connections:
            # Try login again if connections failed
            logger.warning("Failed to get connections, attempting login again...")
            if not self.login():
                logger.error("Re-login failed.")
                return None, []
            connections = self.get_connections()
            if not connections:
                logger.error("Still unable to get connections after re-login.")
                return None, []

        # Select patient ID (use cached one if available)
        if not self.patient_id:
            self.patient_id = self.select_connection(connections)
            if not self.patient_id:
                logger.error("Failed to select a patient connection")
                return None, []

        # Get glucose data
        glucose_data = self.get_glucose_data(self.patient_id)
        if not glucose_data:
            # Try login again if glucose data failed
            logger.warning("Failed to retrieve glucose data. Attempting re-login...")
            if not self.login():
                logger.error("Re-login failed.")
                return None, []
            glucose_data = self.get_glucose_data(self.patient_id)
            if not glucose_data:
                logger.error("Still unable to retrieve glucose data after re-login.")
                return None, []

        # Process the data into the format we need
        try:
            latest_reading = self._process_latest_reading(glucose_data)
            historical_readings = self._process_historical_readings(glucose_data)
            return latest_reading, historical_readings
        except Exception as e:
            logger.error(f"Error processing glucose data: {e}")
            return None, []

    def _parse_llu_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """
        Parses the specific LLU timestamp format and returns a timezone-aware UTC datetime.

        Args:
            timestamp_str: The timestamp string from the LLU API.

        Returns:
            A timezone-aware datetime object (UTC) or None if parsing fails.
        """
        if not timestamp_str:
            return None
        try:
            # Format: Month/Day/Year Hour(12):Minute:Second AM/PM
            # Example: 4/29/2025 6:12:40 PM
            llu_format = "%m/%d/%Y %I:%M:%S %p"
            naive_dt = datetime.strptime(timestamp_str, llu_format)
            # Assume the timestamp from the API represents UTC time, make it timezone-aware
            aware_dt = naive_dt.replace(tzinfo=timezone.utc)
            return aware_dt
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to parse LLU timestamp '{timestamp_str}' with format '{llu_format}': {e}")
            # --- Fallback attempt: Try ISO format ---
            # Sometimes the API *might* return ISO format, although logs suggest otherwise
            try:
                # Remove 'Z' if present and add UTC offset for isoformat compatibility
                if timestamp_str.endswith('Z'):
                    timestamp_str = timestamp_str[:-1] + '+00:00'
                aware_dt = datetime.fromisoformat(timestamp_str)
                # Ensure it's UTC if parsed successfully
                if aware_dt.tzinfo is None:
                    aware_dt = aware_dt.replace(tzinfo=timezone.utc) # Should not happen with +00:00
                else:
                    aware_dt = aware_dt.astimezone(timezone.utc)
                logger.warning(f"Successfully parsed timestamp '{timestamp_str}' using ISO fallback.")
                return aware_dt
            except (ValueError, TypeError):
                # Log the final failure if ISO also fails
                logger.error(f"Could not parse timestamp '{timestamp_str}' using either LLU format or ISO format.")
                return None


    def _process_latest_reading(self, glucose_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process the latest glucose reading into a standardized format.

        Args:
            glucose_data: Raw glucose data from the API

        Returns:
            Dict: Processed latest reading or None if invalid
        """
        connection = glucose_data.get('connection', {})
        measurement = connection.get('glucoseMeasurement', {})
        if not measurement:
            logger.warning("Latest reading data ('glucoseMeasurement') is missing.")
            return None

        timestamp_str = measurement.get('Timestamp', '')
        device_timestamp = self._parse_llu_timestamp(timestamp_str)

        if device_timestamp is None:
            logger.error(f"Invalid timestamp format for latest reading: {timestamp_str}. Skipping latest reading.")
            # Fallback: use current time? Or just return None? Let's return None.
            return None

        # Use current UTC time as the record's own timestamp
        timestamp = datetime.now(timezone.utc)

        value = measurement.get('ValueInMgPerDl')
        trend = measurement.get('TrendArrow', '')

        # Validate essential data
        if value is None:
             logger.warning(f"Latest reading missing 'ValueInMgPerDl'. Skipping.")
             return None

        # Create standardized entry
        entry = {
            "device": "LibreLink Up",
            "device_timestamp": device_timestamp,
            "timestamp": timestamp, # When the record was created/processed
            "sgv": value,   # Sensor Glucose Value in mg/dL
            "direction": self._map_trend_arrow(trend),
            "type": "sgv",
            "glucose_units": "mg/dL",
            "raw_data": measurement # Store the original data for debugging/future use
        }

        return entry

    def _process_historical_readings(self, glucose_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Process historical glucose readings into standardized format.

        Args:
            glucose_data: Raw glucose data from the API

        Returns:
            List: Processed historical readings
        """
        results = []
        history = glucose_data.get('graphData', [])
        if not isinstance(history, list):
             logger.warning("Historical data ('graphData') is not a list or is missing.")
             return []

        current_time = datetime.now(timezone.utc) # Get current time once

        for point in history:
            # Skip points without a value or timestamp
            if 'Value' not in point or 'Timestamp' not in point:
                logger.debug(f"Skipping historical point missing Value or Timestamp: {point}")
                continue

            timestamp_str = point.get('Timestamp', '')
            device_timestamp = self._parse_llu_timestamp(timestamp_str)

            if device_timestamp is None:
                logger.warning(f"Skipping historical point due to invalid timestamp: {timestamp_str}")
                continue

            entry = {
                "device": "LibreLink Up",
                "device_timestamp": device_timestamp,
                "timestamp": current_time, # Use the same processing time for all historical points in this batch
                "sgv": point.get('Value'),
                "direction": "NONE",  # Historical points often don't have direction
                "type": "sgv",
                "glucose_units": "mg/dL",
                "raw_data": point # Store original data
            }

            results.append(entry)

        return results

    def _map_trend_arrow(self, trend: str) -> str:
        """
        Map LibreLink Up trend arrows to standard directional strings.

        Args:
            trend: LLU trend arrow string

        Returns:
            str: Standardized direction string
        """
        # Map LLU trend arrows to standard directions (adjust if needed based on exact API values)
        trend_map = {
            "Rising Quickly": "DoubleUp",
            "Rapidly Rising": "DoubleUp", # Add variations if observed
            "Rising": "SingleUp",
            "Rising Slowly": "FortyFiveUp",
            "Stable": "Flat",
            "Falling Slowly": "FortyFiveDown",
            "Falling": "SingleDown",
            "Falling Quickly": "DoubleDown",
            "Rapidly Falling": "DoubleDown", # Add variations if observed
            "": "NONE", # Handle empty string
            None: "NONE" # Handle None
        }

        # Perform case-insensitive lookup if necessary, default to NONE
        standard_trend = trend_map.get(trend, "NONE")
        logger.debug(f"Mapped trend '{trend}' to '{standard_trend}'")
        return standard_trend


# Create a singleton instance
llu_service = LibreLinkUpService()