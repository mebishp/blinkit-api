"""Smoke tests against the real blinkit.com. Run with: pytest -m live"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

pytestmark = pytest.mark.live

DELHI = "lat=28.6139&lon=77.2090"
BLR = "lat=12.9352&lon=77.6245"


@pytest.fixture(scope="module")
def live():
    with TestClient(create_app()) as c:
        yield c


def test_search_differs_by_location(live):
    a = live.get(f"/v1/products/search?q=amul taaza&{DELHI}&page_size=5").json()
    b = live.get(f"/v1/products/search?q=amul taaza&{BLR}&page_size=5").json()
    assert a["data"] and b["data"]
    assert a["meta"]["merchant_id"] != b["meta"]["merchant_id"]


def test_detail_and_categories(live):
    s = live.get(f"/v1/products/search?q=bread&{BLR}&page_size=1").json()
    pid = s["data"][0]["id"]
    d = live.get(f"/v1/products/{pid}?{BLR}")
    assert d.status_code == 200 and d.json()["data"]["images"]
    cats = live.get("/v1/categories").json()["data"]
    assert len(cats) > 10
