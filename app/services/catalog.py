import asyncio
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.blinkit import endpoints, parser
from app.blinkit.categories import build_category_tree
from app.blinkit.client import BlinkitClient, UpstreamError, UpstreamNotFound
from app.config import Settings
from app.schemas import (
    Category,
    Coordinates,
    PlaceSuggestion,
    Product,
    ProductDetail,
    Serviceability,
)
from app.services import query as q
from app.services.cache import AsyncTTLCache, Cached


class NotFound(Exception):
    pass


class NotServiceable(Exception):
    def __init__(self, lat: float, lon: float):
        super().__init__(f"Blinkit does not deliver to ({lat}, {lon})")


class LocationNotResolved(Exception):
    pass


def loc_key(lat: float, lon: float) -> tuple[float, float]:
    # ~110 m buckets: same dark store, far better cache hit rate.
    return round(lat, 3), round(lon, 3)


@dataclass
class ListingState:
    products: list[Product] = field(default_factory=list)
    next_url: str | None = None
    upstream_total: int | None = None
    started: bool = False
    fetched_at: datetime | None = None

    @property
    def exhausted(self) -> bool:
        return self.started and not self.next_url


@dataclass
class ListingResult:
    items: list[Product]
    total_matched: int
    upstream_total: int | None
    partial: bool
    has_next: bool
    merchant_id: str | None
    cached: bool
    fetched_at: datetime


