from __future__ import annotations

from typing import Any, Callable

from .runpod_http import RunPodHttpClient, RunPodHttpError, safe_url as safe_url


class RunPodProdWorkerHttpError(RunPodHttpError):
    pass


class RunPodProdWorkerHttpClient(RunPodHttpClient):
    def __init__(
        self,
        *,
        error_type: type[Exception] = RunPodProdWorkerHttpError,
        urlopen_func: Callable[..., Any] | None = None,
    ) -> None:
        super().__init__(error_type=error_type, urlopen_func=urlopen_func)
