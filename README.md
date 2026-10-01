# Blinkit Products API

Unofficial REST API for [blinkit.com](https://blinkit.com) product data. Prices, stock and assortment depend on the dark store that serves the given location.

**Full API reference: [API.md](API.md)**

Built with FastAPI and [curl_cffi](https://github.com/lexiforest/curl_cffi). It calls the same JSON endpoints the Blinkit web app uses, parses their UI-layout responses into flat product records, and caches the results in memory.

> **Caveats:** This is an unofficial API and not affiliated with Blinkit. The upstream endpoints are undocumented and can change without notice. Keep request volume low and respect Blinkit's terms of service.

## Quick start

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/uvicorn app.main:app --reload
# interactive docs: http://localhost:8000/docs  (the base URL redirects here)
```

## Location

Every product and serviceability endpoint needs **exactly one** of:

| Params | Example |
|---|---|
| `lat` + `lon` | `lat=12.9352&lon=77.6245` |
| `pincode` | `pincode=560038` |
| `address` | `address=indiranagar bangalore` |

Pincodes and addresses are geocoded through Blinkit's own location service. The resolved coordinates come back in `meta.location`. If Blinkit doesn't deliver to the location, the API returns `424 location_not_serviceable`.

## Endpoints

| Method & path | Description |
|---|---|
| `GET /v1/products/search?q=…` | Keyword search |
| `GET /v1/products/{id}` | Full detail: images, category path, all attributes (ingredients, nutrition, shelf life…), similar products. `include_similar=false` drops the rails |
| `GET /v1/categories?depth=1\|2` | Category tree (L0 → L1), built from Blinkit's public sitemaps |
| `GET /v1/categories/{l0_id}` | One category with its subcategories |
| `GET /v1/categories/{l0_id}/products?l1_id=…` | Browse a category or subcategory |
| `GET /v1/location/suggest?query=…` | Address autocomplete with lat/lon (`resolve=false` skips coordinates). Optional `lat`/`lon` bias |
| `GET /v1/location/serviceability` | Whether Blinkit delivers here, delivery ETA and resolved address |
| `GET /health` | Upstream status and cache sizes |

### Listing parameters (search and category browse)

| Param | Description |
|---|---|
| `page`, `page_size` | 1-based page number and page size (1–100, default 24) |
| `sort` | `relevance` (Blinkit's order), `price_asc`, `price_desc`, `discount_desc`, `name_asc`, `rating_desc` |
| `min_price`, `max_price` | Selling price range in INR |
| `min_discount` | Minimum % off MRP |
| `min_rating` | 0–5 |
| `brand` | Repeatable, case-insensitive: `brand=amul&brand=nandini` |
| `in_stock` | `true` for only in-stock items, `false` for only sold-out items |
| `exclude_sponsored` | Drop ad placements |
| `fields` | Sparse output, e.g. `fields=name,price,unit` (`id` is always included) |
| `fresh` | Bypass the cache |

Blinkit returns 12–15 items per upstream page and has no usable server-side filters. The API therefore follows upstream pagination and filters and sorts locally:

- **With `sort=relevance` and no filters**, it fetches only as many upstream pages as the requested page needs.
- **With any filter or non-default sort**, it scans up to `BLINKIT_MAX_UPSTREAM_ITEMS` items (default 120). `meta.partial=true` means more upstream results existed beyond that cap.

### Example

```bash
curl 'localhost:8000/v1/products/search?q=milk&pincode=560038&brand=amul&in_stock=true&sort=price_asc&page_size=3&fields=name,unit,price'
```

```json
{
  "data": [
    {"id": "206314", "name": "Amul Lactose Free Milk", "unit": "250 ml",
     "price": {"selling": 26.0, "mrp": 26.0, "discount_pct": 0.0, "currency": "INR"}}
  ],
  "meta": {"page": 1, "page_size": 3, "returned": 3, "total_matched": 14, "upstream_total": 1214,
           "partial": true, "has_next": true, "merchant_id": "40076", "cached": false,
           "location": {"lat": 12.978, "lon": 77.641, "source": "pincode", "query": "560038"}, "...": "..."}
}
```

### Product fields

`id, name, brand, unit, price{selling, mrp, discount_pct, currency}, in_stock, inventory, image, rating{value, count}, product_type, merchant_id, merchant_type, group_id, is_sponsored, url`

The detail endpoint adds: `images, categories{l0,l1,l2}, breadcrumbs, description, attributes, similar`.

### Errors

Errors always have the shape `{"error": {"code", "message"}}`:

| Status | Code |
|---|---|
| 400 | `bad_request`, `location_not_resolved` |
| 404 | `not_found` |
| 422 | `validation_error` |
| 424 | `location_not_serviceable` |
| 502 | `upstream_error` |
| 503 | `upstream_blocked` (with `Retry-After`) |

## Configuration

Settings are read from environment variables prefixed `BLINKIT_` (or from `.env`). See `.env.example` for the full list. The main ones are cache TTLs, `MAX_CONCURRENCY` (limits upstream calls in flight) and `MAX_UPSTREAM_ITEMS`.

Cached listings are keyed by coordinates rounded to 3 decimals (about 110 m), so nearby callers share a cache entry.

## Layout

```
app/blinkit/endpoints.py   upstream URLs and headers; edit here when Blinkit changes something
app/blinkit/client.py      curl_cffi client: retries, session reset on block, concurrency limit
app/blinkit/parser.py      layout JSON → Product / ProductDetail
app/blinkit/categories.py  category tree from sitemaps
app/services/catalog.py    orchestration, progressive upstream pagination, caching
app/services/query.py      filters and sorting
app/api/                   FastAPI routes and dependencies
```

## Tests

```bash
.venv/bin/pytest            # offline, against recorded fixtures in tests/fixtures
.venv/bin/pytest -m live    # smoke tests against the real blinkit.com
```
