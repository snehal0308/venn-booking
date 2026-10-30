"""Tools the booking agent can call. Each returns plain JSON-serialisable data."""
from __future__ import annotations

from . import qloo, setlistfm, ticketmaster

# Qloo popularity is a 0-1 percentile and most artists sit above 0.9.
# Above this, an act is usually too big (or too expensive) for a 100-500 cap room.
MAX_POPULARITY = 0.985
EMERGING_BELOW = 0.95
# Legacy acts (e.g. Grateful Dead, Tom Petty) show up via taste overlap but can't be booked.
MIN_START_YEAR = 2005


def _norm(s: str | None) -> str:
    s = (s or "").lower().strip()
    return s[4:] if s.startswith("the ") else s


def _bookable(cands: list[dict], exclude: set[str]) -> list[dict]:
    out = []
    for c in cands:
        if _norm(c["name"]) in exclude:
            continue
        if c.get("popularity") is not None and c["popularity"] > MAX_POPULARITY:
            continue
        if c.get("start_year") and c["start_year"] < MIN_START_YEAR:
            continue
        c = dict(c, emerging=(c.get("popularity") or 1) < EMERGING_BELOW)
        c.pop("image", None)
        out.append(c)
    return out


def get_venue_profile(venue_name: str, city: str | None = None) -> dict:
    venue = setlistfm.find_venue(venue_name, city)
    if not venue:
        return {"error": f"Venue '{venue_name}' not found on setlist.fm"}
    history = setlistfm.venue_history(venue["id"])
    return {"venue": venue, "recent_shows_count": sum(h["shows"] for h in history), "most_booked_artists": history}


def resolve_artists(names: list[str]) -> dict:
    """Map artist names to Qloo entity IDs (exact name matches only)."""
    resolved, unresolved = [], []
    for n in names[:20]:
        hit = qloo.resolve(n)
        if hit:
            resolved.append({"name": hit["name"], "id": hit["id"], "popularity": hit["popularity"], "tags": hit["tags"]})
        else:
            unresolved.append(n)
    return {"resolved": resolved, "not_in_qloo": unresolved}


def get_local_taste(location: str) -> list[dict]:
    """Bookable artists that over-index around this location per Qloo."""
    return _bookable(qloo.local_artist_taste(location, take=40), set())[:20]


def find_candidate_artists(seed_entity_ids: list[str], location: str, already_played: list[str] | None = None) -> list[dict]:
    """Artists loved by fans of the venue's past acts, weighted to the location, filtered to bookable acts."""
    exclude = {_norm(a) for a in (already_played or [])}
    cands = qloo.similar_artists_near(seed_entity_ids[:10], location, take=50)
    return _bookable(cands, exclude)[:20]


def check_regional_momentum(artist_names: list[str], venue_id: str, venue_lat: float, venue_lng: float) -> list[dict]:
    """From setlist.fm: has each artist played near this venue in the last year? Works for small acts."""
    out = []
    for name in artist_names[:8]:
        try:
            out.append(setlistfm.artist_momentum(name, venue_id, venue_lat, venue_lng))
        except Exception as exc:
            out.append({"artist": name, "error": str(exc)})
    return out


def find_routing_gaps(artist_names: list[str], venue_lat: float, venue_lng: float) -> list[dict]:
    """From Ticketmaster: open dates between two upcoming nearby tour stops. Sparse for small acts."""
    gaps = []
    for name in artist_names[:8]:
        try:
            gaps.extend(ticketmaster.routing_gaps(name, venue_lat, venue_lng))
        except Exception as exc:
            gaps.append({"artist": name, "error": str(exc)})
    return gaps


def find_openers(headliner_entity_id: str, location: str, exclude: list[str] | None = None) -> list[dict]:
    """Smaller artists whose fans overlap with the headliner's."""
    cands = _bookable(qloo.similar_artists_near([headliner_entity_id], location, take=40), {_norm(e) for e in exclude or []})
    return sorted(cands, key=lambda c: c.get("popularity") or 0)[:8]


def find_copromo_partners(seed_entity_ids: list[str], location: str) -> dict:
    strip = lambda xs: [{"name": x["name"], "affinity": x["affinity"], "tags": x["tags"][:3]} for x in xs]
    return {
        "places": strip(qloo.cross_domain(seed_entity_ids, qloo.PLACE, location)),
        "brands": strip(qloo.cross_domain(seed_entity_ids, qloo.BRAND, location)),
    }


