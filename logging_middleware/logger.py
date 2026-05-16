import requests
import os
from datetime import datetime
from pathlib import Path

try:
    import importlib

    dotenv_module = importlib.import_module("dotenv")
    load_dotenv = dotenv_module.load_dotenv
except ImportError:
    def load_dotenv(dotenv_path=None):
        return False

project_root = Path(__file__).resolve().parents[1]
load_dotenv(str(project_root / ".env"))

# Configuration
LOG_ENDPOINT = "http://4.224.186.213/evaluation-service/logs"
BEARER_TOKEN = os.getenv("ACCESS_TOKEN", "").strip()
AUTH_HEADERS = {
    "Authorization": f"Bearer {BEARER_TOKEN}",
    "Content-Type": "application/json"
}

if not BEARER_TOKEN:
    raise ValueError(
        "ACCESS_TOKEN not found in environment. "
        "Please add it to .env file or set it as an environment variable."
    )

# Strict validation constraints
VALID_STACKS = {"backend"}
VALID_LEVELS = {"debug", "info", "warn", "error", "fatal"}
VALID_PACKAGES = {
    "cache", "controller", "cron_job", "db", "domain", "handler",
    "repository", "route", "service", "auth", "config", "middleware", "utils"
}


def Log(
    stack: str,
    level: str,
    package: str,
    message: str
) -> bool:
    """Send a structured log to the evaluation service."""

    if stack != stack.lower() or level != level.lower() or package != package.lower():
        raise ValueError("stack, level, and package must be lowercase")

    if stack not in VALID_STACKS:
        raise ValueError(f"Invalid stack '{stack}'. Must be: {VALID_STACKS}")
    
    if level not in VALID_LEVELS:
        raise ValueError(
            f"Invalid level '{level}'. Must be one of: {', '.join(sorted(VALID_LEVELS))}"
        )
    
    if package not in VALID_PACKAGES:
        raise ValueError(
            f"Invalid package '{package}'. Must be one of: {', '.join(sorted(VALID_PACKAGES))}"
        )
    
    if not message or not isinstance(message, str):
        raise ValueError("Message must be a non-empty string")

    payload = {
        "stack": stack,
        "level": level,
        "package": package,
        "message": message,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    try:
        headers = AUTH_HEADERS.copy()
        response = requests.post(LOG_ENDPOINT, json=payload, headers=headers, timeout=5)

        if response.status_code == 200:
            return True
        else:
            print(f"[LOGGER] Warning: Log endpoint returned {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"[LOGGER] Error sending log: {str(e)}")
        return False


if __name__ == "__main__":
    try:
        Log("backend", "info", "middleware", "Logger initialized successfully")
        Log("backend", "debug", "controller", "Test debug message")
        print("[SUCCESS] Logger module validated")
    except ValueError as e:
        print(f"[ERROR] {e}")