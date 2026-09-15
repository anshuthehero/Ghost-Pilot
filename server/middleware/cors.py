"""
Strict Exact-Match CORS Middleware for Ghost Copilot.
Rejects substring matches, wildcards, and attacker domains.
"""

from typing import List
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from server.config.settings import settings


class StrictCORSMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_origins: List[str] = None):
        super().__init__(app)
        self.allowed_origins = set(allowed_origins or settings.ALLOWED_ORIGINS)

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")

        # Handle Preflight OPTIONS requests
        if request.method == "OPTIONS" and origin:
            if origin in self.allowed_origins:
                response = Response(status_code=204)
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Access-Control-Max-Age"] = "86400"
                return response
            else:
                # Reject unauthorized origin preflight
                return Response(content="Forbidden: Cross-Origin Request Blocked", status_code=403)

        response = await call_next(request)

        # Attach CORS headers only if origin is explicitly allowed
        if origin:
            if origin in self.allowed_origins:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
            # If origin is untrusted, we DO NOT attach Access-Control-Allow-Origin header

        return response
