LOC = "lat=12.9352&lon=77.6245"


def test_search_basic(api, fake_client):
    r = api.get(f"/v1/products/search?q=milk&{LOC}&page_size=5")
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 5
    meta = body["meta"]
    assert meta["has_next"] and not meta["partial"] and not meta["cached"]
    assert meta["upstream_total"] == 38
    assert meta["location"]["source"] == "lat_lon"
    assert meta["merchant_id"] == "36778"
    # page 1 of 5 needs only the first upstream page
    assert fake_client.calls["/v1/layout/search"] == 1


def test_search_second_page_follows_upstream_pagination_and_caches(api, fake_client):
    api.get(f"/v1/products/search?q=milk&{LOC}&page_size=5")
    r = api.get(f"/v1/products/search?q=Milk&{LOC}&page=3&page_size=5")  # needs items 10..15
    assert r.status_code == 200
    assert len(r.json()["data"]) == 5
    assert fake_client.calls["/v1/layout/search"] == 2  # one extra upstream page, not a refetch

    r = api.get(f"/v1/products/search?q=milk&{LOC}&page=2&page_size=5")
    assert r.json()["meta"]["cached"] is True
    assert fake_client.calls["/v1/layout/search"] == 2


def test_search_filters_sort_and_fields(api):
    r = api.get(
        f"/v1/products/search?q=milk&{LOC}&sort=price_asc&in_stock=true&page_size=50&fields=name,price"
    )
    body = r.json()
    prices = [p["price"]["selling"] for p in body["data"]]
    assert prices == sorted(prices)
    assert set(body["data"][0]) == {"id", "name", "price"}
    assert body["meta"]["partial"] is False  # fake upstream got exhausted under the cap
    assert body["meta"]["total_matched"] == len(body["data"])


def test_search_brand_filter(api):
    r = api.get(f"/v1/products/search?q=milk&{LOC}&brand=country delight&brand=AMUL&page_size=100")
    brands = {p["brand"].lower() for p in r.json()["data"]}
    assert brands and brands <= {"country delight", "amul"}


def test_location_validation(api):
    assert api.get("/v1/products/search?q=milk").status_code == 400
    assert api.get("/v1/products/search?q=milk&lat=12.9").status_code == 400
    assert api.get(f"/v1/products/search?q=milk&{LOC}&pincode=560034").status_code == 400
    r = api.get("/v1/products/search?q=milk&pincode=12345")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = api.get("/v1/products/search?q=milk&lat=51.5&lon=-0.12")
    assert r.status_code == 424 and r.json()["error"]["code"] == "location_not_serviceable"


def test_bad_params(api):
    assert api.get(f"/v1/products/search?q=milk&{LOC}&min_price=50&max_price=10").status_code == 400
    assert api.get(f"/v1/products/search?q=milk&{LOC}&sort=cheapest").status_code == 422
    assert api.get(f"/v1/products/search?q=milk&{LOC}&fields=name,bogus").status_code == 400


def test_address_location_is_geocoded(api):
    r = api.get("/v1/products/search?q=milk&address=koramangala&page_size=1")
    assert r.status_code == 200
    loc = r.json()["meta"]["location"]
    assert loc["source"] == "address" and loc["query"] == "koramangala"
    assert round(loc["lat"], 2) == 12.94


def test_product_detail(api):
    r = api.get(f"/v1/products/793109?{LOC}")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["price"]["mrp"] == 129 and d["attributes"]["Shelf Life"] == "90 days"
    assert d["similar"]
    r = api.get(f"/v1/products/793109?{LOC}&include_similar=false")
    assert r.json()["data"]["similar"] == [] and r.json()["meta"]["cached"] is True

    r = api.get(f"/v1/products/1?{LOC}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_categories(api, fake_client):
    r = api.get("/v1/categories?depth=1")
    assert r.status_code == 200
    assert all(c["subcategories"] == [] for c in r.json()["data"])
    r = api.get("/v1/categories/14")
    assert any(s["id"] == 922 for s in r.json()["data"]["subcategories"])
    assert fake_client.calls["/sitemaps/categories.xml"] == 1  # cached
    assert api.get("/v1/categories/999999").status_code == 404


def test_browse_category(api):
    r = api.get(f"/v1/categories/14/products?l1_id=922&{LOC}&page_size=10")
    assert r.status_code == 200
    assert len(r.json()["data"]) == 10
    assert r.json()["meta"]["upstream_total"] == 88


def test_location_endpoints(api):
    r = api.get("/v1/location/suggest?query=koramangala")
    s = r.json()
    assert s[0]["title"] == "Koramangala" and s[0]["lat"] is not None

    r = api.get(f"/v1/location/serviceability?{LOC}")
    d = r.json()["data"]
    assert d["serviceable"] and d["eta_minutes"] == 11 and d["city"] == "Bengaluru"


def test_health(api):
    r = api.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_root_redirects_to_docs(api):
    r = api.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/docs"
