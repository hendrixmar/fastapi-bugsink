import json
import logging
import os
import urllib.request

import sentry_sdk
from dotenv import load_dotenv
from fastapi import FastAPI
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

load_dotenv()

logger = logging.getLogger("fastapi-bugsink")


def _infisical_login(base_url: str, client_id: str, client_secret: str) -> str:
    """Authenticate with Infisical using Universal Auth (Machine Identity)."""
    data = json.dumps({"clientId": client_id, "clientSecret": client_secret}).encode()
    req = urllib.request.Request(
        f"{base_url}/api/v1/auth/universal-auth/login", data=data, method="POST"
    )
    req.add_header("Content-Type", "application/json")
    resp = urllib.request.urlopen(req, timeout=5)
    return json.loads(resp.read().decode())["accessToken"]


def load_infisical_secrets() -> dict[str, str]:
    """Fetch secrets from Infisical and inject them into os.environ.

    Supports two auth modes:
    - Machine Identity (recommended): set INFISICAL_CLIENT_ID + INFISICAL_CLIENT_SECRET
    - User JWT (legacy): set INFISICAL_TOKEN
    """
    infisical_url = os.environ.get("INFISICAL_URL", "http://10.0.1.42:8080")
    client_id = os.environ.get("INFISICAL_CLIENT_ID", "")
    client_secret = os.environ.get("INFISICAL_CLIENT_SECRET", "")
    infisical_token = os.environ.get("INFISICAL_TOKEN", "")
    workspace_id = os.environ.get(
        "INFISICAL_WORKSPACE_ID", "95e5961f-8e52-403c-b83b-479e5b422284"
    )
    environment = os.environ.get("INFISICAL_ENVIRONMENT", "dev")

    # Authenticate
    if client_id and client_secret:
        infisical_token = _infisical_login(infisical_url, client_id, client_secret)
    elif not infisical_token:
        logger.warning("No Infisical credentials set, skipping secret injection")
        return {}

    url = (
        f"{infisical_url}/api/v3/secrets/raw"
        f"?workspaceId={workspace_id}&environment={environment}&secretPath=/"
    )
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {infisical_token}")

    try:
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        secrets = {}
        for s in data.get("secrets", []):
            key = s["secretKey"]
            value = s["secretValue"]
            secrets[key] = value
            os.environ.setdefault(key, value)
        logger.info("Loaded %d secrets from Infisical", len(secrets))
        return secrets
    except Exception:
        logger.exception("Failed to load secrets from Infisical")
        return {}


# Load secrets from Infisical before reading config
load_infisical_secrets()

SENTRY_DSN = os.environ.get(
    "SENTRY_DSN",
    "http://ffc27113-eaca-40aa-b322-eef262b2e2f0@bugsink.artesanosdigitalescom.com.mx:8000/1",
)
ENVIRONMENT = os.environ.get("ENVIRONMENT", "production")

sentry_sdk.init(
    dsn=SENTRY_DSN,
    integrations=[
        FastApiIntegration(),
        StarletteIntegration(),
    ],
    send_default_pii=True,
    traces_sample_rate=0,  # Bugsink does not support traces
    environment=ENVIRONMENT,
)

app = FastAPI(title="FastAPI Bugsink Demo", version="1.0.0")


@app.get("/")
def root():
    return {"status": "ok", "service": "fastapi-bugsink"}


@app.get("/health")
def health():
    return {"healthy": True}


@app.get("/error")
def trigger_error():
    """Test endpoint - triggers an error that Bugsink will capture."""
    division_by_zero = 1 / 0  # noqa: F841
    return {"this": "will never return"}


@app.get("/message")
def capture_message():
    """Test endpoint - sends a test message to Bugsink."""
    sentry_sdk.capture_message("Test message from FastAPI Bugsink demo")
    return {"sent": True}
