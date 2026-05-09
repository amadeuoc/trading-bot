from typing import Any, Optional


_cache = {}


def get_cache(key: str) -> Optional[Any]:
    return _cache.get(key)


def set_cache(key: str, value: Any) -> Any:
    _cache[key] = value
    return value
