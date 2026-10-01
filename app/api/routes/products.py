from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import CatalogDep, FieldsParam, FreshParam, ListingQueryDep, LocationDep
from app.api.responses import listing_response
from app.schemas import Item, ItemMeta, Page, Product, ProductDetail

router = APIRouter(prefix="/v1/products", tags=["products"])


@router.get("/search", response_model=Page[Product], summary="Search products at a location")
async def search_products(
    catalog: CatalogDep,
    location: LocationDep,
    lq: ListingQueryDep,
    q: Annotated[str, Query(min_length=1, max_length=100, description="Search text")],
    fields: FieldsParam = None,
    fresh: FreshParam = False,
):
    result = await catalog.search(q, location.lat, location.lon, lq, fresh=fresh)
    return listing_response(result, lq, location, fields)


@router.get("/{product_id}", response_model=Item[ProductDetail], summary="Full product detail at a location")
async def get_product(
    catalog: CatalogDep,
    location: LocationDep,
    product_id: Annotated[int, Path(gt=0)],
    include_similar: Annotated[bool, Query(description="Include 'similar products' rails")] = True,
    fresh: FreshParam = False,
):
    res = await catalog.product(product_id, location.lat, location.lon, fresh=fresh)
    detail: ProductDetail = res.value
    if not include_similar:
        detail = detail.model_copy(update={"similar": []})
    return Item[ProductDetail](
        data=detail, meta=ItemMeta(location=location, cached=res.hit, fetched_at=res.fetched_at)
    )
