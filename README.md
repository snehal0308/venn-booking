# Indie Venue Booker

**Live Nation has a data team. The 200-cap club down the street has this.**

An AI booking agent for independent music venues. Give it a venue; it reads the room's
booking history, uses **Qloo's taste graph** to find artists the venue's crowd and
neighborhood will actually buy tickets for, checks real tour routing for open dates,
pairs an opener with overlapping fans, and drafts the offer email.

Built for the Qloo Agentic Hackathon.

## Why it needs Qloo
A plain LLM can name popular bands in a genre. It can't tell you which emerging artists
the fans of *this room's* best shows love, weighted to *this neighborhood*. Every
recommendation cites the Qloo affinity, venue-history and routing evidence behind it.

## How it works
1. `get_venue_profile`: past shows from setlist.fm, the room's taste fingerprint
2. `resolve_artists`: map them to Qloo entities
3. `get_local_taste` / `find_candidate_artists`: Qloo Insights with interest + location signals
4. `find_routing_gaps`: Ticketmaster tour dates, open nights between nearby stops
5. `find_openers`: smaller acts with overlapping audiences
6. `find_copromo_partners`: Qloo cross-domain (places, brands) for local co-promotion
7. `submit_booking_plan`: structured plan with evidence and offer emails

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your keys
python -m scripts.smoke_test   # verify APIs first
uvicorn app.main:app --reload
```
Open http://localhost:8000

## Keys
- Qloo: hackathon developer guide
- setlist.fm: https://api.setlist.fm (free)
- Ticketmaster Discovery: https://developer.ticketmaster.com (free)
- Anthropic: https://console.anthropic.com

## Deploy
Push to GitHub, create a Render "Blueprint" from `render.yaml`, add the keys.

## License
MIT
