"""
Sanitized Structured Logging Middleware for Ghost Copilot.
Prevents leaking transcripts, passwords, tokens, or clipboard contents into logs.
"""

import time
import logging
import json
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("ghost_copilot.audit")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('{"time":"%(asctime)s", "level":"%(levelname)s", "event":%(message)s}')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


class SafeAuditLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Safe request metadata
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            logger.error(json.dumps({
                "type": "request_error",
                "method": method,
                "path": path,
                "client_ip": client_ip,
                "duration_ms": duration_ms,
                "error_type": type(e).__name__
            }))
            raise e

        duration_ms = round((time.time() - start_time) * 1000, 2)

        # Do not log health checks to reduce spam
        if path not in ("/health", "/ready", "/sharing_mode"):
            logger.info(json.dumps({
                "type": "http_request",
                "method": method,
                "path": path,
                "status": status_code,
                "client_ip": client_ip,
                "duration_ms": duration_ms
            }))

        return response
