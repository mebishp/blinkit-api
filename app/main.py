import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import categories, health, location, products
from app.blinkit.client import BlinkitClient, UpstreamBlocked, UpstreamError
from app.config import Settings, get_settings
from app.services.catalog import Catalog, LocationNotResolved, NotFound, NotServiceable

log = logging.getLogger(__name__)


def _error(status: int, code: str, message: str, headers: dict | None = None, **extra) -> JSONResponse:
    body = {"error": {"code": code, "message": message, **extra}}
    return JSONResponse(status_code=status, content=body, headers=headers)


def create_app(settings: Settings | None = None, client: BlinkitClient | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        c = client or BlinkitClient(settings)
        app.state.catalog = Catalog(c, settings)
        yield
        await c.close()

    app = FastAPI(
        title="Blinkit Products API",
        version="0.1.0",
        description=(
            "Unofficial, location-aware access to Blinkit's catalogue: search, category browse, "
            "product detail, and serviceability. Prices, stock and assortment depend on the dark "
            "store serving the given location."
        ),
        lifespan=lifespan,
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(_: Request, exc: StarletteHTTPException):
        code = {400: "bad_request", 404: "not_found"}.get(exc.status_code, "http_error")
        return _error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exc(_: Request, exc: RequestValidationError):
        details = [{"loc": ".".join(str(p) for p in e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return _error(422, "validation_error", "Invalid request parameters", details=details)

    @app.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound):
        return _error(404, "not_found", str(exc))

    @app.exception_handler(NotServiceable)
    async def not_serviceable(_: Request, exc: NotServiceable):
        return _error(424, "location_not_serviceable", str(exc))

    @app.exception_handler(LocationNotResolved)
    async def not_resolved(_: Request, exc: LocationNotResolved):
        return _error(400, "location_not_resolved", str(exc))

    @app.exception_handler(UpstreamBlocked)
    async def blocked(_: Request, exc: UpstreamBlocked):
        return _error(
            503,
            "upstream_blocked",
            "Blinkit is rate-limiting or blocking requests; retry later",
            headers={"Retry-After": "60"},
        )

    @app.exception_handler(UpstreamError)
    async def upstream(_: Request, exc: UpstreamError):
        log.warning("upstream error: %s", exc)
        return _error(502, "upstream_error", "Blinkit returned an unexpected response")

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse("/docs")

    for r in (products.router, categories.router, location.router, health.router):
        app.include_router(r)
    return app


app = create_app()
