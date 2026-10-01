from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CatalogDep, FreshParam, LocationDep
from app.schemas import Coordinates, Item, ItemMeta, PlaceSuggestion, Serviceability

router = APIRouter(prefix="/v1/location", tags=["location"])


@router.get("/suggest", response_model=list[PlaceSuggestion], summary="Address autocomplete")
async def suggest(
    catalog: CatalogDep,
    query: Annotated[str, Query(min_length=2, max_length=100)],
    lat: Annotated[float | None, Query(ge=-90, le=90, description="Bias results near here")] = None,
    lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    resolve: Annotated[bool, Query(description="Also look up lat/lon for each suggestion")] = True,
):
    bias = Coordinates(lat=lat, lon=lon) if lat is not None and lon is not None else None
    return await catalog.suggest(query, bias=bias, resolve=resolve)


@router.get(
    "/serviceability",
    response_model=Item[Serviceability],
    summary="Whether Blinkit delivers here, delivery ETA and resolved address",
)
async def serviceability(catalog: CatalogDep, location: LocationDep, fresh: FreshParam = False):
    res = await catalog.serviceability(location.lat, location.lon, fresh=fresh)
    return Item[Serviceability](
        data=res.value, meta=ItemMeta(location=location, cached=res.hit, fetched_at=res.fetched_at)
    )
