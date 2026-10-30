"""FastAPI app: serves the UI and streams the agent's progress over Server-Sent Events."""
from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
import traceback
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent

app = FastAPI(title="Venn")
app.mount("/static", StaticFiles(directory="static"), name="static")
DEMO_DIR = Path("demo")

# --- Protection for a public demo: per-visitor limits, a global cap, and a concurrency cap. ---
LIVE_RUNS_PER_HOUR = int(os.getenv("LIVE_RUNS_PER_HOUR", "5"))
GENERIC_RUNS_PER_HOUR = int(os.getenv("GENERIC_RUNS_PER_HOUR", "10"))
GLOBAL_RUNS_PER_HOUR = int(os.getenv("GLOBAL_RUNS_PER_HOUR", "60"))
_running = threading.BoundedSemaphore(int(os.getenv("MAX_CONCURRENT_RUNS", "3")))
_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()

FRIENDLY_ERROR = "Venn couldn't finish researching this venue. Please try again, or use the instant examples above."


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _allow(key: str, limit: int, window: int = 3600) -> bool:
    now = time.time()
    with _hits_lock:
        hits = _hits[key]
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True


class BookRequest(BaseModel):
    venue: str
    city: str | None = None
    notes: str | None = None  # e.g. "need a Thursday in March", "max guarantee $1,500"
    artists: str | None = None  # artists that sold well, comma or newline separated


class GenericRequest(BaseModel):
    venue: str
    city: str | None = None


@app.get("/")
def index():
    return FileResponse("static/index.html", headers={"Cache-Control": "no-cache"})


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/demo/{slug}")
def demo(slug: str):
    """Saved results for the example venues, so judges see a result instantly."""
    path = DEMO_DIR / f"{slug}.json"
    if not re.fullmatch(r"[a-z0-9-]+", slug) or not path.exists():
        raise HTTPException(status_code=404, detail="No saved demo")
    return JSONResponse(json.loads(path.read_text()))


@app.post("/api/generic")
def generic(req: GenericRequest, request: Request):
    """What a plain AI suggests with no Qloo data, for the side-by-side comparison."""
    if not _allow(f"generic:{_client_ip(request)}", GENERIC_RUNS_PER_HOUR):
        raise HTTPException(status_code=429, detail="Comparison limit reached for now. Try again later.")
    try:
        return {"picks": agent.generic_picks(req.venue[:120], (req.city or "")[:80] or None)}
    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail="Couldn't run the comparison right now.")


@app.post("/api/book")
def book(req: BookRequest, request: Request):
    if not req.venue.strip():
        raise HTTPException(status_code=400, detail="Please enter a venue name.")
    if not _allow(f"book:{_client_ip(request)}", LIVE_RUNS_PER_HOUR) or not _allow("book:global", GLOBAL_RUNS_PER_HOUR):
        raise HTTPException(
            status_code=429,
            detail="You've reached the live-run limit for now. The instant examples above still work.",
        )
    if not _running.acquire(blocking=False):
        raise HTTPException(
            status_code=503,
            detail="Venn is busy with other searches. Try again in a minute, or use the instant examples above.",
        )

    prompt = agent.build_prompt(
        req.venue[:120], (req.city or "")[:80] or None, (req.notes or "")[:500] or None, (req.artists or "")[:1000] or None
    )
    q: queue.Queue = queue.Queue()

    def worker():
        try:
            plan = agent.run(prompt, on_event=q.put)
            q.put({"type": "plan", "plan": plan})
        except Exception:
            traceback.print_exc()
            q.put({"type": "error", "message": FRIENDLY_ERROR})
        finally:
            _running.release()
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        while (item := q.get()) is not None:
            yield f"data: {json.dumps(item, default=str)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")