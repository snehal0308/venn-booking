"""Run Venn's data pipeline end to end WITHOUT the LLM, to check data quality.

Run:  python -m scripts.smoke_test "Empty Bottle" Chicago
"""
import sys
import time

from app import tools


def main(venue_name="Empty Bottle", city="Chicago"):
    t0 = time.time()
    prof = tools.get_venue_profile(venue_name, city)
    if "error" in prof:
        print(prof["error"])
        return
    v = prof["venue"]
    hist = prof["most_booked_artists"]
    print(f"VENUE: {v['name']} ({v['city']}), id {v['id']}, {prof['recent_shows_count']} recent shows")
    print("  top past acts:", ", ".join(f"{h['artist']} x{h['shows']}" for h in hist[:12]))

    res = tools.resolve_artists([h["artist"] for h in hist[:15]])
    print(f"\nQLOO: resolved {len(res['resolved'])}, not in Qloo: {res['not_in_qloo']}")
    ids = [r["id"] for r in res["resolved"]]
    if not ids:
        print("No seeds resolved; stopping.")
        return

    cands = tools.find_candidate_artists(ids, v["city"], already_played=[h["artist"] for h in hist])
    print("\nCANDIDATES (bookable, ranked by Qloo affinity):")
    for c in cands[:15]:
        flag = "EMERGING" if c["emerging"] else ""
        print(f"  {c['name']:32} aff {c['affinity']}  pop {c['popularity']}  {c.get('start_year') or ''} {flag}")

    names = [c["name"] for c in cands[:6]]
    print("\nREGIONAL MOMENTUM (setlist.fm, last 12 months):")
    for m in tools.check_regional_momentum(names, v["id"], v["lat"], v["lng"]):
        if "error" in m:
            print(f"  {m['artist']}: error {m['error']}")
            continue
        near = "; ".join(f"{n['city']} {n['date']}" for n in m["nearby_recent_shows"][:3]) or "none nearby"
        print(f"  {m['artist']:32} {m['recent_shows_found']} recent shows | nearby: {near} | played here: {m['has_played_this_venue_recently']}")

    print(f"\nDone in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main(*sys.argv[1:3])
