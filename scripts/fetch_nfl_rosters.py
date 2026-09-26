#!/usr/bin/env python3
"""
fetch_nfl_rosters.py — NFL roster snapshot + diff (offseason churn tracker).

Why: NFL is offseason but rosters are moving NOW, and September's model hazard
is exactly the churn that happens in July/August (QB changes above all). Each
run snapshots every team's roster from ESPN (free); when a previous snapshot
exists it writes a diff — players added/removed per team, QB room changes
called out separately, and a churn share — so at kickoff the model knows which
teams last season's data still describes and which it doesn't.

Files:
  data/nfl_rosters.json         — latest snapshot (replaces previous)
  data/nfl_roster_changes.json  — diff vs the snapshot it replaced (append-run log)

Run: python3 scripts/fetch_nfl_rosters.py   (weekly during offseason is plenty)
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SNAP = Path(__file__).parent.parent / "data" / "nfl_rosters.json"
DIFF = Path(__file__).parent.parent / "data" / "nfl_roster_changes.json"
API = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
UA = {"User-Agent": "Mozilla/5.0"}


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def team_ids() -> list[tuple[str, str]]:
    doc = get(f"{API}/teams?limit=40")
    out = []
    for grp in doc.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", []):
        t = grp.get("team") or {}
        if t.get("id") and t.get("displayName"):
            out.append((t["id"], t["displayName"]))
    return out


def fetch_roster(team_id: str) -> list[dict]:
    doc = get(f"{API}/teams/{team_id}/roster")
    players = []
    for group in doc.get("athletes", []):
        for p in group.get("items", []):
            players.append({
                "name": p.get("fullName"),
                "pos": (p.get("position") or {}).get("abbreviation"),
                "exp": (p.get("experience") or {}).get("years"),
            })
    return players


def diff_rosters(old: dict, new: dict) -> dict:
    """Per-team added/removed (by name), QB room changes, churn share."""
    teams = {}
    for team, roster in new.items():
        old_roster = old.get(team) or []
        old_names = {p["name"] for p in old_roster if p.get("name")}
        new_names = {p["name"] for p in roster if p.get("name")}
        added = sorted(new_names - old_names)
        removed = sorted(old_names - new_names)
        if not added and not removed:
            continue
        qb_new = {p["name"] for p in roster if p.get("pos") == "QB"}
        qb_old = {p["name"] for p in old_roster if p.get("pos") == "QB"}
        entry = {
            "added": added, "removed": removed,
            "churn_share": round(len(set(added) | set(removed)) /
                                 max(len(old_names | new_names), 1), 3),
        }
        if qb_new != qb_old:
            entry["qb_changes"] = {"in": sorted(qb_new - qb_old),
                                   "out": sorted(qb_old - qb_new)}
        teams[team] = entry
    return teams


def main() -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rosters = {}
    for tid, name in team_ids():
        try:
            rosters[name] = fetch_roster(tid)
        except Exception as e:                                 # noqa: BLE001
            print(f"  {name}: fetch failed ({e}) — skipped", file=sys.stderr)
    if len(rosters) < 30:
        print(f"only {len(rosters)} team rosters — aborting, keeping old snapshot",
              file=sys.stderr)
        return 1

    prev = None
    if SNAP.exists():
        try:
            prev = json.loads(SNAP.read_text())
        except (OSError, json.JSONDecodeError):
            prev = None

    if prev and prev.get("teams"):
        changes = diff_rosters(prev["teams"], rosters)
        log = []
        if DIFF.exists():
            try:
                log = json.loads(DIFF.read_text())
            except (OSError, json.JSONDecodeError):
                log = []
        log.append({"from": prev.get("fetched_at"), "to": now, "teams": changes})
        DIFF.write_text(json.dumps(log, indent=1, ensure_ascii=False))
        qb_moves = sum(1 for t in changes.values() if "qb_changes" in t)
        print(f"diff vs {prev.get('fetched_at')}: {len(changes)} teams changed, "
              f"{qb_moves} QB rooms moved -> {DIFF.name}")
    else:
        print("first snapshot — no previous to diff against")

    SNAP.write_text(json.dumps({"fetched_at": now,
                                "source": "ESPN NFL rosters (free)",
                                "teams": rosters}, indent=1, ensure_ascii=False))
    total = sum(len(r) for r in rosters.values())
    print(f"wrote {SNAP.name}: {len(rosters)} teams, {total} players")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
