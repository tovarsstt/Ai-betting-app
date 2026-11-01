"""Endpoint inventory from a page_recorder.js dump (our adaptation of REA's captured-traffic -> API inventory idea, https://github.com/morluto/rea).

Groups captured events by (kind, path, GraphQL operation), counts calls, sums bytes and odds-looking numbers, and keeps one response shape per group, so
"which request actually carries the prices?" is answered by data instead of guessing. Reads only the metadata recorder output (no headers, no bodies).

Usage: python3 scripts/web_capture/analyze_capture.py dump.json
"""
import sys, json
from collections import defaultdict
from urllib.parse import urlparse

ODDS_MIN_HITS = 3          # a group needs at least this many price-like numbers to be called odds-bearing


def group_key(e: dict) -> tuple:
    path = urlparse(e.get("url", "")).path
    return (e.get("kind", "?"), e.get("method", ""), path, e.get("op") or "-")


def inventory(events: list) -> list:
    g = defaultdict(lambda: {"calls": 0, "bytes": 0, "odds_hits": 0, "frames": 0, "statuses": set(), "shape": None})
    for e in events:
        r = g[group_key(e)]
        r["calls"] += 1
        r["bytes"] += e.get("bytes") or 0
        r["odds_hits"] += e.get("odds_hits") or 0
        r["frames"] += e.get("frames") or 0
        if e.get("status") is not None:
            r["statuses"].add(e["status"])
        r["shape"] = r["shape"] or e.get("shape") or e.get("sample_shape")
    out = []
    for (kind, method, path, op), r in g.items():
        out.append({"kind": kind, "method": method, "path": path, "op": op, "calls": r["calls"], "bytes": r["bytes"], "odds_hits": r["odds_hits"],
                    "frames": r["frames"], "statuses": sorted(r["statuses"]), "carries_odds": r["odds_hits"] >= ODDS_MIN_HITS, "shape_top": sorted((r["shape"] or {}).keys()) if isinstance(r["shape"], dict) else None})
    return sorted(out, key=lambda x: (-x["odds_hits"], -x["bytes"]))


def verdict(inv: list) -> str:
    odds = [r for r in inv if r["carries_odds"]]
    if odds:
        return "odds-bearing: " + ", ".join(f"{r['kind']} {r['path']} ({r['op']})" for r in odds[:3])
    ws = [r for r in inv if r["kind"] == "ws"]
    if not ws:
        return "no price-bearing request seen: prices likely arrive over a socket/widget opened BEFORE the recorder (read the DOM instead, or record from a fresh load)"
    return "sockets seen but no price-like numbers in JSON frames (binary or non-standard framing)"


if __name__ == "__main__":
    d = json.load(open(sys.argv[1]))
    inv = inventory(d["events"])
    for r in inv[:25]:
        print(f"{r['kind']:5s} {r['method']:5s} {r['path'][:60]:60s} op={r['op'][:20]:20s} calls={r['calls']:3d} bytes={r['bytes']:7d} odds={r['odds_hits']:4d}")
    print("->", verdict(inv))
