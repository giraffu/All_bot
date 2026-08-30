from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from .providers.runpod import redact_text


class RunPodHttpError(ValueError):
    pass


DEFAULT_USER_AGENT = "AllBot-RunPod-Operator/1"


def safe_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(parsed._replace(query="", fragment=""))


class RunPodHttpClient:
    def __init__(
        self,
        *,
        error_type: type[Exception] = RunPodHttpError,
        urlopen_func: Callable[..., Any] | None = None,
        transient_get_attempts: int = 1,
        sleep_func: Callable[[float], None] = time.sleep,
    ) -> None:
        self._error_type = error_type
        self._urlopen = urlopen_func or urllib.request.urlopen
        self._transient_get_attempts = max(1, int(transient_get_attempts))
        self._sleep = sleep_func

    def json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        expected_statuses: tuple[int, ...] = (200,),
        allow_statuses: tuple[int, ...] = (),
    ) -> dict[str, Any]:
        body = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        request_headers = dict(headers or {})
        if json_body is not None:
            request_headers["Content-Type"] = "application/json"
        response = self.request(
            method,
            url,
            params=params,
            body=body,
            headers=request_headers,
            expected_statuses=expected_statuses,
            allow_statuses=allow_statuses,
        )
        if not response["text"]:
            return {"_status": response["status"]}
        try:
            payload = json.loads(response["text"])
        except json.JSONDecodeError as exc:
            raise self._error(
                f"invalid JSON response from {method} {safe_url(url)}"
            ) from exc
        if isinstance(payload, dict):
            payload.setdefault("_status", response["status"])
            return payload
        return {"_status": response["status"], "data": payload}

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        expected_statuses: tuple[int, ...] = (200,),
        allow_statuses: tuple[int, ...] = (),
    ) -> dict[str, Any]:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
        request_headers = dict(headers or {})
        if not any(key.lower() == "user-agent" for key in request_headers):
            request_headers["User-Agent"] = DEFAULT_USER_AGENT
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers=request_headers,
        )
        attempts = self._transient_get_attempts if method.upper() == "GET" else 1
        for attempt in range(1, attempts + 1):
            try:
                with self._urlopen(request, timeout=30) as response:
                    status = int(response.status)
                    raw = response.read()
                    text = raw.decode("utf-8", errors="replace")
                break
            except urllib.error.HTTPError as exc:
                status = int(exc.code)
                raw = exc.read()
                text = raw.decode("utf-8", errors="replace")
                if status not in expected_statuses and status not in allow_statuses:
                    raise self._status_error(
                        f"{method} {safe_url(url)} returned HTTP {status}: "
                        f"{redact_text(text[:500])}",
                        status,
                    ) from exc
                break
            except (
                urllib.error.URLError,
                http.client.RemoteDisconnected,
                ConnectionResetError,
                TimeoutError,
            ) as exc:
                if attempt < attempts:
                    self._sleep(min(float(attempt), 2.0))
                    continue
                reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
                raise self._error(
                    f"{method} {safe_url(url)} network error: "
                    f"{redact_text(str(reason))}"
                ) from exc
        if status not in expected_statuses and status not in allow_statuses:
            raise self._status_error(
                f"{method} {safe_url(url)} returned HTTP {status}: "
                f"{redact_text(text[:500])}",
                status,
            )
        return {"status": status, "text": text, "raw": raw}

    def _error(self, message: str) -> Exception:
        return self._error_type(message)

    def _status_error(self, message: str, status: int) -> Exception:
        error = self._error(message)
        setattr(error, "http_status", status)
        return error
