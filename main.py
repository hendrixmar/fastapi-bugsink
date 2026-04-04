import logging
import os
from contextlib import asynccontextmanager

import sentry_sdk
from dotenv import load_dotenv
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

ENVIRONMENT = os.environ.get("ENVIRONMENT", "production")

if ENVIRONMENT != "production":
    load_dotenv()

# --- OpenTelemetry setup ---
OTEL_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://10.0.1.50:4318")
SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "fastapi-bugsink")
SERVICE_VERSION = os.environ.get("SERVICE_VERSION", "dev")

resource = Resource.create({
    "service.name": SERVICE_NAME,
    "service.version": SERVICE_VERSION,
    "deployment.environment": ENVIRONMENT,
})

provider = TracerProvider(resource=resource)
provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{OTEL_ENDPOINT}/v1/traces"))
)
trace.set_tracer_provider(provider)

LoggingInstrumentor().instrument(set_logging_format=True)
HTTPXClientInstrumentor().instrument()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Sentry/Bugsink setup ---
sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN", ""),
    integrations=[
        FastApiIntegration(),
        StarletteIntegration(),
    ],
    send_default_pii=False,
    traces_sample_rate=0,  # Bugsink does not support traces
    environment=ENVIRONMENT,
    release=SERVICE_VERSION,
)


# --- Graceful shutdown ---
@asynccontextmanager
async def lifespan(app):
    yield
    provider.shutdown()
    sentry_sdk.flush(timeout=5)


# --- FastAPI app ---
app = FastAPI(
    title="FastAPI Bugsink Demo",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if ENVIRONMENT == "production" else "/docs",
    redoc_url=None if ENVIRONMENT == "production" else "/redoc",
    openapi_url=None if ENVIRONMENT == "production" else "/openapi.json",
)
FastAPIInstrumentor.instrument_app(app)
tracer = trace.get_tracer(__name__)


@app.get("/")
def root():
    return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@app.get("/health")
def health():
    return {"healthy": True}


@app.get("/error")
def trigger_error():
    """Test endpoint - triggers an error that Bugsink will capture."""
    with tracer.start_as_current_span("trigger-error"):
        division_by_zero = 1 / 0  # noqa: F841
    return {"this": "will never return"}


@app.get("/message")
def capture_message():
    """Test endpoint - sends a test message to Bugsink."""
    with tracer.start_as_current_span("capture-message"):
        sentry_sdk.capture_message("Test message from FastAPI Bugsink demo")
        logger.info("Test message sent to Bugsink")
    return {"sent": True}
