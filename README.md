# Venn

**Find the overlap between your crowd and the next band they'll love.**

Live demo: https://venn-booking.onrender.com

Venn is an AI booking co-pilot for independent music venues (100–500 capacity). Big promoters have data teams to decide who to book; the person booking a small club has gut instinct and an inbox of pitches. Existing tools show how *popular* an artist is in a city. Venn answers the question bookers actually have: **will my crowd love them?**

Venn doesn't replace the booker's taste. It does the research behind it, and shows its receipts.

Built for the Qloo Agentic Hackathon.

## What it does

Enter a venue (and optionally a few artists who sold well for you). The agent:

1. **Reads the room.** Pulls the venue's recent shows from setlist.fm to learn what its crowd buys tickets for, or uses the booker's own best sellers for venues with little public history.
2. **Matches taste with Qloo.** Finds artists that fans of those past acts love, weighted toward the venue's city.
3. **Keeps it bookable.** Filters out acts too big for a small room and legacy acts, and highlights rising artists.
4. **Checks momentum.** Has the artist played nearby recently, but not at this room?
5. **Checks routing.** Finds real open dates between two nearby upcoming tour stops, when they exist.
6. **Builds the bill.** Pairs each headliner with an opener whose fans overlap.
7. **Plans promotion.** Suggests local co-promotion partners using Qloo's cross-domain data (places and brands).
8. **Writes the outreach.** Drafts the offer email and a one-page **pitch sheet** for the artist's agent.

Every pick shows its evidence: a taste-overlap diagram, chips naming the room's past acts whose fans connect to the artist, and touring facts.

A **"Compare with a generic AI"** button shows what the same model suggests with no Qloo data. It can name plausible bands, but it can't show why they fit *this* room.

## Why it needs Qloo

A plain LLM can name popular bands in a genre. It can't tell you that fans of Broncho and The Tubs, in Chicago specifically, show a very strong taste match with Dehd. Venn uses Qloo in four ways:

| Use | Qloo call |
|---|---|
| Seed the room's taste from its history | `GET /search` (exact-match artist entities) |
| Find artists this crowd loves, near the venue | `GET /v2/insights` with `signal.interests.entities` + `signal.location.query` |
| Pair openers by fan overlap | `GET /v2/insights` seeded with the headliner |
| Co-promotion partners | `GET /v2/insights` with `filter.type` = place / brand |

## Built to be honest

- No invented numbers. Taste is shown as Qloo affinity tiers ("very strong match"), never as ticket sales or made-up percentages.
- Routing is shown as pitch windows, never "available." Offer emails ask about radius clauses.
- Acts Qloo doesn't know are skipped, not guessed.

## Architecture

```
Browser (static/index.html)
   │  streams agent steps (Server-Sent Events)
FastAPI (app/main.py)  ── rate limits, demo results, generic-AI comparison
   │
Agent loop (app/agent.py) ── Claude tool use, 8 tools (app/tools.py)
   ├── Qloo        (app/qloo.py)         taste graph, images
   ├── setlist.fm  (app/setlistfm.py)    venue history, recent shows
   └── Ticketmaster(app/ticketmaster.py) upcoming tour dates
```

- `app/tools.py`: the agent's tools, plus the bookability filter (Qloo popularity and artist start year).
- `scripts/make_demos.py`: pre-runs the example venues so judges see results instantly (`demo/*.json`).
- `scripts/smoke_test.py`: runs the data pipeline without the LLM.

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add your keys
python -m scripts.smoke_test "Empty Bottle" Chicago   # check the data APIs
python -m uvicorn app.main:app --reload --port 8001
```

Open http://127.0.0.1:8001

### Keys
- `QLOO_API_KEY`, `QLOO_BASE_URL`: Qloo hackathon developer guide
- `SETLISTFM_API_KEY`: https://www.setlist.fm/settings/api (free, non-commercial)
- `TICKETMASTER_API_KEY`: https://developer.ticketmaster.com (Consumer Key)
- `ANTHROPIC_API_KEY`, `LLM_MODEL`: https://console.anthropic.com

Optional limits for a public deployment: `LIVE_RUNS_PER_HOUR` (default 5 per visitor), `GLOBAL_RUNS_PER_HOUR` (60), `MAX_CONCURRENT_RUNS` (3).

## Known limitations

- setlist.fm is fan-maintained, so small venues may have few logged shows (the best-seller input covers this).
- Ticketmaster lists few small-venue shows, so exact routing gaps are rare; regional momentum from setlist.fm fills in.
- Qloo coverage is thinner for very small local acts; Venn seeds from the acts Qloo does know.

## What's next

"Fill my dead night" search for empty weeknights, a deal calculator using the booker's own numbers, watchlist alerts when a good-fit artist announces nearby dates, and syncing with ticketing systems so Venn learns from real turnout.

## Credits

Taste data from [Qloo](https://www.qloo.com). Venue history and recent shows from [setlist.fm](https://www.setlist.fm). Tour dates from Ticketmaster.

## License

MIT