REGISTRY = {
    "get_venue_profile": get_venue_profile,
    "resolve_artists": resolve_artists,
    "get_local_taste": get_local_taste,
    "find_candidate_artists": find_candidate_artists,
    "check_regional_momentum": check_regional_momentum,
    "find_routing_gaps": find_routing_gaps,
    "find_openers": find_openers,
    "find_copromo_partners": find_copromo_partners,
}

_str_list = {"type": "array", "items": {"type": "string"}}

SCHEMAS = [
    {
        "name": "get_venue_profile",
        "description": "Look up a venue (setlist.fm) and the artists it booked across its recent shows. Returns venue id, lat/lng.",
        "input_schema": {
            "type": "object",
            "properties": {"venue_name": {"type": "string"}, "city": {"type": "string"}},
            "required": ["venue_name"],
        },
    },
    {
        "name": "resolve_artists",
        "description": "Resolve artist names to Qloo entity IDs (exact matches only). Call before any taste query.",
        "input_schema": {"type": "object", "properties": {"names": _str_list}, "required": ["names"]},
    },
    {
        "name": "get_local_taste",
        "description": "Bookable artists that over-index around a location according to Qloo.",
        "input_schema": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]},
    },
    {
        "name": "find_candidate_artists",
        "description": "Main booking signal. Artists loved by fans of the seed artists, weighted to the venue's location, already filtered to acts a small room can book. Pass the venue's past artists as already_played.",
        "input_schema": {
            "type": "object",
            "properties": {"seed_entity_ids": _str_list, "location": {"type": "string"}, "already_played": _str_list},
            "required": ["seed_entity_ids", "location"],
        },
    },
    {
        "name": "check_regional_momentum",
        "description": "For candidate artists, check setlist.fm for shows near the venue in the last 12 months, and whether they've played this venue. Best routing signal for small acts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "artist_names": _str_list,
                "venue_id": {"type": "string"},
                "venue_lat": {"type": "number"},
                "venue_lng": {"type": "number"},
            },
            "required": ["artist_names", "venue_id", "venue_lat", "venue_lng"],
        },
    },
    {
        "name": "find_routing_gaps",
        "description": "Ticketmaster: exact open dates between two upcoming tour stops near the venue. Often empty for small acts; that's normal.",
        "input_schema": {
            "type": "object",
            "properties": {"artist_names": _str_list, "venue_lat": {"type": "number"}, "venue_lng": {"type": "number"}},
            "required": ["artist_names", "venue_lat", "venue_lng"],
        },
    },
    {
        "name": "find_openers",
        "description": "Smaller artists whose audience overlaps with a headliner's, near the venue.",
        "input_schema": {
            "type": "object",
            "properties": {"headliner_entity_id": {"type": "string"}, "location": {"type": "string"}, "exclude": _str_list},
            "required": ["headliner_entity_id", "location"],
        },
    },
    {
        "name": "find_copromo_partners",
        "description": "Local places and brands the bill's fans also love (Qloo cross-domain), for co-promotion.",
        "input_schema": {
            "type": "object",
            "properties": {"seed_entity_ids": _str_list, "location": {"type": "string"}},
            "required": ["seed_entity_ids", "location"],
        },
    },
    {
        "name": "submit_booking_plan",
        "description": "Submit the final plan. Call exactly once, at the end.",
        "input_schema": {
            "type": "object",
            "properties": {
                "venue_summary": {"type": "string", "description": "2-3 sentences on the room's taste fingerprint and neighborhood."},
                "recommendations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "headliner": {"type": "string"},
                            "opener": {"type": "string"},
                            "suggested_date": {"type": "string", "description": "A real open date if found, else a timing window like 'their next Midwest run'."},
                            "why": {"type": "string", "description": "Cite concrete evidence: which past acts' fans love them, Qloo affinity, momentum/routing."},
                            "affinity": {"type": "number", "description": "Qloo affinity score for the headliner (0-1)."},
                            "connected_acts": {**_str_list, "description": "1-3 of this venue's past acts (seeds you used) whose fans love this artist."},
                            "evidence": {**_str_list, "description": "2-4 short factual chips, max 5 words each, e.g. 'Rising act', 'Played Chicago Jul 2026', 'Not here recently', 'Chicago local'."},
                            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                            "routing_note": {"type": "string"},
                            "copromo": _str_list,
                            "offer_email": {"type": "string", "description": "Short, professional email to the artist's booking agent."},
                        },
                        "required": ["headliner", "why", "confidence", "offer_email"],
                    },
                },
            },
            "required": ["venue_summary", "recommendations"],
        },
    },
]