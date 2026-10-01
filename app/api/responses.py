from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.schemas import LocationContext, Page, PageMeta, Product
from app.services.catalog import ListingResult
from app.services.query import ListingQuery

PRODUCT_FIELDS = set(Product.model_fields)


def parse_fields(fields: str | None) -> set[str] | None:
    if not fields:
        return None
    wanted = {f.strip() for f in fields.split(",") if f.strip()}
    unknown = wanted - PRODUCT_FIELDS
    if unknown:
        raise HTTPException(400, f"Unknown fields: {', '.join(sorted(unknown))}")
    return wanted | {"id"}


def listing_response(
    result: ListingResult, lq: ListingQuery, location: LocationContext, fields: str | None
) -> Page[Product] | JSONResponse:
    meta = PageMeta(
        page=lq.page,
        page_size=lq.page_size,
        returned=len(result.items),
        total_matched=result.total_matched,
        upstream_total=result.upstream_total,
        partial=result.partial,
        has_next=result.has_next,
        location=location,
        merchant_id=result.merchant_id,
        cached=result.cached,
        fetched_at=result.fetched_at,
    )
    include = parse_fields(fields)
    if include is None:
        return Page[Product](data=result.items, meta=meta)
    # Sparse fieldsets don't fit the response model, so bypass it.
    return JSONResponse(
        jsonable_encoder(
            {"data": [p.model_dump(include=include) for p in result.items], "meta": meta.model_dump()}
        )
    )
