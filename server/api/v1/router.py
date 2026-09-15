"""
Central API v1 Router.
"""

from fastapi import APIRouter
from server.api.v1.endpoints.auth import router as auth_router
from server.api.v1.endpoints.sessions import router as sessions_router
from server.api.v1.endpoints.copilot import router as copilot_router
from server.api.v1.endpoints.features import router as features_router
from server.api.v1.endpoints.updates import router as updates_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(sessions_router)
api_v1_router.include_router(copilot_router)
api_v1_router.include_router(features_router)
api_v1_router.include_router(updates_router)
