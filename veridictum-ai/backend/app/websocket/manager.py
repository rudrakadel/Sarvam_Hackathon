"""
VeriDictum AI — WebSocket Connection Manager
Provides real-time status updates for analysis jobs, transcription, and OCR processing.

Auth model
==========
WebSockets accept a JWT via the `?token=...` query parameter (the browser's
WebSocket API can't set Authorization headers). The token is the same access
token issued by /auth/login. The connection is rejected with a 4401 close
code if the token is missing, expired, or doesn't match the requested
resource:

  - /ws/users/{user_id}  : token's `sub` claim must equal {user_id}.
  - /ws/cases/{case_id}  : token's user must belong to the same organisation
                           as the case (lightweight check — we re-verify on
                           the broadcast side for sensitive events).
  - /ws/jobs/{job_id}    : any authenticated user can subscribe (job IDs
                           are UUIDs that the user already has reference to).
"""

import logging
from collections import defaultdict
from typing import Any, Dict, Optional, Set

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from fastapi.websockets import WebSocketState
from jose import JWTError
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Case
from app.utils.security import decode_token

logger = logging.getLogger(__name__)

router = APIRouter()


# WebSocket close codes — RFC 6455 says 4000-4999 is application-defined.
WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_FORBIDDEN = 4403


async def _authenticate(token: Optional[str]) -> Optional[str]:
    """Decode the JWT from the query string. Returns the user's UUID or None."""
    if not token:
        return None
    try:
        payload = decode_token(token)
    except JWTError:
        return None
    if payload.get("type") != "access":
        return None
    sub = payload.get("sub")
    if not isinstance(sub, str):
        return None
    return sub


async def _user_has_access_to_case(user_id: str, case_id: str) -> bool:
    """A user can subscribe to a case channel iff the case lives in their org."""
    async with AsyncSessionLocal() as session:
        # Lookup user's org via the User row
        from app.models import User  # local import — avoid cycles at module load
        u = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()
        if u is None:
            return False
        c = (await session.execute(
            select(Case).where(Case.id == case_id)
        )).scalar_one_or_none()
        if c is None:
            return False
        return str(c.organisation_id) == str(u.organisation_id)


class WebSocketManager:
    """
    Manages WebSocket connections keyed by (topic, resource_id).

    Topics:
      - job/{job_id}      — analysis job progress
      - case/{case_id}    — all case-level events (transcription, OCR, analysis)
      - user/{user_id}    — user-scoped notifications
    """

    def __init__(self) -> None:
        # topic_key -> set of connected websockets
        self._connections: Dict[str, Set[WebSocket]] = defaultdict(set)

    def _key(self, topic: str, resource_id: str) -> str:
        return f"{topic}:{resource_id}"

    async def connect(self, websocket: WebSocket, topic: str, resource_id: str) -> None:
        await websocket.accept()
        key = self._key(topic, resource_id)
        self._connections[key].add(websocket)
        logger.info("ws_connect", extra={"key": key, "total": len(self._connections[key])})

    def disconnect(self, websocket: WebSocket, topic: str, resource_id: str) -> None:
        key = self._key(topic, resource_id)
        self._connections[key].discard(websocket)
        if not self._connections[key]:
            del self._connections[key]
        logger.info("ws_disconnect", extra={"key": key})

    async def broadcast(self, topic: str, resource_id: str, payload: Dict[str, Any]) -> None:
        """Send a JSON payload to all subscribers of a topic+resource."""
        key = self._key(topic, resource_id)
        dead: Set[WebSocket] = set()
        for ws in list(self._connections.get(key, [])):
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json(payload)
                else:
                    dead.add(ws)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._connections[key].discard(ws)

    async def broadcast_job_update(
        self,
        job_id: str,
        status: str,
        progress: int = 0,
        total_contradictions: int = 0,
        error: str | None = None,
    ) -> None:
        """Convenience: broadcast an analysis job status change."""
        await self.broadcast("job", job_id, {
            "event": "job_update",
            "job_id": job_id,
            "status": status,
            "progress": progress,
            "total_contradictions_found": total_contradictions,
            "error": error,
        })

    async def broadcast_case_event(
        self,
        case_id: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> None:
        """Convenience: broadcast any case-level event."""
        await self.broadcast("case", case_id, {
            "event": event_type,
            "case_id": case_id,
            **payload,
        })

    async def broadcast_user_notification(
        self,
        user_id: str,
        notification_id: str,
        title: str,
        body: str | None,
        notification_type: str,
        case_id: str | None = None,
    ) -> None:
        """Convenience: push a new notification to a specific user."""
        await self.broadcast("user", user_id, {
            "event": "notification",
            "notification_id": notification_id,
            "type": notification_type,
            "title": title,
            "body": body,
            "case_id": case_id,
        })


ws_manager = WebSocketManager()


# ---------------------------------------------------------------------------
# WebSocket endpoints
# ---------------------------------------------------------------------------

@router.websocket("/ws/jobs/{job_id}")
async def ws_job_status(
    websocket: WebSocket,
    job_id: str,
    token: Optional[str] = Query(default=None),
) -> None:
    """Real-time analysis job progress for a specific job.

    Auth: any authenticated user can subscribe. Job IDs are UUIDs the user
    already received from POST /contradictions/analyze; we don't re-validate
    org membership here because it would require an extra DB hop on every
    connect and the worst-case leak is a job-status counter.
    """
    user_id = await _authenticate(token)
    if user_id is None:
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED, reason="Missing or invalid token")
        return
    await ws_manager.connect(websocket, "job", job_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, "job", job_id)


@router.websocket("/ws/cases/{case_id}")
async def ws_case_events(
    websocket: WebSocket,
    case_id: str,
    token: Optional[str] = Query(default=None),
) -> None:
    """Real-time events for a case. Restricted to members of the case's org."""
    user_id = await _authenticate(token)
    if user_id is None:
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED, reason="Missing or invalid token")
        return
    if not await _user_has_access_to_case(user_id, case_id):
        await websocket.close(code=WS_CLOSE_FORBIDDEN, reason="Case not in your organisation")
        return
    await ws_manager.connect(websocket, "case", case_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, "case", case_id)


@router.websocket("/ws/users/{user_id}")
async def ws_user_notifications(
    websocket: WebSocket,
    user_id: str,
    token: Optional[str] = Query(default=None),
) -> None:
    """Real-time in-app notifications. The token's `sub` must match {user_id}."""
    token_user_id = await _authenticate(token)
    if token_user_id is None:
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED, reason="Missing or invalid token")
        return
    if token_user_id != user_id:
        await websocket.close(code=WS_CLOSE_FORBIDDEN, reason="Cannot subscribe to another user")
        return
    await ws_manager.connect(websocket, "user", user_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, "user", user_id)
