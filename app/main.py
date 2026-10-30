"""FastAPI app: serves the UI and streams the agent's progress over Server-Sent Events."""
from __future__ import annotations

import json
import queue
import re
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent

app = FastAPI(title="Venn")
app.mount("/static", StaticFiles(directory="static"), name="static")
DEMO_DIR = Path("demo")


class BookRequest(BaseModel):
    venue: str
    city: str | None = None
    notes: str | None = None  # e.g. "need a Thursday in March", "max guarantee $1,500"


@app.get("/")
def index():
    return FileResponse("static/index.html")


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


@app.post("/api/book")
def book(req: BookRequest):
    prompt = agent.build_prompt(req.venue, req.city, req.notes)

    q: queue.Queue = queue.Queue()

    def worker():
        try:
            plan = agent.run(prompt, on_event=q.put)
            q.put({"type": "plan", "plan": plan})
        except Exception as exc:
            q.put({"type": "error", "message": str(exc)})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        while (item := q.get()) is not None:
            yield f"data: {json.dumps(item, default=str)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")