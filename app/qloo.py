"""Qloo API client (verified against the hackathon API on 2026-10-24).

Confirmed working:
  GET {base}/search?query=...&types=urn:entity:artist&take=N
  GET {base}/v2/insights?filter.type=urn:entity:artist
                         &signal.interests.entities=<id,id>
                         &signal.location.query=Chicago
Response: results.entities[] with name, entity_id, popularity (0-1 percentile,
most artists > 0.9), query.affinity (0-1), tags, properties.start_year.
"""
from __future__ import annotations

import requests

from .cache import cached
from .config import QLOO_API_KEY, QLOO_BASE_URL

ARTIST = "urn:entity:artist"
PLACE = "urn:entity:place"
BRAND = "urn:entity:brand"


class QlooError(RuntimeError):
    pass


def _get(path: str, params: dict) -> dict:
    if not QLOO_API_KEY:
        raise QlooError("QLOO_API_KEY is not set")
    resp = requests.get(
        f"{QLOO_BASE_URL}{path}",
        params={k: v for k, v in params.items() if v not in (None, "", [])},
        headers={"X-Api-Key": QLOO_API_KEY, "Accept": "application/json"},
        timeout=25,
    )
    if resp.status_code >= 400:
        raise QlooError(f"Qloo {resp.status_code} on {path}: {resp.text[:300]}")
    return resp.json()


def _entities(payload: dict) -> list[dict]:
    """Normalise response shapes into a flat, compact list of entities."""
    results = payload.get("results", payload)
    if isinstance(results, dict):
        results = results.get("entities", [])
    out = []
    for e in results or []:
        props = e.get("properties") or {}
        out.append(
            {
                "id": e.get("entity_id") or e.get("id"),
                "name": e.get("name"),
                "popularity": round(e["popularity"], 3) if e.get("popularity") is not None else None,
                "affinity": round((e.get("query") or {}).get("affinity") or 0, 3) or None,
                "start_year": props.get("start_year"),
                "image": (props.get("image") or {}).get("url"),
                "tags": [t.get("name") for t in (e.get("tags") or [])][:6],
            }
        )
    return out


def _norm(s: str | None) -> str:
    s = (s or "").lower().strip()
    return s[4:] if s.startswith("the ") else s


@cached("qloo-search")
def search(query: str, entity_type: str = ARTIST, limit: int = 5) -> list[dict]:
    data = _get("/search", {"query": query, "types": entity_type, "take": limit})
    return _entities(data)


def resolve(name: str, entity_type: str = ARTIST) -> dict | None:
    """Exact-name match only. Search is fuzzy, and a wrong seed poisons recommendations."""
    for hit in search(name, entity_type):
        if _norm(hit["name"]) == _norm(name):
            return hit
    return None


@cached("qloo-insights")
def insights(
    filter_type: str = ARTIST,
    interest_ids: list[str] | None = None,
    location_query: str | None = None,
    take: int = 20,
    extra: dict | None = None,
) -> list[dict]:
    params = {
        "filter.type": filter_type,
        "signal.interests.entities": ",".join(interest_ids or []),
        "signal.location.query": location_query,
        "take": take,
    }
    params.update(extra or {})
    return _entities(_get("/v2/insights", params))


def local_artist_taste(location: str, take: int = 25) -> list[dict]:
    return insights(ARTIST, location_query=location, take=take)


def similar_artists_near(seed_ids: list[str], location: str, take: int = 50) -> list[dict]:
    return insights(ARTIST, interest_ids=seed_ids, location_query=location, take=take)


def cross_domain(seed_ids: list[str], filter_type: str, location: str | None = None, take: int = 10) -> list[dict]:
    return insights(filter_type, interest_ids=seed_ids, location_query=location, take=take)