class Catalog:
    def __init__(self, client: BlinkitClient, settings: Settings):
        self.client = client
        self.s = settings
        self.cache = AsyncTTLCache(
            settings.cache_max_entries,
            {
                "listing": settings.cache_ttl_listing,
                "product": settings.cache_ttl_product,
                "location": settings.cache_ttl_location,
                "geocode": settings.cache_ttl_geocode,
                "categories": settings.cache_ttl_categories,
            },
        )

    # ---------- listings (search + category browse) ----------

    async def _extend(self, state: ListingState, first_path: str, lat: float, lon: float, want: int) -> None:
        while len(state.products) < want and not state.exhausted:
            path = state.next_url if state.started else first_path
            resp = await self.client.post_layout(path, lat, lon)
            products, next_url, total = parser.parse_listing(resp)
            seen = {p.id for p in state.products}
            new = [p for p in products if p.id not in seen]
            state.products.extend(new)
            state.started = True
            state.next_url = next_url if new else None  # stop if upstream starts repeating itself
            if total is not None:
                state.upstream_total = total
            state.fetched_at = datetime.now(UTC)

    async def _listing(
        self, key: tuple, first_path: str, lat: float, lon: float, lq: q.ListingQuery, fresh: bool
    ) -> ListingResult:
        cap = self.s.max_upstream_items
        want = cap if lq.needs_full_scan else min(cap, lq.end + 1)

        cached_entry = None if fresh else self.cache.peek("listing", key)
        state: ListingState = cached_entry[0] if cached_entry else ListingState()
        cache_hit = cached_entry is not None and (len(state.products) >= want or state.exhausted)

        if not cache_hit:
            async with self.cache.locked("listing", key):
                if not fresh and (again := self.cache.peek("listing", key)):
                    state = again[0]
                await self._extend(state, first_path, lat, lon, want)
                self.cache.put("listing", key, state)

        matched = q.apply(state.products, lq)
        page_items = matched[lq.start : lq.end]
        scanned_all = state.exhausted
        more_upstream = not scanned_all and len(state.products) < cap
        return ListingResult(
            items=page_items,
            total_matched=len(matched),
            upstream_total=state.upstream_total,
            partial=lq.needs_full_scan and not scanned_all,
            has_next=len(matched) > lq.end or (not lq.needs_full_scan and more_upstream),
            merchant_id=next((p.merchant_id for p in state.products if p.merchant_id), None),
            cached=cache_hit,
            fetched_at=state.fetched_at or datetime.now(UTC),
        )

    async def search(self, text: str, lat: float, lon: float, lq: q.ListingQuery, fresh: bool = False):
        await self.ensure_serviceable(lat, lon)
        norm = " ".join(text.lower().split())
        key = ("search", norm, *loc_key(lat, lon))
        return await self._listing(key, endpoints.search_path(norm), lat, lon, lq, fresh)

    async def browse(
        self, l0: int, l1: int | None, lat: float, lon: float, lq: q.ListingQuery, fresh: bool = False
    ):
        await self.ensure_serviceable(lat, lon)
        key = ("browse", l0, l1, *loc_key(lat, lon))
        try:
            return await self._listing(key, endpoints.listing_path(l0, l1), lat, lon, lq, fresh)
        except UpstreamError as exc:
            if isinstance(exc, UpstreamNotFound) or "unsuccessful" in str(exc):
                raise NotFound(f"category {l0}/{l1} not found") from exc
            raise

    # ---------- product detail ----------

    async def product(self, product_id: int, lat: float, lon: float, fresh: bool = False) -> Cached:
        await self.ensure_serviceable(lat, lon)

        async def load() -> ProductDetail:
            try:
                resp = await self.client.post_layout(endpoints.product_path(product_id), lat, lon)
            except UpstreamNotFound as exc:
                raise NotFound(f"product {product_id} not found") from exc
            except UpstreamError as exc:
                if "unsuccessful" in str(exc):
                    raise NotFound(f"product {product_id} not found") from exc
                raise
            detail = parser.parse_product_detail(resp, product_id)
            if detail is None:
                raise NotFound(f"product {product_id} not found")
            return detail

        return await self.cache.get_or_load("product", (product_id, *loc_key(lat, lon)), load, fresh=fresh)

    # ---------- categories ----------

    async def categories(self, fresh: bool = False) -> Cached:
        async def load() -> list[Category]:
            cats_xml, index_xml = await asyncio.gather(
                self.client.get_text(endpoints.SITEMAP_CATEGORIES),
                self.client.get_text(endpoints.SITEMAP_INDEX),
            )
            tree = build_category_tree(cats_xml, index_xml)
            if not tree:
                raise UpstreamError("category sitemap returned no categories")
            return tree

        return await self.cache.get_or_load("categories", "tree", load, fresh=fresh)

    # ---------- location ----------

    async def serviceability(self, lat: float, lon: float, fresh: bool = False) -> Cached:
        klat, klon = loc_key(lat, lon)

        async def load() -> Serviceability:
            info_raw, eta_raw = await asyncio.gather(
                self.client.get_json(endpoints.LOCATION_INFO, params={"lat": lat, "lon": lon}),
                self.client.get_json(endpoints.ETA, lat=lat, lon=lon),
                return_exceptions=True,
            )
            if isinstance(info_raw, BaseException):
                raise info_raw
            info = parser.parse_location_info(info_raw)
            eta_min, eta_text = (None, None)
            if info["serviceable"] and isinstance(eta_raw, dict):
                eta_min, eta_text = parser.parse_eta(eta_raw)
            return Serviceability(**{**info, "lat": lat, "lon": lon}, eta_minutes=eta_min, eta_text=eta_text)

        return await self.cache.get_or_load("location", (klat, klon), load, fresh=fresh)

    async def ensure_serviceable(self, lat: float, lon: float) -> None:
        svc = (await self.serviceability(lat, lon)).value
        if not svc.serviceable:
            raise NotServiceable(lat, lon)

    async def suggest(
        self, text: str, bias: Coordinates | None = None, resolve: bool = False
    ) -> list[PlaceSuggestion]:
        bias = bias or Coordinates(lat=self.s.default_lat, lon=self.s.default_lon)
        norm = " ".join(text.lower().split())

        async def load() -> list[dict]:
            data = await self.client.get_json(
                endpoints.AUTOSUGGEST, params={"query": norm, "lat": bias.lat, "lng": bias.lon}
            )
            return parser.parse_autosuggest(data)

        raw = (
            await self.cache.get_or_load("geocode", ("suggest", norm, *loc_key(bias.lat, bias.lon)), load)
        ).value
        suggestions = [PlaceSuggestion(**r) for r in raw]
        if resolve and suggestions:
            coords = await asyncio.gather(*(self.place_coordinates(s.place_id) for s in suggestions))
            for s, c in zip(suggestions, coords):
                if c:
                    s.lat, s.lon = c.lat, c.lon
        return suggestions

    async def place_coordinates(self, place_id: str) -> Coordinates | None:
        async def load() -> Coordinates | None:
            data = await self.client.get_json(endpoints.LOCATION_INFO, params={"place_id": place_id})
            info = parser.parse_location_info(data)
            if info["lat"] is None or info["lon"] is None:
                return None
            return Coordinates(lat=info["lat"], lon=info["lon"])

        return (await self.cache.get_or_load("geocode", ("place", place_id), load)).value

    async def geocode(self, text: str) -> Coordinates:
        """Resolve a pincode or free-form address to coordinates via Blinkit's own geocoder."""
        suggestions = await self.suggest(text)
        if re.fullmatch(r"\d{6}", text.strip()):
            # Prefer a suggestion that actually mentions the pincode.
            suggestions.sort(key=lambda s: text.strip() not in f"{s.title} {s.subtitle or ''}")
        for s in suggestions[:3]:
            if coords := await self.place_coordinates(s.place_id):
                return coords
        raise LocationNotResolved(f"could not resolve location '{text}'")
