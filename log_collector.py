import os
import requests
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
import logging
import logging.handlers

# Load environment variables
load_dotenv()
CLIENT_ID = os.getenv("CLIENT_ID")
PASSWORD = os.getenv("PASSWORD")
SYSLOG_SERVER_IP = os.getenv("SYSLOG_SERVER_IP")

# Debug: Print environment variables to check their values
print("CLIENT_ID:", CLIENT_ID)
print("PASSWORD:", PASSWORD)  # Be careful with printing passwords in real-world applications
print("SYSLOG_SERVER_IP:", SYSLOG_SERVER_IP)

BASE_URL = "https://fortiextender.forticloud.com"
AUTH_URL = f"{BASE_URL}/cloud/api/public/v1/oauth/token/init/"
REFRESH_URL = f"{BASE_URL}/cloud/api/public/v1/oauth/token/refresh/"
LOG_URL = f"{BASE_URL}/fext/api/public/v1/logging/fcld_event"
ACCESS_TOKEN = None
REFRESH_TOKEN = None
LAST_POLLED_TIMESTAMP = None

def authenticate():
    global ACCESS_TOKEN, REFRESH_TOKEN
    payload = {"api_user_id": CLIENT_ID, "password": PASSWORD}
    headers = {'Content-Type': 'application/json'}  # Explicit Content-Type header
    response = requests.post(AUTH_URL, json=payload, headers=headers)
    if response.status_code == 200:
        data = response.json()
        ACCESS_TOKEN, REFRESH_TOKEN = data["access_token"], data["refresh_token"]
    else:
        print(f"Authentication failed with status code: {response.status_code}, response: {response.text}")
        raise Exception("Authentication failed")


def refresh_token():
    global ACCESS_TOKEN, REFRESH_TOKEN
    payload = {"token": REFRESH_TOKEN}
    response = requests.post(REFRESH_URL, json=payload)
    if response.status_code == 200:
        data = response.json()
        ACCESS_TOKEN, REFRESH_TOKEN = data["access_token"], data["refresh_token"]
    else:
        raise Exception("Token refresh failed")

def poll_logs():
    global LAST_POLLED_TIMESTAMP
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    response = requests.get(LOG_URL, headers=headers)
    if response.status_code == 200:
        data = response.json()["payload"]["results"]
        for log_entry in data:
            # Convert log entry timestamp to datetime for comparison
            entry_timestamp = datetime.fromtimestamp(log_entry["timestamp"])
            if LAST_POLLED_TIMESTAMP is None or entry_timestamp > LAST_POLLED_TIMESTAMP:
                normalize_and_send_to_syslog(log_entry)
        if data:
            LAST_POLLED_TIMESTAMP = datetime.fromtimestamp(data[-1]["timestamp"])
    else:
        print("Failed to retrieve logs")

def setup_logger():
    # Create a logger
    logger = logging.getLogger('SyslogFileLogger')
    logger.setLevel(logging.INFO)

    # Prevent adding multiple handlers to the logger in subsequent calls
    if not logger.handlers:
        # Syslog handler setup
        syslog_handler = logging.handlers.SysLogHandler(address=(SYSLOG_SERVER_IP, 514))
        syslog_formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        syslog_handler.setFormatter(syslog_formatter)
        logger.addHandler(syslog_handler)

        # Rotating file handler setup
        file_handler = logging.handlers.RotatingFileHandler(
            'log_collector.log', maxBytes=5*1024*1024, backupCount=5)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger

def normalize_and_send_to_syslog(log_entry):
    # Ensure logger setup
    logger = setup_logger()

    # Construct syslog message including all KVPs
    # Use 'json.dumps' for the 'object' and 'sort' fields if they are not strings
    import json
    syslog_message_parts = []
    for key, value in log_entry.items():
        if isinstance(value, (list, dict)):
            value = json.dumps(value)  # Convert lists and dictionaries to a JSON string
        syslog_message_parts.append(f"{key}={value}")
    syslog_message = ' '.join(syslog_message_parts)

    # Send the log message
    logger.info(syslog_message)


def main():
    authenticate()
    while True:
        poll_logs()
        # Wait for 15 minutes before the next poll
        time.sleep(900)
        refresh_token()

if __name__ == "__main__":
    main()
