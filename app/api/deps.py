from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request

from app.schemas import LocationContext, SortOption
from app.services.catalog import Catalog
from app.services.query import ListingQuery


def get_catalog(request: Request) -> Catalog:
    return request.app.state.catalog


CatalogDep = Annotated[Catalog, Depends(get_catalog)]


async def resolve_location(
    catalog: CatalogDep,
    lat: Annotated[float | None, Query(ge=-90, le=90, description="Latitude (use with lon)")] = None,
    lon: Annotated[float | None, Query(ge=-180, le=180, description="Longitude (use with lat)")] = None,
    pincode: Annotated[str | None, Query(pattern=r"^\d{6}$", description="Indian 6-digit PIN code")] = None,
    address: Annotated[
        str | None, Query(min_length=3, max_length=200, description="Free-form address / locality")
    ] = None,
) -> LocationContext:
    """Exactly one of: lat+lon, pincode, address."""
    given = [lat is not None or lon is not None, pincode is not None, address is not None]
    if sum(given) != 1:
        raise HTTPException(400, "Provide exactly one location: lat+lon, pincode, or address")
    if given[0]:
        if lat is None or lon is None:
            raise HTTPException(400, "Both lat and lon are required")
        return LocationContext(lat=lat, lon=lon, source="lat_lon")
    text = pincode or address
    coords = await catalog.geocode(text)
    return LocationContext(
        lat=coords.lat, lon=coords.lon, source="pincode" if pincode else "address", query=text
    )


LocationDep = Annotated[LocationContext, Depends(resolve_location)]


def listing_query(
    page: Annotated[int, Query(ge=1, le=100)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 24,
    sort: SortOption = SortOption.relevance,
    min_price: Annotated[float | None, Query(ge=0, description="Min selling price (INR)")] = None,
    max_price: Annotated[float | None, Query(ge=0, description="Max selling price (INR)")] = None,
    min_discount: Annotated[float | None, Query(ge=0, le=100, description="Min discount % off MRP")] = None,
    min_rating: Annotated[float | None, Query(ge=0, le=5)] = None,
    brand: Annotated[
        list[str] | None, Query(description="Brand filter; repeatable, case-insensitive")
    ] = None,
    in_stock: Annotated[bool | None, Query(description="true = only in stock, false = only sold out")] = None,
    exclude_sponsored: Annotated[bool, Query(description="Drop ad/sponsored listings")] = False,
) -> ListingQuery:
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(400, "min_price cannot exceed max_price")
    return ListingQuery(
        page=page,
        page_size=page_size,
        sort=sort,
        min_price=min_price,
        max_price=max_price,
        min_discount=min_discount,
        min_rating=min_rating,
        brands=brand or [],
        in_stock=in_stock,
        exclude_sponsored=exclude_sponsored,
    )


ListingQueryDep = Annotated[ListingQuery, Depends(listing_query)]

FreshParam = Annotated[bool, Query(description="Bypass the cache and refetch from Blinkit")]
FieldsParam = Annotated[
    str | None,
    Query(description="Comma-separated product fields to return, e.g. id,name,price. Default: all."),
]
