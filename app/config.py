"""Настройки из переменных окружения (.env)."""
import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _int_or_none(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    return int(value) if value else None


@dataclass(frozen=True)
class Settings:
    keitaro_url: str
    keitaro_api_key: str
    database_url: str
    campaign_prefix: str
    default_group_id: int | None
    default_domain_id: int | None
    default_traffic_source_id: int | None
    geo_redirect_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        keitaro_url=os.getenv("KEITARO_URL", "").rstrip("/"),
        keitaro_api_key=os.getenv("KEITARO_API_KEY", ""),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./keitaro_wrapper.db"),
        campaign_prefix=os.getenv("CAMPAIGN_PREFIX", "test_ivanov_"),
        default_group_id=_int_or_none("DEFAULT_GROUP_ID"),
        default_domain_id=_int_or_none("DEFAULT_DOMAIN_ID"),
        default_traffic_source_id=_int_or_none("DEFAULT_TRAFFIC_SOURCE_ID"),
        geo_redirect_url=os.getenv("GEO_REDIRECT_URL", "https://google.com"),
    )
