from __future__ import annotations

import ipaddress
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import Settings


class LocalSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings, csrf_token: str):
        super().__init__(app)
        self.networks = tuple(
            ipaddress.ip_network(value) for value in settings.allowed_networks
        )
        self.origins = set(settings.allowed_origins)
        self.csrf_token = csrf_token

    async def dispatch(self, request: Request, call_next):
        client = request.client.host if request.client else ""
        try:
            address = ipaddress.ip_address(client)
        except ValueError:
            return JSONResponse({"detail": "network_not_allowed"}, status_code=403)
        if not any(address in network for network in self.networks):
            return JSONResponse({"detail": "network_not_allowed"}, status_code=403)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "json_required"}, status_code=415)
            if request.headers.get("origin") not in self.origins:
                return JSONResponse({"detail": "origin_not_allowed"}, status_code=403)
            if not secrets.compare_digest(
                request.headers.get("x-csrf-token", ""), self.csrf_token
            ):
                return JSONResponse({"detail": "csrf_failed"}, status_code=403)
        return await call_next(request)
