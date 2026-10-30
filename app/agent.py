"""The booking agent: an LLM tool-use loop grounded in Qloo + real touring data."""
from __future__ import annotations

import json
from typing import Callable

import anthropic

from . import qloo
from .config import ANTHROPIC_API_KEY, LLM_MODEL
from .tools import REGISTRY, SCHEMAS

SYSTEM = """You are the booking brain for an independent music venue (capacity ~100-500).
Your job: recommend 3 shows this venue should book, who to pair as opener, which date,
and draft the offer email.

Work like a real talent buyer:
1. Get the venue profile. Its most-booked artists are what this room's crowd buys tickets for.
2. Resolve 10-15 of those artists to Qloo IDs (prefer ones with repeat shows), then call
   find_candidate_artists with those IDs, the venue's city, and the venue's past artists as
   already_played. Optionally check get_local_taste for what over-indexes nearby.
3. Qloo popularity is a 0-1 percentile; almost everyone is above 0.9. Below ~0.95 is emerging.
   Prefer emerging and mid-size acts with high affinity. Candidates are pre-filtered to bookable acts.
4. Shortlist ~6 candidates and call check_regional_momentum. An artist who played nearby cities
   recently but never this venue is a strong pitch. Also try find_routing_gaps; it is often empty.
5. Pick an opener whose audience overlaps with the headliner (find_openers), ideally a local act.
6. Optionally find local co-promotion partners.
7. Call submit_booking_plan once with 3 recommendations. Every "why" must cite concrete evidence
   from tool results (named past acts, affinity, nearby shows), never generic genre talk.
   If data is missing, say so and lower confidence. Never invent dates or shows.

Ranking rules:
- At least 2 of the 3 headliners must be emerging (popularity < 0.95). Lead with the best one.
- Do not recommend an act whose recent shows are at arenas, stadiums or big festivals.
- A recent nearby show but no recent show at this venue is a strong signal. Say so plainly.
- Only call something a routing gap if find_routing_gaps returned it.

Writing rules (the reader is a busy venue booker scanning on a phone):
- venue_summary: max 2 sentences.
- why: max 40 words. Lead with the strongest fact. Name 1-2 past acts whose fans love this artist.
- routing_note: max 20 words. Only include it when there is positive news (a real open date or a
  recent nearby show). If nothing was found, leave routing_note out entirely.
- suggested_date: a short date or window, e.g. "Fri 20 Nov" or "next Midwest run".
- Never mention tool names, field names, "Qloo returned", or raw scores like 0.968.
  Say "very strong taste match" or "rising act" instead.
- offer_email: under 120 words, friendly and specific, signed "[Your name], Talent Buyer, <venue>".
- affinity: always fill in the headliner's Qloo affinity score from the candidate list.
- connected_acts: 1-3 real past acts of this venue (or the booker's list) that you used as seeds.
- evidence: 2-4 chips, each max 5 words, each backed by a tool result. No raw scores.
"""

MAX_STEPS = 14


def build_prompt(venue: str, city: str | None = None, notes: str | None = None, artists: str | None = None) -> str:
    prompt = f"Venue: {venue}" + (f", {city}" if city else "")
    names = [a.strip() for a in (artists or "").replace("\n", ",").split(",") if a.strip()]
    if names:
        prompt += (
            "\nThe booker says these artists sold well at this venue: " + ", ".join(names[:20]) + ".\n"
            "Treat them as the room's strongest taste signal: resolve them first and use them as the main "
            "seeds, alongside the venue's setlist.fm history if it exists. If the venue isn't on setlist.fm, "
            "continue with these artists and the city, and skip the momentum and routing checks."
        )
    if notes:
        prompt += f"\nBooker's notes: {notes}"
    return prompt


def _attach_images(plan: dict) -> dict:
    """Add Qloo artist photos to each recommendation (cached lookups, best effort)."""
    for rec in plan.get("recommendations", []):
        try:
            hit = qloo.resolve(rec.get("headliner", ""))
            if hit and hit.get("image"):
                rec["image"] = hit["image"]
        except Exception:
            pass
    return plan


def run(request: str, on_event: Callable[[dict], None] | None = None) -> dict:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": request}]
    emit = on_event or (lambda e: None)

    for _ in range(MAX_STEPS):
        resp = client.messages.create(
            model=LLM_MODEL,
            max_tokens=4096,
            system=SYSTEM,
            tools=SCHEMAS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        tool_results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            if block.name == "submit_booking_plan":
                emit({"type": "done"})
                return _attach_images(block.input)
            emit({"type": "tool", "name": block.name, "input": block.input})
            try:
                result = REGISTRY[block.name](**block.input)
            except Exception as exc:
                result = {"error": f"{type(exc).__name__}: {exc}"}
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str)[:12000],
                }
            )

        if not tool_results:
            messages.append({"role": "user", "content": "Please finish by calling submit_booking_plan."})
        else:
            messages.append({"role": "user", "content": tool_results})

    raise RuntimeError("Agent did not finish within the step limit")


def generic_picks(venue: str, city: str | None = None) -> list[dict]:
    """Baseline for comparison: the same model, same question, but no Qloo or venue data."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    where = f"{venue}, {city}" if city else venue
    resp = client.messages.create(
        model=LLM_MODEL,
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": f"I book shows at {where}, an independent music venue. "
                       "Recommend 3 artists I should book next, with one short sentence each on why. "
                       'Reply with only a JSON array like [{"artist": "...", "why": "..."}].',
        }],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        picks = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []
    return [p for p in picks if isinstance(p, dict) and p.get("artist")][:3]