from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Price(BaseModel):
    selling: float | None = None
    mrp: float | None = None
    discount_pct: float = 0.0
    currency: str = "INR"


class Rating(BaseModel):
    value: float | None = None
    count: str | None = Field(None, description="As displayed by Blinkit, e.g. '4,627' or '1.2 lac'")


class CategoryRef(BaseModel):
    id: int | None = None
    name: str | None = None


class Product(BaseModel):
    id: str
    name: str
    brand: str | None = None
    unit: str | None = None
    price: Price
    in_stock: bool
    inventory: int | None = Field(None, description="Max quantity orderable right now")
    image: str | None = None
    rating: Rating | None = None
    product_type: str | None = None
    merchant_id: str | None = None
    merchant_type: str | None = None
    group_id: int | None = None
    is_sponsored: bool = False
    url: str


class ProductDetail(Product):
    images: list[str] = []
    categories: dict[str, CategoryRef] = Field(default_factory=dict, description="l0 / l1 / l2")
    breadcrumbs: list[str] = []
    description: str | None = None
    attributes: dict[str, str] = {}
    similar: list[Product] = []


class Category(BaseModel):
    id: int
    name: str
    slug: str
    url: str
    subcategories: list["Category"] = []


class Coordinates(BaseModel):
    lat: float
    lon: float


class LocationContext(Coordinates):
    source: str = Field(description="lat_lon | pincode | address")
    query: str | None = None


class Serviceability(BaseModel):
    lat: float
    lon: float
    serviceable: bool
    eta_minutes: int | None = None
    eta_text: str | None = None
    address: str | None = None
    locality: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None


class PlaceSuggestion(BaseModel):
    title: str
    subtitle: str | None = None
    place_id: str
    lat: float | None = None
    lon: float | None = None


class SortOption(StrEnum):
    relevance = "relevance"
    price_asc = "price_asc"
    price_desc = "price_desc"
    discount_desc = "discount_desc"
    name_asc = "name_asc"
    rating_desc = "rating_desc"


class PageMeta(BaseModel):
    page: int
    page_size: int
    returned: int
    total_matched: int = Field(description="Items matching filters among those fetched from upstream")
    upstream_total: int | None = Field(None, description="Total items Blinkit reports for the query")
    partial: bool = Field(
        description="True when not every upstream item was scanned, so filters/sorting cover a subset"
    )
    has_next: bool
    location: LocationContext
    merchant_id: str | None = None
    cached: bool
    fetched_at: datetime


class Page[T](BaseModel):
    data: list[T]
    meta: PageMeta


class ItemMeta(BaseModel):
    location: LocationContext | None = None
    cached: bool
    fetched_at: datetime


class Item[T](BaseModel):
    data: T
    meta: ItemMeta


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
