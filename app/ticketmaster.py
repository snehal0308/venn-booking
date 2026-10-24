"""Ticketmaster Discovery API: where is an artist already touring?
Free key: https://developer.ticketmaster.com/
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import requests

from .cache import cached
from .config import ROUTING_RADIUS_KM, TICKETMASTER_API_KEY

BASE = "https://app.ticketmaster.com/discovery/v2"


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@cached("tm-tour", ttl_seconds=60 * 60 * 6)
def upcoming_dates(artist: str, months_ahead: int = 4) -> list[dict]:
    if not TICKETMASTER_API_KEY:
        return []
    start = date.today()
    end = start + timedelta(days=30 * months_ahead)
    resp = requests.get(
        f"{BASE}/events.json",
        params={
            "apikey": TICKETMASTER_API_KEY,
            "keyword": artist,
            "classificationName": "music",
            "startDateTime": f"{start}T00:00:00Z",
            "endDateTime": f"{end}T23:59:59Z",
            "size": 50,
            "sort": "date,asc",
        },
        timeout=20,
    )
    resp.raise_for_status()
    events = resp.json().get("_embedded", {}).get("events", [])
    out = []
    for e in events:
        attractions = [a.get("name", "") for a in e.get("_embedded", {}).get("attractions", [])]
        if not any(artist.lower() == a.lower() for a in attractions):
            continue  # keyword search is fuzzy; keep only real matches
        v = (e.get("_embedded", {}).get("venues") or [{}])[0]
        loc = v.get("location") or {}
        out.append(
            {
                "date": e.get("dates", {}).get("start", {}).get("localDate"),
                "venue": v.get("name"),
                "city": (v.get("city") or {}).get("name"),
                "lat": float(loc["latitude"]) if loc.get("latitude") else None,
                "lng": float(loc["longitude"]) if loc.get("longitude") else None,
            }
        )
    return out


MAX_GAP_DAYS = 5  # a real routing gap is a few days between shows, not the end of a tour


def routing_gaps(artist: str, venue_lat: float, venue_lng: float) -> list[dict]:
    """Open nights between two nearby tour stops = a natural offer date for this venue."""
    stops = [s for s in upcoming_dates(artist) if s["date"] and s["lat"] is not None]
    gaps = []
    for a, b in zip(stops, stops[1:]):
        d1, d2 = date.fromisoformat(a["date"]), date.fromisoformat(b["date"])
        if not 2 <= (d2 - d1).days <= MAX_GAP_DAYS:
            continue
        dist_a = haversine_km(a["lat"], a["lng"], venue_lat, venue_lng)
        dist_b = haversine_km(b["lat"], b["lng"], venue_lat, venue_lng)
        if max(dist_a, dist_b) <= ROUTING_RADIUS_KM * 1.5 and min(dist_a, dist_b) <= ROUTING_RADIUS_KM:
            gaps.append(
                {
                    "artist": artist,
                    "between": [a, b],
                    "open_dates": [str(d1 + timedelta(days=i)) for i in range(1, (d2 - d1).days)],
                    "nearest_stop_km": round(min(dist_a, dist_b)),
                }
            )
    return gaps