"""Run the agent on the example venues and save the results to demo/<slug>.json.

Run all:   python -m scripts.make_demos
Run one:   python -m scripts.make_demos empty-bottle
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

from app import agent

DEMOS = {
    "empty-bottle": ("Empty Bottle", "Chicago"),
    "mercury-lounge": ("Mercury Lounge", "New York"),
    "mohawk": ("Mohawk", "Austin"),
}


def main(slugs):
    out_dir = Path("demo")
    out_dir.mkdir(exist_ok=True)
    for slug in slugs:
        venue, city = DEMOS[slug]
        print(f"\n== {venue}, {city}")
        steps = []

        def on_event(e):
            if e.get("type") == "tool":
                steps.append(e["name"])
                print("  ->", e["name"])

        t0 = time.time()
        plan = agent.run(agent.build_prompt(venue, city), on_event=on_event)
        result = {"venue": venue, "city": city, "generated": str(date.today()), "steps": steps, "plan": plan}
        (out_dir / f"{slug}.json").write_text(json.dumps(result, indent=2))
        print(f"  saved demo/{slug}.json in {time.time() - t0:.0f}s")
        for r in plan.get("recommendations", []):
            print(f"  * {r.get('headliner')} [{r.get('confidence')}] with {r.get('opener')}")


if __name__ == "__main__":
    main(sys.argv[1:] or list(DEMOS))