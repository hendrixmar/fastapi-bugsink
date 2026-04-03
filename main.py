import os

import sentry_sdk
from dotenv import load_dotenv
from fastapi import FastAPI
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

load_dotenv()

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN", ""),
    integrations=[
        FastApiIntegration(),
        StarletteIntegration(),
    ],
    send_default_pii=True,
    traces_sample_rate=0,  # Bugsink does not support traces
    environment=os.environ.get("ENVIRONMENT", "production"),
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
