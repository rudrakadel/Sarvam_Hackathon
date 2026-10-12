"""
VeriDictum AI — FastAPI Application Entry Point
Courtroom Transcript Intelligence & Contradiction Detector
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.config import settings
from app.middleware.idempotency import IdempotencyMiddleware
from app.websocket.manager import router as ws_router, ws_manager
from app.websocket.pubsub import redis_pubsub_listener

# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Lifespan — modern replacement for the deprecated @app.on_event handlers.
# Starts the Redis pub/sub listener on boot and cancels it on shutdown so
# the WebSocket fan-out keeps working but never leaks an orphan task.
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", environment=settings.APP_ENV, version="1.1.0")
    pubsub_task = asyncio.create_task(redis_pubsub_listener(ws_manager))
    try:
        yield
    finally:
        pubsub_task.cancel()
        try:
            await pubsub_task
        except (asyncio.CancelledError, Exception):
            pass
        log.info("shutdown")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.APP_NAME,
    description="Courtroom Transcript Intelligence & Contradiction Detector — Enterprise AI Platform",
    version="1.1.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-Process-Time"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"] if settings.DEBUG else ["sarvam.ai", "*.sarvam.ai", "localhost"],
)

# Idempotency-Key support for mutating endpoints. Backed by Redis; if Redis
# is unreachable the middleware fails-open (logs a warning, lets the request
# through) rather than blocking attorneys from creating reports.
app.add_middleware(
    IdempotencyMiddleware,
    redis_url=settings.REDIS_URL,
    ttl_seconds=settings.IDEMPOTENCY_TTL_SECONDS,
)


# Upload routes get the large limit; everything else gets MAX_JSON_BODY_BYTES.
# Keep this list in sync with backend/app/api/v1/audio.py and documents.py.
_UPLOAD_PATH_PREFIXES = (
    "/api/v1/cases/",  # any /audio or /documents POST under here
)


def _path_is_upload(path: str) -> bool:
    """Heuristic: only POSTs to /audio or /documents under a case path."""
    if not path.startswith("/api/v1/cases/"):
        return False
    return path.endswith("/audio") or path.endswith("/documents") or "/audio/" in path or "/documents/" in path


@app.middleware("http")
async def body_size_limit_middleware(request: Request, call_next):
    """Reject oversized requests before Pydantic touches them.

    Why this exists: an unauthenticated client can stream a 500 MB JSON payload
    at any POST endpoint and pin a worker until Starlette finishes buffering
    or OOMs. We reject early using the Content-Length header. Streamed
    requests without Content-Length still go through; rely on the proxy /
    ingress to enforce there.
    """
    # Only inspect methods that can carry a body.
    if request.method in ("POST", "PUT", "PATCH"):
        length_header = request.headers.get("content-length")
        if length_header is not None:
            try:
                length = int(length_header)
            except ValueError:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Invalid Content-Length header."},
                )

            path = request.url.path
            if _path_is_upload(path):
                # Upload routes: the bigger of audio/document caps applies.
                cap = max(settings.MAX_AUDIO_SIZE_BYTES, settings.MAX_DOCUMENT_SIZE_BYTES)
            else:
                cap = settings.MAX_JSON_BODY_BYTES

            if length > cap:
                log.warning(
                    "body_too_large",
                    path=path,
                    content_length=length,
                    cap=cap,
                )
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={
                        "detail": "Request body too large.",
                        "limit_bytes": cap,
                    },
                )

    return await call_next(request)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log every request with timing and request ID."""
    import uuid
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    start = time.monotonic()

    response = await call_next(request)

    elapsed = time.monotonic() - start
    log.info(
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round(elapsed * 1000, 2),
        request_id=request_id,
    )
    response.headers["X-Process-Time"] = f"{elapsed:.4f}"
    response.headers["X-Request-ID"] = request_id
    return response


