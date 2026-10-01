# Blinkit Products API — Reference

Base URL (local): `http://localhost:8000` · `/` redirects to `/docs` · Interactive docs: `/docs` (Swagger) and `/redoc` · OpenAPI schema: `/openapi.json`

All endpoints are `GET` and return JSON. No authentication.

> **Unofficial.** Not affiliated with Blinkit. Data is fetched live from Blinkit's internal web API, so availability and shape can change without notice. Keep request volume low.

## Contents

- [Concepts](#concepts)
  - [Location](#location)
  - [Response envelopes](#response-envelopes)
  - [Pagination, filtering and `partial`](#pagination-filtering-and-partial)
  - [Caching](#caching)
- [Endpoints](#endpoints)
  - [Search products](#get-v1productssearch)
  - [Product detail](#get-v1productsproduct_id)
  - [List categories](#get-v1categories)
  - [Get one category](#get-v1categoriesl0_id)
  - [Browse a category](#get-v1categoriesl0_idproducts)
  - [Location suggest](#get-v1locationsuggest)
  - [Serviceability](#get-v1locationserviceability)
  - [Health](#get-health)
- [Data models](#data-models)
- [Errors](#errors)
- [Recipes](#recipes)
- [Configuration](#configuration)

---

## Concepts

### Location

Prices, stock and assortment come from the dark store that serves a location, so every product endpoint needs one. Provide **exactly one** of:

| Form | Params | Notes |
|---|---|---|
| Coordinates | `lat`, `lon` | Both required together. `lat` in −90..90, `lon` in −180..180 |
| PIN code | `pincode` | 6 digits, e.g. `560038` |
| Free text | `address` | 3–200 chars, e.g. `indiranagar bangalore` |

`pincode` and `address` are resolved to coordinates through Blinkit's own geocoder. The resolved point is echoed in `meta.location` (`source` is `lat_lon`, `pincode` or `address`).

- Zero or more than one location form → `400 bad_request`.
- A location Blinkit doesn't deliver to → `424 location_not_serviceable`.
- A pincode/address that can't be geocoded → `400 location_not_resolved`.

### Response envelopes

Lists of products use a **page envelope**:

```json
{ "data": [ /* Product… */ ], "meta": { /* PageMeta */ } }
```

Single objects use an **item envelope**:

```json
{ "data": { /* object */ }, "meta": { "location": { }, "cached": false, "fetched_at": "2026-09-29T07:15:15Z" } }
```

`/v1/location/suggest` returns a bare JSON array. Errors always use the [error shape](#errors).

### Pagination, filtering and `partial`

Blinkit returns 12–15 items per upstream page and offers no usable server-side filters, so this API follows upstream pagination and applies filters and sorting itself.

| Request | Upstream work | `meta.partial` |
|---|---|---|
| `sort=relevance`, no filters | Fetches only as many upstream pages as `page`×`page_size` needs | always `false` |
| Any filter, or any other `sort` | Scans up to `BLINKIT_MAX_UPSTREAM_ITEMS` items (default 120), then filters, sorts and pages | `true` if Blinkit had more results than were scanned |

When `partial` is `true`, filters and sorting cover only the scanned items. `meta.upstream_total` is Blinkit's own total for the query, so compare it with what you need.

`meta.total_matched` counts items matching your filters **among those scanned**, not the whole catalogue.

### Caching

Results are cached in memory, keyed by request and location rounded to 3 decimals (~110 m), so nearby callers share entries.

| Data | TTL |
|---|---|
| Search / browse listings | 5 min |
| Product detail | 5 min |
| Serviceability | 10 min |
| Category tree | 6 h |
| Geocoding / suggestions | 24 h |

`meta.cached` says whether the response came from cache and `meta.fetched_at` when it was fetched. Add `fresh=true` to bypass the cache. Concurrent identical requests share one upstream call.

---

## Endpoints

### `GET /v1/products/search`

Keyword search at a location.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `q` | string (1–100) | **required** | Search text |
| location | see [Location](#location) | **required** | `lat`+`lon`, `pincode`, or `address` |
| `page` | int 1–100 | `1` | Page number |
| `page_size` | int 1–100 | `24` | Items per page |
| `sort` | enum | `relevance` | `relevance`, `price_asc`, `price_desc`, `discount_desc`, `name_asc`, `rating_desc` |
| `min_price` | number ≥ 0 | – | Minimum selling price (INR) |
| `max_price` | number ≥ 0 | – | Maximum selling price (INR). Must be ≥ `min_price` |
| `min_discount` | number 0–100 | – | Minimum % off MRP |
| `min_rating` | number 0–5 | – | Minimum rating value. Items with no rating are excluded |
| `brand` | string, repeatable | – | Case-insensitive exact brand match. `brand=amul&brand=nandini` matches either |
| `in_stock` | bool | – | `true` = only in stock, `false` = only sold out |
| `exclude_sponsored` | bool | `false` | Drop ad placements |
| `fields` | comma list | all | Sparse output, e.g. `name,price,unit`. `id` is always included. Unknown names → `400` |
| `fresh` | bool | `false` | Bypass cache |

**Sorting notes:** ties keep Blinkit's relevance order. Items without a price sort last for `price_asc`.

**Example**

```bash
curl 'http://localhost:8000/v1/products/search?q=milk&lat=12.9352&lon=77.6245&sort=price_asc&in_stock=true&brand=amul&page_size=2'
```

```json
{
  "data": [
    {
      "id": "206314",
      "name": "Amul Lactose Free Milk",
      "brand": "Amul",
      "unit": "250 ml",
      "price": { "selling": 26.0, "mrp": 26.0, "discount_pct": 0.0, "currency": "INR" },
      "in_stock": true,
      "inventory": 50,
      "image": "https://cdn.grofers.com/da/cms-assets/cms/product/87c1c525-750e-475f-91d1-f155026ddaa1.png",
      "rating": { "value": 4.6, "count": "91,060" },
      "product_type": "Milk",
      "merchant_id": "40076",
      "merchant_type": "express",
      "group_id": 143225,
      "is_sponsored": false,
      "url": "https://blinkit.com/prn/amul-lactose-free-milk/prid/206314"
    }
  ],
  "meta": {
    "page": 1,
    "page_size": 2,
    "returned": 2,
    "total_matched": 14,
    "upstream_total": 1214,
    "partial": true,
    "has_next": true,
    "location": { "lat": 12.9352, "lon": 77.6245, "source": "lat_lon", "query": null },
    "merchant_id": "40076",
    "cached": false,
    "fetched_at": "2026-09-29T07:15:10.812971+00:00"
  }
}
```

The example shows the first of the two requested items; `meta` is from the same request.

Sparse output with `fields=name,price` returns only those keys per product (plus `id`); `meta` is unchanged.

---

### `GET /v1/products/{product_id}`

Full detail for one product at a location. Price and stock come from the store serving the given location (`merchant_id`).

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `product_id` | int > 0 (path) | **required** | Blinkit product id (the `id` from search) |
| location | see [Location](#location) | **required** | |
| `include_similar` | bool | `true` | `false` returns `similar: []` |
| `fresh` | bool | `false` | Bypass cache |

**Example**

```bash
curl 'http://localhost:8000/v1/products/793109?lat=12.9352&lon=77.6245&include_similar=false'
```

```json
{
  "data": {
    "id": "793109",
    "name": "Country Delight 25 g High Protein Vanilla Milk",
    "brand": "Country Delight",
    "unit": "250 ml",
    "price": { "selling": 101.0, "mrp": 129.0, "discount_pct": 21.7, "currency": "INR" },
    "in_stock": true,
    "inventory": 1,
    "image": "https://cdn.grofers.com/da/cms-assets/cms/product/rc-upload-1785470076523-215.jpg",
    "rating": null,
    "merchant_id": "40076",
    "merchant_type": "express",
    "group_id": 3024333,
    "is_sponsored": false,
    "url": "https://blinkit.com/prn/country-delight-25-g-high-protein-vanilla-milk/prid/793109",
    "images": ["https://cdn.grofers.com/…-215.jpg", "https://cdn.grofers.com/…-216.jpg"],
    "categories": {
      "l0": { "id": 12,   "name": "Tea, Coffee & Milk Drinks" },
      "l1": { "id": 1184, "name": "Lassi, Shakes & More" },
      "l2": { "id": 36,   "name": "Flavoured Milk & Milk Shake" }
    },
    "breadcrumbs": ["Tea, Coffee & Milk Drinks", "Lassi, Shakes & More", "Flavoured Milk & Milk Shake"],
    "description": "Country Delight 25g Protein Vanilla Milk is a high-protein milk drink…",
    "attributes": {
      "Shelf Life": "90 days",
      "Country of Origin": "India",
      "Food Type": "veg"
    },
    "similar": []
  },
  "meta": { "location": { "lat": 12.9352, "lon": 77.6245, "source": "lat_lon", "query": null }, "cached": false, "fetched_at": "…" }
}
```

`attributes` is a free-form map of everything Blinkit publishes for the product (ingredients, nutrition per 100 g, FSSAI licence, dimensions, storage tips, …). Keys vary by product; internal flags are omitted.

Returns `404 not_found` if the product doesn't exist or isn't sold at that location.

---

### `GET /v1/categories`

Category tree (L0 → L1), independent of location.

| Name | Type | Default | Description |
|---|---|---|---|
| `depth` | int 1–2 | `2` | `1` = top level only (`subcategories: []`), `2` = include subcategories |
| `fresh` | bool | `false` | Bypass cache |

```bash
curl 'http://localhost:8000/v1/categories?depth=2'
```

```json
{
  "data": [
    {
      "id": 14,
      "name": "Dairy Breakfast",
      "slug": "dairy-breakfast",
      "url": "https://blinkit.com/cn/milk/cid/14/922",
      "subcategories": [
        { "id": 922, "name": "Milk", "slug": "milk", "url": "https://blinkit.com/cn/milk/cid/14/922", "subcategories": [] }
      ]
    }
  ],
  "meta": { "location": null, "cached": true, "fetched_at": "…" }
}
```

The tree is derived from Blinkit's public sitemaps. Names are built from URL slugs, so punctuation may differ from the app (e.g. "Atta Rice Dal" for "Atta, Rice & Dal"). Use the numeric `id`s, which are authoritative. Only categories present in the sitemap are listed.

---

### `GET /v1/categories/{l0_id}`

One top-level category with its subcategories. `404` if unknown.

---

### `GET /v1/categories/{l0_id}/products`

Browse products in a category (or subcategory) at a location. Accepts the same [location](#location), listing parameters (`page`, `page_size`, `sort`, `min_price`, `max_price`, `min_discount`, `min_rating`, `brand`, `in_stock`, `exclude_sponsored`, `fields`, `fresh`) and returns the same page envelope as search.

| Name | Type | Default | Description |
|---|---|---|---|
| `l0_id` | int > 0 (path) | **required** | Top-level category id |
| `l1_id` | int > 0 | – | Subcategory id. Omit for the whole L0 category |

```bash
curl 'http://localhost:8000/v1/categories/14/products?l1_id=922&lat=12.9352&lon=77.6245&sort=discount_desc&page_size=5&fields=name,price'
```

`404 not_found` if Blinkit doesn't recognise the category.

---

### `GET /v1/location/suggest`

Address autocomplete backed by Blinkit's location service.

| Name | Type | Default | Description |
|---|---|---|---|
| `query` | string (2–100) | **required** | Text to complete |
| `lat`, `lon` | number | server default | Bias results near this point (both needed) |
| `resolve` | bool | `true` | Also look up `lat`/`lon` for each suggestion (one extra upstream call each, cached 24 h). `false` returns `lat`/`lon` as `null` |

```bash
curl 'http://localhost:8000/v1/location/suggest?query=koramangala'
```

```json
[
  {
    "title": "Koramangala",
    "subtitle": "Bengaluru, Karnataka, India",
    "place_id": "ChIJLfyY2E4UrjsRVq4AjI7zgRY",
    "lat": 12.9352403,
    "lon": 77.624532
  }
]
```

Feed a suggestion's `lat`/`lon` into any product endpoint.

---

### `GET /v1/location/serviceability`

Whether Blinkit delivers to a location, the delivery ETA and the resolved address. Accepts the [location](#location) params plus `fresh`.

```bash
curl 'http://localhost:8000/v1/location/serviceability?address=indiranagar%20bangalore'
```

```json
{
  "data": {
    "lat": 12.9783692,
    "lon": 77.6408356,
    "serviceable": true,
    "eta_minutes": 10,
    "eta_text": "Delivery in 10 minutes",
    "address": "788, 100 Feet Rd, Binnamangala, Stage 1, Indiranagar, Bengaluru, Karnataka 560038, India",
    "locality": "Indiranagar",
    "city": "Bengaluru",
    "state": "Karnataka",
    "postal_code": "560038"
  },
  "meta": {
    "location": { "lat": 12.9783692, "lon": 77.6408356, "source": "address", "query": "indiranagar bangalore" },
    "cached": false,
    "fetched_at": "2026-09-29T07:15:15.752173Z"
  }
}
```

This endpoint returns `200` with `serviceable: false` (and `eta_minutes: null`) for unserved locations, rather than `424`. Other endpoints check serviceability first and return `424`.

---

### `GET /health`

```json
{
  "status": "ok",
  "upstream": { "last_success_at": "2026-09-29T07:15:15.98+00:00", "last_block_at": null },
  "cache": { "listing": 3, "product": 1, "location": 4, "geocode": 10, "categories": 1 }
}
```

`last_block_at` is when Blinkit last rejected a request as bot traffic; non-null and recent means expect `503`s. `cache` shows entry counts per namespace. This endpoint never calls Blinkit.

---

## Data models

### Product

| Field | Type | Description |
|---|---|---|
| `id` | string | Blinkit product id |
| `name` | string | Display name |
| `brand` | string \| null | Brand |
| `unit` | string \| null | Pack size / variant, e.g. `"500 ml"` |
| `price` | [Price](#price) | |
| `in_stock` | bool | Available to order right now at this location |
| `inventory` | int \| null | Max quantity currently orderable |
| `image` | string \| null | Primary image URL |
| `rating` | [Rating](#rating) \| null | |
| `product_type` | string \| null | Product type label, e.g. `"High Protein Milk"` |
| `merchant_id` | string \| null | Serving dark store id |
| `merchant_type` | string \| null | e.g. `express` |
| `group_id` | int \| null | Blinkit's product-group id (variants share it) |
| `is_sponsored` | bool | Ad placement |
| `url` | string | blinkit.com product page |

### ProductDetail

Everything in **Product**, plus:

| Field | Type | Description |
|---|---|---|
| `images` | string[] | All gallery images |
| `categories` | map `l0`/`l1`/`l2` → `{id, name}` | Category path (only levels Blinkit provides) |
| `breadcrumbs` | string[] | Category names as shown on the page |
| `description` | string \| null | Marketing description |
| `attributes` | map string → string | All published attributes |
| `similar` | Product[] | Similar/related products at this location |

### Price

| Field | Type | Description |
|---|---|---|
| `selling` | number \| null | Price payable (INR) |
| `mrp` | number \| null | Maximum retail price. Equals `selling` when there is no markdown |
| `discount_pct` | number | `(mrp − selling) / mrp × 100`, one decimal; `0` if none |
| `currency` | string | Always `INR` |

### Rating

| Field | Type | Description |
|---|---|---|
| `value` | number \| null | 0–5 |
| `count` | string \| null | As displayed by Blinkit, e.g. `"4,627"` or `"1.2 lac"` (not a number) |

### PageMeta

| Field | Type | Description |
|---|---|---|
| `page`, `page_size` | int | Echo of the request |
| `returned` | int | Items in `data` |
| `total_matched` | int | Items matching your filters among those scanned |
| `upstream_total` | int \| null | Blinkit's own total for the query |
| `partial` | bool | See [Pagination](#pagination-filtering-and-partial) |
| `has_next` | bool | Another page is available |
| `location` | object | `{lat, lon, source, query}` as resolved |
| `merchant_id` | string \| null | Store serving this location |
| `cached` | bool | Served from cache |
| `fetched_at` | ISO 8601 | When the data was fetched from Blinkit |

### Category

`{ id: int, name: string, slug: string, url: string, subcategories: Category[] }`

### Serviceability

`{ lat, lon, serviceable, eta_minutes, eta_text, address, locality, city, state, postal_code }` — all but `lat`, `lon`, `serviceable` may be `null`.

### PlaceSuggestion

`{ title, subtitle, place_id, lat, lon }` — `lat`/`lon` are `null` when `resolve=false` or unresolvable.

---

## Errors

Every error uses one shape:

```json
{ "error": { "code": "location_not_serviceable", "message": "Blinkit does not deliver to (51.5, -0.12)" } }
```

| Status | `code` | When |
|---|---|---|
| 400 | `bad_request` | Missing/multiple location forms, `min_price` > `max_price`, unknown `fields` |
| 400 | `location_not_resolved` | Pincode/address couldn't be geocoded |
| 404 | `not_found` | Unknown product, category, or path |
| 422 | `validation_error` | Malformed parameter (bad enum, out of range, wrong pincode format). Includes `details: [{loc, msg}]` |
| 424 | `location_not_serviceable` | Blinkit doesn't deliver to the location |
| 502 | `upstream_error` | Blinkit returned an unexpected response |
| 503 | `upstream_blocked` | Blinkit is blocking/rate-limiting; has `Retry-After: 60` |

Validation example:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Invalid request parameters",
    "details": [{ "loc": "query.pincode", "msg": "String should match pattern '^\\d{6}$'" }]
  }
}
```

Clients should retry `502`/`503` with backoff and treat `4xx` as non-retryable.

---

## Recipes

**Cheapest in-stock Amul milk near a PIN code**

```bash
curl 'localhost:8000/v1/products/search?q=milk&pincode=560038&brand=amul&in_stock=true&sort=price_asc&page_size=5&fields=name,unit,price'
```

**Biggest discounts in a category (dairy → milk)**

```bash
curl 'localhost:8000/v1/categories/14/products?l1_id=922&lat=12.9352&lon=77.6245&sort=discount_desc&min_discount=10'
```

**Compare one item across cities**

```bash
for loc in 'lat=28.6139&lon=77.2090' 'lat=12.9352&lon=77.6245'; do
  curl -s "localhost:8000/v1/products/search?q=amul%20taaza&$loc&page_size=1&fields=name,price,inventory"
done
```

**From address text to products**

```bash
# 1. find coordinates
curl 'localhost:8000/v1/location/suggest?query=hsr layout'
# 2. check delivery
curl 'localhost:8000/v1/location/serviceability?lat=12.91&lon=77.64'
# 3. shop
curl 'localhost:8000/v1/products/search?q=bread&lat=12.91&lon=77.64'
```

(Or skip the first two steps and pass `address=hsr layout` directly.)

**Walk all pages of a search (Python)**

```python
import httpx

base, page, items = "http://localhost:8000", 1, []
while True:
    r = httpx.get(f"{base}/v1/products/search",
                  params={"q": "milk", "pincode": "560038", "page": page, "page_size": 50})
    r.raise_for_status()
    body = r.json()
    items += body["data"]
    if not body["meta"]["has_next"]:
        break
    page += 1
```

The upstream scan is capped (default 120 items), so very deep pages end early. `has_next` becomes `false` at the cap.

---

## Configuration

Environment variables, prefix `BLINKIT_`, or a `.env` file:

| Variable | Default | Meaning |
|---|---|---|
| `BLINKIT_UPSTREAM_TIMEOUT` | `20` | Seconds per upstream request |
| `BLINKIT_MAX_CONCURRENCY` | `4` | Max simultaneous upstream requests |
| `BLINKIT_MAX_RETRIES` | `2` | Retries on block / 5xx / network error |
| `BLINKIT_MAX_UPSTREAM_ITEMS` | `120` | Scan cap for filtered/sorted listings |
| `BLINKIT_CACHE_TTL_LISTING` | `300` | Seconds |
| `BLINKIT_CACHE_TTL_PRODUCT` | `300` | Seconds |
| `BLINKIT_CACHE_TTL_LOCATION` | `600` | Seconds |
| `BLINKIT_CACHE_TTL_CATEGORIES` | `21600` | Seconds |
| `BLINKIT_CACHE_TTL_GEOCODE` | `86400` | Seconds |
| `BLINKIT_CACHE_MAX_ENTRIES` | `2048` | Per cache namespace |
| `BLINKIT_DEFAULT_LAT`, `BLINKIT_DEFAULT_LON` | Delhi | Bias for address autocomplete when the caller gives no coordinates |
