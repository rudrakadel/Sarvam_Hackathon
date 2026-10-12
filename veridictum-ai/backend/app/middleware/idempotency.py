"""
Idempotency-Key middleware (RFC-style, Stripe-compatible).

Why this exists:

Mutating endpoints (`POST /reports`, `POST /audio`, `PATCH /contradictions/{id}/review`,
etc.) are not naturally idempotent. A flaky network connection can cause a
client retry to produce a duplicate report, a duplicate review action, or
a double-uploaded audio file. Stripe popularised the `Idempotency-Key`
header pattern: the client picks a UUID, sends it as a header, and the
server caches the (key → response) for some TTL so a retry replays the
original outcome.

How this implementation works:

1. The client sends `Idempotency-Key: <opaque-string>` on a `POST` / `PATCH` /
   `PUT` / `DELETE` request.
2. We hash the *user* + *method* + *path* + *key* into a Redis cache key so
   two different users cannot collide and so the same key against two
   different routes is treated as two requests.
3. If the cache key exists, we return the cached response body, status, and
   headers — the original request's outcome is replayed verbatim. The
   replay carries `Idempotency-Replayed: true` so the client knows.
4. If the cache key does not exist, the request runs as normal. On
   completion (any 2xx/3xx/4xx response — we don't cache 5xx because the
   original may not have finished server-side), we write the response into
   Redis with `IDEMPOTENCY_TTL_SECONDS` TTL.
5. A request *in flight* with the same key waits up to a short timeout for
   the original to finish, then replays the cached outcome. This is the
   "in-flight lock" — without it, two simultaneous retries both run.

Failure modes & safety:

- Redis unreachable → the middleware **skips** idempotency rather than
  fail-closed. We log a warning and let the request through. Locking down a
  mutating endpoint when Redis blips is a worse outcome than the rare
  duplicate.
- Body too large to cache → skipped (`IDEMPOTENCY_MAX_BODY_BYTES`).
- 5xx responses → not cached. The client should retry; doing so will run
  the handler again, which is the desired behaviour after a server error.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from typing import Awaitable, Callable

import redis.asyncio as redis_asyncio
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# Only these methods can use Idempotency-Key. GET/HEAD/OPTIONS are already
# idempotent by HTTP spec.
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Don't cache responses larger than this — Idempotency-Key is for control
# plane mutations, not file downloads.
IDEMPOTENCY_MAX_BODY_BYTES = 256 * 1024  # 256 KB


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Cache mutating-endpoint responses keyed by `Idempotency-Key` header."""

    def __init__(
        self,
        app: ASGIApp,
        redis_url: str,
        ttl_seconds: int,
        key_prefix: str = "veridictum:idem",
    ) -> None:
        super().__init__(app)
        self._redis_url = redis_url
        self._ttl = ttl_seconds
        self._prefix = key_prefix
        self._client: redis_asyncio.Redis | None = None

    async def _get_redis(self) -> redis_asyncio.Redis | None:
        """Lazy connect. Returns None if Redis is unreachable."""
        if self._client is not None:
            return self._client
        try:
            client = redis_asyncio.from_url(self._redis_url, socket_timeout=1.0)
            await client.ping()
            self._client = client
            return client
        except Exception as exc:
            logger.warning("idempotency_redis_unavailable", extra={"error": str(exc)[:200]})
            return None

    def _cache_key(self, request: Request, idem_key: str) -> str:
        """Compose a Redis key that includes the authenticated user when present."""
        # The user is set on request.state by app.api.deps after auth. The
        # auth header itself is good enough for unauthenticated routes.
        user_marker = ""
        user = getattr(request.state, "user_id", None)
        if user:
            user_marker = str(user)
        else:
            auth = request.headers.get("authorization", "")
            user_marker = hashlib.sha256(auth.encode()).hexdigest()[:16]
        payload = f"{user_marker}|{request.method}|{request.url.path}|{idem_key}"
        return f"{self._prefix}:{hashlib.sha256(payload.encode()).hexdigest()}"

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Bypass quickly for the cheap paths
        if request.method not in _MUTATING_METHODS:
            return await call_next(request)

        idem_key = request.headers.get("idempotency-key")
        if not idem_key:
            return await call_next(request)

        # Defensive validation: keys must be 1-255 printable ASCII chars.
        if not (1 <= len(idem_key) <= 255) or not idem_key.isascii() or not idem_key.isprintable():
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=400,
                content={"detail": "Idempotency-Key must be 1-255 printable ASCII characters."},
            )

        redis_client = await self._get_redis()
        if redis_client is None:
            # Fail-open: Redis is the cache, not the source of truth. Without
            # it we let the request through and accept the small duplicate
            # risk rather than blocking attorneys from creating reports.
            return await call_next(request)

        cache_key = self._cache_key(request, idem_key)

        # Try to acquire an in-flight lock so simultaneous retries serialize.
        lock_key = cache_key + ":lock"
        got_lock = await redis_client.set(lock_key, str(uuid.uuid4()), nx=True, ex=60)

        if not got_lock:
            # An earlier request with the same key is in flight. Poll briefly
            # for its outcome before falling back to running our own.
            for _ in range(20):  # 20 × 250ms = 5s budget
                cached_raw = await redis_client.get(cache_key)
                if cached_raw:
                    return self._replay(cached_raw)
                import asyncio
                await asyncio.sleep(0.25)
            # Lock-holder hasn't finished yet → fall through and run anyway.
            # Better to risk a duplicate than to deadlock the user.

        # If we already have a cached result, replay immediately.
        cached_raw = await redis_client.get(cache_key)
        if cached_raw:
            await redis_client.delete(lock_key)
            return self._replay(cached_raw)

        # No cache hit → run the actual handler.
        start = time.monotonic()
        try:
            response = await call_next(request)
        finally:
            # Release the lock before caching so a parallel retry can pick up
            # the cached result without contention.
            try:
                await redis_client.delete(lock_key)
            except Exception:
                pass

        # Only cache successful responses (2xx) and client errors (4xx).
        # 5xx may indicate the original mutation didn't complete server-side;
        # caching it would prevent a legitimate retry from healing.
        if 200 <= response.status_code < 500:
            try:
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk
                # Re-wrap so the downstream receives the full body.
                from starlette.responses import Response as StarletteResponse
                response = StarletteResponse(
                    content=body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )

                if len(body) <= IDEMPOTENCY_MAX_BODY_BYTES:
                    payload = json.dumps({
                        "status": response.status_code,
                        "headers": dict(response.headers),
                        "body_b64": body.hex(),
                    })
                    await redis_client.set(cache_key, payload, ex=self._ttl)
                    response.headers["Idempotency-Key"] = idem_key
                    response.headers["X-Idempotency-Cached"] = "miss"
                    response.headers["X-Idempotency-Duration-Ms"] = (
                        f"{(time.monotonic() - start) * 1000:.1f}"
                    )
            except Exception as exc:  # pragma: no cover — best-effort cache
                logger.warning("idempotency_cache_write_failed", extra={"error": str(exc)[:200]})

        return response

    @staticmethod
    def _replay(cached_raw: bytes) -> Response:
        from starlette.responses import Response as StarletteResponse
        payload = json.loads(cached_raw)
        body = bytes.fromhex(payload["body_b64"])
        headers = payload.get("headers", {})
        # Strip hop-by-hop headers that don't belong in a replay
        for h in ("content-length", "content-encoding", "transfer-encoding"):
            headers.pop(h, None)
            headers.pop(h.title(), None)
        resp = StarletteResponse(
            content=body,
            status_code=payload["status"],
            headers=headers,
        )
        resp.headers["X-Idempotency-Cached"] = "hit"
        resp.headers["Idempotency-Replayed"] = "true"
        return resp