_CSP_PROD = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "  # Tailwind ships inline styles; harmless
    "img-src 'self' data: blob: https:; "
    "font-src 'self' data:; "
    "connect-src 'self' https: wss: ws:; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "upgrade-insecure-requests"
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses (NFR-10, NFR-11).

    These headers are defence-in-depth — they don't replace input validation
    or auth, but they ensure that even if something slips through, the browser
    refuses to clickjack, render mixed content, or load arbitrary scripts.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    )
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        response.headers["Content-Security-Policy"] = _CSP_PROD
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-site"
    return response


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal error occurred. Please contact support."},
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc) -> JSONResponse:
    detail = exc.detail if hasattr(exc, "detail") else "Resource not found"
    return JSONResponse(status_code=404, content={"detail": detail})


@app.exception_handler(405)
async def method_not_allowed_handler(request: Request, exc) -> JSONResponse:
    detail = exc.detail if hasattr(exc, "detail") else "Method not allowed"
    return JSONResponse(status_code=405, content={"detail": detail})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
app.include_router(api_router)
app.include_router(ws_router)


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    """Liveness probe — must stay cheap (no DB, no Redis).

    Returns 200 as long as the Python process is alive and serving. Use
    /readiness for the deeper "can this instance actually take traffic" check.
    """
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": "1.1.0",
    }


@app.get("/readiness", tags=["Health"])
async def readiness_check() -> JSONResponse:
    """Readiness probe — verifies the dependencies a request actually needs.

    Probes:
      - PostgreSQL/SQLite (executes SELECT 1)
      - Redis (PING — only if a real REDIS_URL is configured)

    Returns:
      200 with each subsystem's status when all probes succeed.
      503 when any required dependency is unreachable, with per-subsystem
      diagnostics so a Kubernetes / load-balancer event makes the failure
      mode immediately obvious.
    """
    checks: dict[str, dict] = {}
    overall_ok = True

    # ── Database ────────────────────────────────────────────────────────────
    from sqlalchemy import text
    from app.database import AsyncSessionLocal

    db_start = time.monotonic()
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            value = result.scalar()
        if value != 1:
            raise RuntimeError(f"unexpected db response: {value!r}")
        checks["database"] = {
            "status": "ok",
            "duration_ms": round((time.monotonic() - db_start) * 1000, 2),
        }
    except Exception as exc:  # pragma: no cover — best-effort probe
        overall_ok = False
        checks["database"] = {
            "status": "fail",
            "error": str(exc)[:200],
            "duration_ms": round((time.monotonic() - db_start) * 1000, 2),
        }

    # ── Redis (optional in dev; required for Celery/WS in prod) ─────────────
    redis_url = getattr(settings, "REDIS_URL", "")
    if redis_url and redis_url.startswith("redis://"):
        redis_start = time.monotonic()
        try:
            import redis.asyncio as redis_asyncio  # local import — keep cold path cheap
            client = redis_asyncio.from_url(redis_url, socket_timeout=2.0)
            try:
                pong = await client.ping()
            finally:
                await client.aclose()
            if not pong:
                raise RuntimeError("ping returned falsy")
            checks["redis"] = {
                "status": "ok",
                "duration_ms": round((time.monotonic() - redis_start) * 1000, 2),
            }
        except Exception as exc:  # pragma: no cover
            # Redis being down is a hard failure in production (Celery dead,
            # WS fan-out dead, rate-limit broken). Mark not-ready.
            overall_ok = False
            checks["redis"] = {
                "status": "fail",
                "error": str(exc)[:200],
                "duration_ms": round((time.monotonic() - redis_start) * 1000, 2),
            }

    body = {
        "status": "ready" if overall_ok else "not_ready",
        "service": settings.APP_NAME,
        "version": "1.1.0",
        "checks": checks,
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK if overall_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=body,
    )


@app.get("/", include_in_schema=False)
async def root():
    return {"message": f"{settings.APP_NAME} API — use /docs for documentation."}


# Startup / shutdown are now handled by the `lifespan` context manager
# attached to the FastAPI() constructor above. Do not add @app.on_event
# handlers here — they're deprecated in FastAPI ≥0.93.
