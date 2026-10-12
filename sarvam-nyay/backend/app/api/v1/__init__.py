"""VeriDictum AI — API v1 router registry."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.cases import router as cases_router
from app.api.v1.audio import router as audio_router
from app.api.v1.documents import router as documents_router
from app.api.v1.contradictions import router as contradictions_router
from app.api.v1.query import router as query_router
from app.api.v1.reports import router as reports_router
from app.api.v1.users import router as users_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.notifications import router as notifications_router

# Side-loaded Phase B+C endpoints — must import BEFORE include_router(cases_router)
# so the decorators register on cases_router before it's copied into api_router.
from app.api.v1 import _phase_bc_endpoints  # noqa: F401, E402

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(cases_router)
api_router.include_router(audio_router)
api_router.include_router(documents_router)
api_router.include_router(contradictions_router)
api_router.include_router(query_router)
api_router.include_router(reports_router)
api_router.include_router(dashboard_router)
api_router.include_router(notifications_router)
