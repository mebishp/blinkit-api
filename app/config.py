from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BLINKIT_", env_file=".env", extra="ignore")

    base_url: str = "https://blinkit.com"
    impersonate: str = "chrome"
    upstream_timeout: float = 20.0
    max_concurrency: int = 4
    max_retries: int = 2

    # Upper bound on items pulled from upstream for one listing when local
    # filtering/sorting is required (upstream pages are 12-15 items each).
    max_upstream_items: int = 120

    cache_ttl_listing: int = 300
    cache_ttl_product: int = 300
    cache_ttl_location: int = 600
    cache_ttl_categories: int = 6 * 3600
    cache_ttl_geocode: int = 24 * 3600
    cache_max_entries: int = 2048

    default_lat: float = 28.6139
    default_lon: float = 77.2090


@lru_cache
def get_settings() -> Settings:
    return Settings()
