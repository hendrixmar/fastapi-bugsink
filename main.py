import json
import logging
import os
import uuid
from contextlib import asynccontextmanager

import sentry_sdk
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import (
    Counter,
    Histogram,
    generate_latest,
)
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


# --- Structured JSON logging ---
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "environment": ENVIRONMENT,
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "otelTraceID") and record.otelTraceID != "0":
            log_entry["trace_id"] = record.otelTraceID
            log_entry["span_id"] = record.otelSpanID
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        return json.dumps(log_entry)


handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.root.handlers = [handler]
logging.root.setLevel(logging.INFO)
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

# --- Prometheus metrics ---
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)


# --- Graceful shutdown ---
@asynccontextmanager
async def lifespan(app):
    logger.info("Service starting", extra={"event": "startup"})
    yield
    logger.info("Service shutting down", extra={"event": "shutdown"})
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


# --- Request ID + Metrics middleware ---
@app.middleware("http")
async def request_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id

    method = request.method
    path = request.url.path

    with REQUEST_LATENCY.labels(method=method, endpoint=path).time():
        response: Response = await call_next(request)

    REQUEST_COUNT.labels(method=method, endpoint=path, status=response.status_code).inc()
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/")
def root():
    return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@app.get("/health")
def health():
    return {"healthy": True}


@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type="text/plain; charset=utf-8")


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
