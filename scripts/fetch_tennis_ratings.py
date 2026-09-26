#!/usr/bin/env python3
"""
fetch_tennis_ratings.py — refresh the tennis player ratings the model prices on.

Pulls current ATP + WTA singles rankings from ESPN's public tennis API (free, no
key) and merges them into data/all_ratings.json under "Tennis" as
{displayName: {rank, points, tour}}. The tennis model is a rank-difference
logistic (edge_api /predict), so a current rank is all it needs to price a match
— this is what lets it cover WTA + current ATP instead of a stale men-only set.

Run: ./.venv/bin/python scripts/fetch_tennis_ratings.py   (refresh weekly)
ESPN rankings only carry the overall rank + points; surface-specific rank isn't
exposed here, and the model doesn't use surface yet (defaults Hard), so rank is
the field that matters.
"""
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"
RATINGS = DATA / "all_ratings.json"
META = DATA / "ratings_meta.json"   # freshness stamp — lets the model flag stale ranks
TOURS = ("atp", "wta")
# ESPN serves the OFFICIAL ATP/WTA ranking numbers (licensed) over a free, reliable
# JSON API. The official sites (atptour.com / wtatennis.com) are Cloudflare-gated and
# block scripted fetches, so ESPN is the honest way to pull official ranks weekly.
URL = "https://site.api.espn.com/apis/site/v2/sports/tennis/{}/rankings"


def fetch_tour(tour: str) -> dict:
    req = urllib.request.Request(URL.format(tour), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    out = {}
    for group in data.get("rankings", []):
        for rk in group.get("ranks", []):
            ath = rk.get("athlete") or {}
            name = ath.get("displayName")
            cur = rk.get("current")
            if name and cur:
                out[name] = {"rank": float(cur), "points": rk.get("points"),
                             "tour": tour.upper()}
        break  # first group = singles rankings
    return out


def main() -> None:
    allr = json.load(open(RATINGS))
    tennis = dict(allr.get("Tennis") or {})
    added = updated = 0
    counts: dict[str, int] = {}
    for tour in TOURS:
        feed = fetch_tour(tour)
        counts[tour] = len(feed)
        # A tour that returns nothing (ESPN hiccup) must NOT wipe existing ranks.
        if not feed:
            print(f"  {tour.upper()}: 0 fetched — keeping existing ranks (no overwrite)")
            continue
        for name, info in feed.items():
            if name in tennis:
                tennis[name] = {**tennis[name], **info}
                updated += 1
            else:
                tennis[name] = info
                added += 1
        print(f"  {tour.upper()}: {len(feed)} ranked players fetched")
    allr["Tennis"] = tennis
    json.dump(allr, open(RATINGS, "w"), ensure_ascii=False)
    # Freshness stamp — only when at least one tour actually refreshed.
    if any(counts.values()):
        META.write_text(json.dumps({
            "tennis": {
                "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "atp": counts.get("atp", 0), "wta": counts.get("wta", 0),
                "players": len(tennis), "source": "ESPN (official ATP/WTA ranks)",
            }
        }, indent=2))
    print(f"merged -> Tennis now {len(tennis)} players (+{added} new, {updated} updated)")
    print("restart edge_api (or kill :8001 — server.ts respawns) to load the new ranks")


if __name__ == "__main__":
    main()
