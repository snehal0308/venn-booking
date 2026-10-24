"""setlist.fm client.

- A venue's past shows = its taste fingerprint.
- An artist's recent shows = where they're already touring (regional momentum).
Free API key: https://www.setlist.fm/settings/api  (limit ~2 requests/sec)
"""
from __future__ import annotations

import time
from collections import Counter
from datetime import date, datetime, timedelta

import requests

from .cache import cached
from .config import ROUTING_RADIUS_KM, SETLISTFM_API_KEY

BASE = "https://api.setlist.fm/rest/1.0"
_last_call = [0.0]


def _get(path: str, params: dict) -> dict:
    resp = None
    for attempt in range(4):
        wait = 0.6 - (time.time() - _last_call[0])  # stay under ~2 requests/sec
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        resp = requests.get(
            f"{BASE}{path}",
            params=params,
            headers={"x-api-key": SETLISTFM_API_KEY, "Accept": "application/json"},
            timeout=20,
        )
        if resp.status_code == 429:
            time.sleep(2 ** attempt)  # back off: 1s, 2s, 4s, 8s
            continue
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()
    return {}


def _norm(s: str | None) -> str:
    s = (s or "").lower().strip()
    return s[4:] if s.startswith("the ") else s


def _parse_date(d: str | None) -> date | None:
    try:
        return datetime.strptime(d, "%d-%m-%Y").date()  # setlist.fm uses dd-MM-yyyy
    except (TypeError, ValueError):
        return None


@cached("sfm-venue")
def find_venue(name: str, city: str | None = None) -> dict | None:
    target = _norm(name)
    venues: list[dict] = []
    for q in {name, target}:  # search both "The Empty Bottle" and "empty bottle"
        data = _get("/search/venues", {"name": q, "cityName": city or ""})
        for v in data.get("venue", []):
            if v["id"] not in {x["id"] for x in venues}:
                venues.append(v)
    if not venues:
        return None

    def score(v):
        n = _norm(v.get("name"))
        return (n == target, n.startswith(target), -len(n))

    v = max(venues, key=score)  # exact match first, then shortest similar name
    c = v.get("city", {})
    coords = c.get("coords", {})
    return {
        "id": v["id"],
        "name": v["name"],
        "city": c.get("name"),
        "state": c.get("stateCode"),
        "country": c.get("country", {}).get("code"),
        "lat": coords.get("lat"),
        "lng": coords.get("long"),
    }


@cached("sfm-history")
def venue_history(venue_id: str, pages: int = 8) -> list[dict]:
    """Most-booked artists at the venue over its last ~pages*20 shows."""
    counts: Counter = Counter()
    last_seen: dict[str, str] = {}
    for page in range(1, pages + 1):
        data = _get(f"/venue/{venue_id}/setlists", {"p": page})
        setlists = data.get("setlist", [])
        for s in setlists:
            artist = s.get("artist", {}).get("name")
            if not artist:
                continue
            counts[artist] += 1
            last_seen.setdefault(artist, s.get("eventDate"))
        if not setlists:
            break
    return [
        {"artist": a, "shows": n, "last_played": last_seen.get(a)}
        for a, n in counts.most_common(40)
    ]


def _km(lat1, lng1, lat2, lng2) -> float:
    from .ticketmaster import haversine_km

    return haversine_km(lat1, lng1, lat2, lng2)


@cached("sfm-momentum", ttl_seconds=60 * 60 * 12)
def artist_momentum(artist: str, venue_id: str, venue_lat: float, venue_lng: float, months: int = 12) -> dict:
    """Has this artist been playing near the venue recently? Have they played the venue itself?"""
    data = _get("/search/setlists", {"artistName": artist, "p": 1})
    cutoff = date.today() - timedelta(days=30 * months)
    nearby, total_recent, played_here = [], 0, False
    for s in data.get("setlist", []):
        if _norm(s.get("artist", {}).get("name")) != _norm(artist):
            continue  # artistName search is fuzzy
        d = _parse_date(s.get("eventDate"))
        if not d or d < cutoff:
            continue
        total_recent += 1
        v = s.get("venue", {})
        if v.get("id") == venue_id:
            played_here = True
        coords = (v.get("city") or {}).get("coords") or {}
        if coords.get("lat") is None:
            continue
        km = _km(venue_lat, venue_lng, coords["lat"], coords["long"])
        if km <= ROUTING_RADIUS_KM:
            nearby.append({"date": str(d), "venue": v.get("name"), "city": (v.get("city") or {}).get("name"), "km": round(km)})
    return {
        "artist": artist,
        "recent_shows_found": total_recent,
        "nearby_recent_shows": nearby[:6],
        "has_played_this_venue_recently": played_here,
    }
