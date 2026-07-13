from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


DEFAULT_AUTH_COOKIE_NAME = "local_analytics_session"
PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 260_000


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def hash_password(password: str, *, salt: str | None = None, iterations: int = PASSWORD_HASH_ITERATIONS) -> str:
    resolved_salt = salt or secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        resolved_salt.encode("utf-8"),
        int(iterations),
    )
    return f"{PASSWORD_HASH_ALGORITHM}${int(iterations)}${resolved_salt}${_b64encode(digest)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected_digest = password_hash.split("$", 3)
        parsed_iterations = int(iterations)
    except ValueError:
        return False
    if algorithm != PASSWORD_HASH_ALGORITHM:
        return False
    candidate = hash_password(password, salt=salt, iterations=parsed_iterations).rsplit("$", 1)[-1]
    return hmac.compare_digest(candidate, expected_digest)


@dataclass(frozen=True)
class AuthConfig:
    enabled: bool
    username: str
    password: str
    password_hash: str
    session_secret: str
    cookie_name: str
    cookie_secure: bool
    session_ttl_seconds: int

    @classmethod
    def from_env(cls) -> "AuthConfig":
        try:
            session_ttl_seconds = int(os.getenv("LOCAL_ANALYTICS_AUTH_SESSION_TTL_SECONDS", "43200") or "43200")
        except ValueError:
            session_ttl_seconds = 43200
        return cls(
            enabled=_truthy(os.getenv("LOCAL_ANALYTICS_AUTH_ENABLED")),
            username=os.getenv("LOCAL_ANALYTICS_AUTH_USERNAME", "").strip(),
            password=os.getenv("LOCAL_ANALYTICS_AUTH_PASSWORD", ""),
            password_hash=os.getenv("LOCAL_ANALYTICS_AUTH_PASSWORD_HASH", "").strip(),
            session_secret=os.getenv("LOCAL_ANALYTICS_AUTH_SESSION_SECRET", ""),
            cookie_name=os.getenv("LOCAL_ANALYTICS_AUTH_COOKIE_NAME", DEFAULT_AUTH_COOKIE_NAME).strip()
            or DEFAULT_AUTH_COOKIE_NAME,
            cookie_secure=_truthy(os.getenv("LOCAL_ANALYTICS_AUTH_COOKIE_SECURE")),
            session_ttl_seconds=max(60, session_ttl_seconds),
        )

    @property
    def configured(self) -> bool:
        return bool(
            self.username
            and self.session_secret
            and (self.password_hash or self.password)
        )


def _sign(payload: str, secret: str) -> str:
    return _b64encode(hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest())


def create_session_token(config: AuthConfig, *, username: str) -> str:
    now = int(time.time())
    payload = _b64encode(
        json.dumps(
            {
                "sub": username,
                "iat": now,
                "exp": now + config.session_ttl_seconds,
                "nonce": secrets.token_urlsafe(12),
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    return f"{payload}.{_sign(payload, config.session_secret)}"


def read_session_token(config: AuthConfig, token: str | None) -> dict[str, Any] | None:
    if not token or "." not in token or not config.session_secret:
        return None
    payload, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, _sign(payload, config.session_secret)):
        return None
    try:
        data = json.loads(_b64decode(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if data.get("exp", 0) < int(time.time()):
        return None
    if data.get("sub") != config.username:
        return None
    return data


def verify_login(config: AuthConfig, *, username: str, password: str) -> bool:
    if not config.configured:
        return False
    if not hmac.compare_digest(username, config.username):
        return False
    if config.password_hash:
        return verify_password(password, config.password_hash)
    return hmac.compare_digest(password, config.password)


def _auth_required_response(request: Request) -> Response:
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "authentication required"}, status_code=401)
    target = request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(f"/login?next={quote(target, safe='')}", status_code=303)


class LocalAnalyticsAuthMiddleware(BaseHTTPMiddleware):
    PUBLIC_PATHS = {"/login", "/api/auth/login", "/api/auth/logout", "/api/auth/session"}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        config = AuthConfig.from_env()
        if not config.enabled:
            return await call_next(request)
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)
        if not config.configured:
            return JSONResponse({"detail": "local analytics auth is not configured"}, status_code=503)
        session = read_session_token(config, request.cookies.get(config.cookie_name))
        if session:
            return await call_next(request)
        return _auth_required_response(request)


def install_auth(app: FastAPI, *, static_dir: Path) -> None:
    app.add_middleware(LocalAnalyticsAuthMiddleware)

    @app.get("/login")
    async def login_page(request: Request) -> Response:
        config = AuthConfig.from_env()
        if not config.enabled:
            return RedirectResponse("/", status_code=303)
        session = read_session_token(config, request.cookies.get(config.cookie_name))
        if session:
            return RedirectResponse(request.query_params.get("next") or "/", status_code=303)
        return FileResponse(static_dir / "login.html")

    @app.get("/api/auth/session")
    async def auth_session(request: Request) -> dict[str, Any]:
        config = AuthConfig.from_env()
        session = read_session_token(config, request.cookies.get(config.cookie_name)) if config.enabled else None
        return {
            "auth_enabled": config.enabled,
            "authenticated": bool(session),
            "username": session.get("sub") if session else None,
        }

    @app.post("/api/auth/login")
    async def auth_login(request: Request) -> Response:
        config = AuthConfig.from_env()
        if not config.enabled:
            return JSONResponse({"authenticated": True, "username": None})
        if not config.configured:
            return JSONResponse({"detail": "local analytics auth is not configured"}, status_code=503)
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            body = (await request.body()).decode("utf-8")
            payload = {key: values[-1] for key, values in parse_qs(body).items()}
        username = str(payload.get("username", ""))
        password = str(payload.get("password", ""))
        if not verify_login(config, username=username, password=password):
            return JSONResponse({"detail": "invalid username or password"}, status_code=401)

        response = JSONResponse({"authenticated": True, "username": config.username})
        response.set_cookie(
            config.cookie_name,
            create_session_token(config, username=config.username),
            max_age=config.session_ttl_seconds,
            httponly=True,
            secure=config.cookie_secure,
            samesite="lax",
            path="/",
        )
        return response

    @app.post("/api/auth/logout")
    async def auth_logout() -> Response:
        config = AuthConfig.from_env()
        response = JSONResponse({"authenticated": False})
        response.delete_cookie(config.cookie_name, path="/")
        return response


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Local analytics auth helpers.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    hash_parser = subparsers.add_parser("hash-password", help="print a PBKDF2 password hash")
    hash_parser.add_argument("password")
    args = parser.parse_args()
    if args.command == "hash-password":
        print(hash_password(args.password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
