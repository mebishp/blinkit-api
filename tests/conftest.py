import json
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.blinkit.client import UpstreamNotFound
from app.config import Settings
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"

SERVICEABLE = (12.9352, 77.6245)
UNSERVICEABLE_LAT_MIN = 40  # anything north of this is "London" in the fake


def load_json(name: str):
    return json.loads((FIXTURES / name).read_text())


def load_text(name: str) -> str:
    return (FIXTURES / name).read_text()


EMPTY_PAGE = {"snippets": [], "pagination": {}}


class FakeBlinkitClient:
    """Serves recorded Blinkit responses; records every call."""

    def __init__(self):
        self.calls: Counter[str] = Counter()
        self.last_success_at = None
        self.last_block_at = None

    async def post_layout(self, path: str, lat: float, lon: float) -> dict:
        self.calls[path.split("?")[0]] += 1
        if path.startswith("/v1/layout/search"):
            if "offset=12" in path:
                return load_json("search_milk_delhi_p2.json")["response"]
            if "offset=" in path:
                return EMPTY_PAGE
            return load_json("search_milk_delhi.json")["response"]
        if path.startswith("/v1/layout/listing_widgets"):
            if "offset=" in path:
                return EMPTY_PAGE
            return load_json("listing_14_922.json")["response"]
        if path == "/v1/layout/product/793109":
            return load_json("product_pdp.json")["response"]
        raise UpstreamNotFound(path)

    async def get_json(self, path: str, *, lat=None, lon=None, params=None):
        self.calls[path] += 1
        params = params or {}
        if path == "/location/info":
            if float(params.get("lat", 0)) > UNSERVICEABLE_LAT_MIN:
                return {"is_serviceable": False, "coordinate": {"lat": 0, "lon": 0}}
            return load_json("location_info_koramangala.json")
        if path == "/v1/consumerweb/eta":
            return load_json("eta.json")
        if path == "/location/autoSuggest":
            return load_json("autosuggest_koramangala.json")
        raise UpstreamNotFound(path)

    async def get_text(self, path: str) -> str:
        self.calls[path] += 1
        return {
            "/sitemaps/categories.xml": load_text("sitemap_categories.xml"),
            "/sitemap.xml": load_text("sitemap_index.xml"),
        }[path]

    async def close(self):
        pass


@pytest.fixture
def fake_client() -> FakeBlinkitClient:
    return FakeBlinkitClient()


@pytest.fixture
def api(fake_client):
    app = create_app(Settings(max_upstream_items=60, _env_file=None), client=fake_client)
    with TestClient(app) as c:
        yield c
