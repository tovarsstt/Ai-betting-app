#!/usr/bin/env python3
"""
fetch_volleyball_rankings.py — official FIVB World Ranking + data-fitted win model.

Why: Jul 16 2026 the user dropped $80 on international volleyball the app had no
model for ("no data, no bet" gate now blocks it — this module EARNS the coverage
back with real data). Source is FIVB's own ranking API (the one their site uses):
  https://en.volleyballworld.com/api/v1/worldranking/volleyball/{gender}/0/50
gender: 1 = men, 0 = women (their page config: vWrConfig={men:1,women:0}).

Each team carries ~47 recent matches with the WR score of BOTH sides at match
time plus the set result — so the win-probability curve is FITTED BY MLE from
those real outcomes, never an invented constant:
  - k_match: logistic scale for P(match win) on WR-score diff
  - k_set:   logistic scale for P(single set win) (each set = one Bernoulli)
Both, with sample sizes and favorite-accuracy, are stored in meta so the model
can cite its own calibration. Free endpoint, no key — NOT Odds API quota.

Writes data/volleyball_ratings.json:
  {"meta": {...}, "men": {team: {rank, points}}, "women": {team: {rank, points}}}

Run: python3 scripts/fetch_volleyball_rankings.py
"""
from __future__ import annotations

import json
import math
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).parent.parent / "data" / "volleyball_ratings.json"
API = "https://en.volleyballworld.com/api/v1/worldranking/volleyball/{g}/0/50"
GENDERS = {"men": 1, "women": 0}
UA = {"User-Agent": "Mozilla/5.0"}


def fetch(gender_code: int) -> dict:
    req = urllib.request.Request(API.format(g=gender_code), headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def unique_matches(payloads: list[dict]) -> list[dict]:
    """Dedupe matches across all teams' lists (each match appears on both sides)."""
    seen: set = set()
    out = []
    for payload in payloads:
        for team in payload.get("teams", []):
            for m in team.get("teamMatches") or []:
                key = (m.get("localDate"), m.get("homeTeamCode"), m.get("awayTeamCode"))
                if key in seen:
                    continue
                seen.add(key)
                out.append(m)
    return out


def outcome_pairs(matches: list[dict]) -> tuple[list, list]:
    """(match_pairs, set_pairs): (wr_diff, home_won) per match / per individual set."""
    match_pairs, set_pairs = [], []
    for m in matches:
        try:
            hs, as_ = (int(x) for x in str(m["result"]).split("-"))
            diff = float(m["homeWRS"]) - float(m["awayWRS"])
        except (KeyError, ValueError, TypeError):
            continue
        if hs == as_:
            continue
        match_pairs.append((diff, 1 if hs > as_ else 0))
        set_pairs.extend([(diff, 1)] * hs + [(diff, 0)] * as_)
    return match_pairs, set_pairs


def fit_logistic_scale(pairs: list, k_lo=0.001, k_hi=0.08, steps=159) -> float:
    """MLE over a fine grid for k in P = 1/(1+exp(-k*diff)). Grid is enough:
    one-parameter concave likelihood, 0.0005 resolution."""
    best_k, best_ll = k_lo, -math.inf
    for i in range(steps + 1):
        k = k_lo + (k_hi - k_lo) * i / steps
        ll = 0.0
        for diff, won in pairs:
            p = 1.0 / (1.0 + math.exp(-k * diff))
            p = min(max(p, 1e-9), 1 - 1e-9)
            ll += math.log(p) if won else math.log(1.0 - p)
        if ll > best_ll:
            best_k, best_ll = k, ll
    return best_k


def favorite_accuracy(pairs: list) -> float:
    if not pairs:
        return 0.0
    return sum(1 for d, w in pairs if (d > 0) == (w == 1)) / len(pairs)


def main() -> int:
    payloads = {}
    for name, code in GENDERS.items():
        payloads[name] = fetch(code)
        if not payloads[name].get("teams"):
            print(f"FIVB API returned no {name} teams — aborting, keeping old file",
                  file=sys.stderr)
            return 1

    matches = unique_matches(list(payloads.values()))
    match_pairs, set_pairs = outcome_pairs(matches)
    if len(match_pairs) < 200:      # too thin to trust a fit — refuse to write junk
        print(f"only {len(match_pairs)} decided matches — not enough to fit, aborting",
              file=sys.stderr)
        return 1

    k_match = fit_logistic_scale(match_pairs)
    k_set = fit_logistic_scale(set_pairs)

    doc = {
        "meta": {
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "FIVB World Ranking API (en.volleyballworld.com)",
            "k_match": round(k_match, 4),
            "k_set": round(k_set, 4),
            "n_matches_fit": len(match_pairs),
            "n_sets_fit": len(set_pairs),
            "favorite_accuracy": round(favorite_accuracy(match_pairs), 4),
            "method": "logistic on WR-score diff, scale fitted by MLE on real results",
        },
    }
    for name in GENDERS:
        doc[name] = {
            t["name"]: {"rank": t["rank"], "points": round(float(t["decimalPoints"]), 2),
                        "code": t.get("teamCode") or t.get("federationCode")}
            for t in payloads[name]["teams"]
        }

    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    print(f"wrote {OUT.name}: {len(doc['men'])} men + {len(doc['women'])} women teams, "
          f"k_match={k_match:.4f} k_set={k_set:.4f} "
          f"(fit on {len(match_pairs)} matches / {len(set_pairs)} sets, "
          f"fav-acc {favorite_accuracy(match_pairs):.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
