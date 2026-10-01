from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from app.api.deps import CatalogDep, FieldsParam, FreshParam, ListingQueryDep, LocationDep
from app.api.responses import listing_response
from app.schemas import Category, Item, ItemMeta, Page, Product

router = APIRouter(prefix="/v1/categories", tags=["categories"])


@router.get("", response_model=Item[list[Category]], summary="Category tree (L0 → L1)")
async def list_categories(
    catalog: CatalogDep,
    depth: Annotated[int, Query(ge=1, le=2, description="1 = top level only, 2 = with subcategories")] = 2,
    fresh: FreshParam = False,
):
    res = await catalog.categories(fresh=fresh)
    tree: list[Category] = res.value
    if depth == 1:
        tree = [c.model_copy(update={"subcategories": []}) for c in tree]
    return Item[list[Category]](data=tree, meta=ItemMeta(cached=res.hit, fetched_at=res.fetched_at))


@router.get("/{l0_id}", response_model=Item[Category], summary="One top-level category with subcategories")
async def get_category(catalog: CatalogDep, l0_id: Annotated[int, Path(gt=0)]):
    res = await catalog.categories()
    for c in res.value:
        if c.id == l0_id:
            return Item[Category](data=c, meta=ItemMeta(cached=res.hit, fetched_at=res.fetched_at))
    raise HTTPException(404, f"category {l0_id} not found")


@router.get(
    "/{l0_id}/products", response_model=Page[Product], summary="Browse products in a category at a location"
)
async def browse_category(
    catalog: CatalogDep,
    location: LocationDep,
    lq: ListingQueryDep,
    l0_id: Annotated[int, Path(gt=0)],
    l1_id: Annotated[
        int | None, Query(gt=0, description="Subcategory id; omit for the whole category")
    ] = None,
    fields: FieldsParam = None,
    fresh: FreshParam = False,
):
    result = await catalog.browse(l0_id, l1_id, location.lat, location.lon, lq, fresh=fresh)
    return listing_response(result, lq, location, fields)
