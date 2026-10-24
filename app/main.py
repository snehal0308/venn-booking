"""FastAPI app: serves the UI and streams the agent's progress over Server-Sent Events."""
from __future__ import annotations

import json
import queue
import threading

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent

app = FastAPI(title="Venn")
app.mount("/static", StaticFiles(directory="static"), name="static")


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


@app.post("/api/book")
def book(req: BookRequest):
    prompt = f"Venue: {req.venue}" + (f", {req.city}" if req.city else "")
    if req.notes:
        prompt += f"\nBooker's notes: {req.notes}"

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
