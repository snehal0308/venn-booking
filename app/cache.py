"""Tiny disk cache so repeated demo queries are instant and you don't burn API quota."""
import hashlib
import json
import os
import time

from .config import CACHE_DIR

os.makedirs(CACHE_DIR, exist_ok=True)


def _path(namespace: str, key: str) -> str:
    digest = hashlib.sha256(key.encode()).hexdigest()[:24]
    return os.path.join(CACHE_DIR, f"{namespace}-{digest}.json")


def cached(namespace: str, ttl_seconds: int = 60 * 60 * 24):
    """Decorator: cache a function's JSON-serialisable result by its arguments."""

    def wrap(fn):
        def inner(*args, **kwargs):
            key = json.dumps([args, kwargs], sort_keys=True, default=str)
            path = _path(namespace, key)
            if os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl_seconds:
                with open(path) as f:
                    return json.load(f)
            result = fn(*args, **kwargs)
            try:
                with open(path, "w") as f:
                    json.dump(result, f)
            except (TypeError, OSError):
                pass
            return result

        return inner

    return wrap
