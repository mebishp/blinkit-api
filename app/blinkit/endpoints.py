"""Upstream Blinkit endpoints (reverse-engineered from the consumer web app).

Everything Blinkit-specific about URLs and headers lives here so a change on
their side is a one-file fix.
"""

from urllib.parse import quote

SEARCH = "/v1/layout/search?q={q}&search_type=type_to_search"
LISTING = "/v1/layout/listing_widgets?l0_cat={l0}"
PRODUCT = "/v1/layout/product/{product_id}"
ETA = "/v1/consumerweb/eta"
LOCATION_INFO = "/location/info"
AUTOSUGGEST = "/location/autoSuggest"
SITEMAP_CATEGORIES = "/sitemaps/categories.xml"
SITEMAP_INDEX = "/sitemap.xml"


def search_path(q: str) -> str:
    return SEARCH.format(q=quote(q))


def listing_path(l0: int, l1: int | None) -> str:
    path = LISTING.format(l0=l0)
    return f"{path}&l1_cat={l1}" if l1 is not None else path


def product_path(product_id: int) -> str:
    return PRODUCT.format(product_id=product_id)


def location_headers(lat: float, lon: float) -> dict[str, str]:
    # Blinkit resolves the serving dark store (merchant) from these headers.
    return {
        "lat": f"{lat:.6f}",
        "lon": f"{lon:.6f}",
        "app_client": "consumer_web",
        "accept": "application/json",
        "content-type": "application/json",
    }
