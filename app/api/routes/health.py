from datetime import UTC, datetime

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, UTC).isoformat() if ts else None


@router.get("/health")
async def health(request: Request):
    catalog = request.app.state.catalog
    client = catalog.client
    return {
        "status": "ok",
        "upstream": {
            "last_success_at": _iso(client.last_success_at),
            "last_block_at": _iso(client.last_block_at),
        },
        "cache": catalog.cache.stats(),
    }
