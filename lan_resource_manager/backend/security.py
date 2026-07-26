from __future__ import annotations

import ipaddress
import secrets
import time
import uuid
from collections import defaultdict, deque

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
        self.rate_limit = settings.mutation_rate_limit_per_minute
        self.mutations: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        request.state.request_id = f"lrm-{uuid.uuid4().hex[:20]}"
        client = request.client.host if request.client else ""
        try:
            address = ipaddress.ip_address(client)
        except ValueError:
            return JSONResponse({"detail": "network_not_allowed"}, status_code=403)
        if not any(address in network for network in self.networks):
            return JSONResponse({"detail": "network_not_allowed"}, status_code=403)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            now = time.monotonic()
            recent = self.mutations[client]
            while recent and recent[0] < now - 60:
                recent.popleft()
            if len(recent) >= self.rate_limit:
                return JSONResponse(
                    {"detail": "mutation_rate_limited"}, status_code=429
                )
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "json_required"}, status_code=415)
            if request.headers.get("origin") not in self.origins:
                return JSONResponse({"detail": "origin_not_allowed"}, status_code=403)
            if not secrets.compare_digest(
                request.headers.get("x-csrf-token", ""), self.csrf_token
            ):
                return JSONResponse({"detail": "csrf_failed"}, status_code=403)
            recent.append(now)
        response = await call_next(request)
        response.headers["x-request-id"] = request.state.request_id
        return response
