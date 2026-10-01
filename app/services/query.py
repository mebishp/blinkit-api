"""Local filtering / sorting / pagination over parsed products.

Blinkit's web API has no server-side price/brand/sort filters we can rely on,
so these are applied to the items fetched from upstream.
"""

from dataclasses import dataclass, field

from app.schemas import Product, SortOption


@dataclass
class ListingQuery:
    page: int = 1
    page_size: int = 24
    sort: SortOption = SortOption.relevance
    min_price: float | None = None
    max_price: float | None = None
    min_discount: float | None = None
    min_rating: float | None = None
    brands: list[str] = field(default_factory=list)
    in_stock: bool | None = None
    exclude_sponsored: bool = False

    @property
    def start(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def end(self) -> int:
        return self.page * self.page_size

    @property
    def needs_full_scan(self) -> bool:
        """True if the result order/membership depends on items beyond the requested page."""
        return self.sort is not SortOption.relevance or any(
            (
                self.min_price is not None,
                self.max_price is not None,
                self.min_discount is not None,
                self.min_rating is not None,
                bool(self.brands),
                self.in_stock is not None,
                self.exclude_sponsored,
            )
        )


def matches(p: Product, q: ListingQuery) -> bool:
    price = p.price.selling
    if q.min_price is not None and (price is None or price < q.min_price):
        return False
    if q.max_price is not None and (price is None or price > q.max_price):
        return False
    if q.min_discount is not None and p.price.discount_pct < q.min_discount:
        return False
    if q.min_rating is not None and (p.rating is None or (p.rating.value or 0) < q.min_rating):
        return False
    if q.brands:
        wanted = {b.strip().lower() for b in q.brands if b.strip()}
        if (p.brand or "").lower() not in wanted:
            return False
    if q.in_stock is not None and p.in_stock != q.in_stock:
        return False
    return not (q.exclude_sponsored and p.is_sponsored)


_INF = float("inf")

_SORT_KEYS = {
    SortOption.price_asc: lambda p: p.price.selling if p.price.selling is not None else _INF,
    SortOption.price_desc: lambda p: -(p.price.selling if p.price.selling is not None else -_INF),
    SortOption.discount_desc: lambda p: -p.price.discount_pct,
    SortOption.name_asc: lambda p: p.name.lower(),
    SortOption.rating_desc: lambda p: -((p.rating.value or 0) if p.rating else 0),
}


def apply(products: list[Product], q: ListingQuery) -> list[Product]:
    out = [p for p in products if matches(p, q)]
    key = _SORT_KEYS.get(q.sort)
    if key:
        out.sort(key=key)  # stable: ties keep Blinkit's relevance order
    return out
