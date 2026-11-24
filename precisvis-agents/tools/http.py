"""Petit client HTTP avec nouvelles tentatives (429 / 5xx / réseau)."""
from __future__ import annotations

import time
from typing import Any

import httpx


class ApiError(Exception):
    def __init__(self, service: str, status: int | None, message: str):
        super().__init__(f"{service} [{status}] {message}")
        self.service = service
        self.status = status


def request(service: str, method: str, url: str, *, retries: int = 3, timeout: float = 60.0, **kwargs: Any) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            resp = httpx.request(method, url, timeout=timeout, **kwargs)
        except httpx.HTTPError as exc:  # réseau
            last = exc
        else:
            if resp.status_code < 400:
                return resp
            if resp.status_code not in (408, 409, 429) and resp.status_code < 500:
                raise ApiError(service, resp.status_code, resp.text[:500])
            last = ApiError(service, resp.status_code, resp.text[:500])
        time.sleep(min(30, 2 ** attempt * 2))
    if isinstance(last, ApiError):
        raise last
    raise ApiError(service, None, str(last))
