from functools import lru_cache

from core.config import Settings, settings as _settings


@lru_cache
def get_settings() -> Settings:
    return _settings