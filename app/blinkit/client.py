import asyncio
import logging
import random
import time
from typing import Any

from curl_cffi.requests import AsyncSession
from curl_cffi.requests.exceptions import RequestException

from app.blinkit import endpoints
from app.config import Settings

log = logging.getLogger(__name__)


class UpstreamError(Exception):
    """Blinkit returned something unusable (5xx, bad JSON, timeout)."""


class UpstreamBlocked(UpstreamError):
    """Blinkit's bot protection rejected us (403 / Cloudflare challenge)."""


class UpstreamNotFound(UpstreamError):
    pass


def _is_challenge(status: int, text: str) -> bool:
    if status in (403, 429, 503):
        return True
    head = text[:512].lower()
    return "just a moment" in head or "cf-chl" in head or "/careers/error-page" in text[:4096]


class BlinkitClient:
    """Async HTTP client for Blinkit's internal web API.

    Uses curl_cffi with browser TLS impersonation. On a block it drops the
    session (fresh cookies) and retries with backoff; if still blocked it
    raises UpstreamBlocked rather than escalating further.
    """

    def __init__(self, settings: Settings):
        self._s = settings
        self._session: AsyncSession | None = None
        self._lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(settings.max_concurrency)
        self.last_block_at: float | None = None
        self.last_success_at: float | None = None

    async def _get_session(self) -> AsyncSession:
        async with self._lock:
            if self._session is None:
                self._session = AsyncSession(
                    impersonate=self._s.impersonate, timeout=self._s.upstream_timeout
                )
            return self._session

    async def _reset_session(self) -> None:
        async with self._lock:
            if self._session is not None:
                await self._session.close()
            self._session = None

    async def close(self) -> None:
        await self._reset_session()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        lat: float | None = None,
        lon: float | None = None,
        params: dict[str, Any] | None = None,
        want_json: bool = True,
    ) -> Any:
        url = path if path.startswith("http") else self._s.base_url + path
        headers = endpoints.location_headers(lat, lon) if lat is not None and lon is not None else {}
        last_exc: Exception | None = None

        for attempt in range(self._s.max_retries + 1):
            if attempt:
                await asyncio.sleep(min(8.0, 0.5 * 2**attempt) + random.uniform(0, 0.5))
            session = await self._get_session()
            try:
                async with self._sem:
                    resp = await session.request(
                        method,
                        url,
                        headers=headers,
                        params=params,
                        json={} if method == "POST" else None,
                    )
            except RequestException as exc:
                last_exc = UpstreamError(f"network error: {exc}")
                continue

            text = resp.text
            if resp.status_code == 404:
                raise UpstreamNotFound(path)
            if _is_challenge(resp.status_code, text):
                self.last_block_at = time.time()
                log.warning(
                    "blinkit blocked request (status %s) on %s, resetting session", resp.status_code, path
                )
                last_exc = UpstreamBlocked(f"blocked with status {resp.status_code}")
                await self._reset_session()
                continue
            if resp.status_code >= 500:
                last_exc = UpstreamError(f"upstream status {resp.status_code}")
                continue
            if resp.status_code >= 400:
                raise UpstreamError(f"upstream status {resp.status_code}: {text[:200]}")

            self.last_success_at = time.time()
            if not want_json:
                return text
            try:
                return resp.json()
            except ValueError as exc:
                raise UpstreamError("upstream returned non-JSON body") from exc

        assert last_exc is not None
        raise last_exc

    async def post_layout(self, path: str, lat: float, lon: float) -> dict:
        data = await self._request("POST", path, lat=lat, lon=lon)
        if not isinstance(data, dict) or not data.get("is_success", False):
            raise UpstreamError(f"layout call unsuccessful: {path}")
        return data["response"]

    async def get_json(
        self, path: str, *, lat: float | None = None, lon: float | None = None, params: dict | None = None
    ) -> Any:
        return await self._request("GET", path, lat=lat, lon=lon, params=params)

    async def get_text(self, path: str) -> str:
        return await self._request("GET", path, want_json=False)
