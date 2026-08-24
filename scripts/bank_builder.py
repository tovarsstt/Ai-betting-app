#!/usr/bin/env python3
"""
bank_builder.py — constructs the 3-5x growth-lane ticket from model edges.

Why: rule 14 (global_heuristics) is the user's proven winning shape — 8/8 won,
+176% ROI: 2-3 legs across DIFFERENT soccer matches, every leg a probable event.
The slip linter judges tickets the user already built; nothing BUILT the ticket.
This closes that gap: feed it the board's model edges, it emits the best
combos in the bankroll-doubling lane, win-prob ranked, linter-approved.

Bankroll context (low capital, building bank): target combined odds 3.0-5.0 —
one hit trebles the stake. The proven pattern range 2.3-6.0 is the fallback
lane, flagged so the user knows it's off the preferred target.

Every number in = a model number (devig / Poisson). Never fabricates a price
or a probability. Pure local compute, no API calls, safe in dev/test.

CLI:  echo '{"candidates":[{"match":..,"selection":..,"decimal":..,"prob":..}]}' \
        | python3 scripts/bank_builder.py --json
"""
from __future__ import annotations

import json
import math

import model_gate as gate
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from slip_linter import lint  # every emitted ticket must survive the pre-bet gate
from staking import NORMAL_MIN  # 0.58 — the tier floor "bet more" already trusts

TARGET_MIN, TARGET_MAX = 3.0, 5.0    # user's growth lane: 3-5x the stake
PATTERN_MIN, PATTERN_MAX = 2.3, 6.0  # rule 14 proven range (8/8, +176% ROI)
MIN_LEG_PROB = 0.56                  # rule 14 floor: every leg a probable event
LEG_COUNTS = (2, 3)                  # the +ROI shape; 5+ legs bust (sim + record)
DEFAULT_TICKETS = 3

# Strong singles: 1.75+ pays enough to matter as a single (user directive);
# betting BIGGER demands 2.5x the +2% scan flag gate; quarter-Kelly because
# model probs carry error — full Kelly on an overestimated prob ruins banks.
SINGLE_MIN_ODDS = 1.75
SINGLE_MIN_EV = 0.05
KELLY_FRACTION = 0.25
KELLY_CAP_PCT = 3.0                  # never more than 3% of bank on one bet


def _leg_ok(c: dict) -> bool:
    """Gate a candidate leg: probable (>=56%), not -EV, and from a model that
    has not already been measured losing to the market.

    That last condition is rule 30 enforced rather than described. A leg whose
    probability comes from a model with negative measured ROI against real
    prices is not a 56% leg; it is a leg the model *believes* is 56% while the
    same belief has been shown to run ~6 sigma overconfident.
    """
    prob, dec = float(c["prob"]), float(c["decimal"])
    if not gate.allows_standalone(c.get("sport") or ""):
        return False
    return prob >= MIN_LEG_PROB and (prob * dec - 1.0) >= 0.0


def _ceil2(x: float) -> float:
    """Round UP to 2 decimals — a price floor must never understate."""
    return math.ceil(x * 100 - 1e-9) / 100


def _lane(combined: float) -> str | None:
    if TARGET_MIN <= combined <= TARGET_MAX:
        return "target"
    if PATTERN_MIN <= combined <= PATTERN_MAX:
        return "pattern"
    return None


def _ticket(legs: tuple) -> dict | None:
    """Score one combo; None if it's outside both lanes or the linter cuts it."""
    combined = joint = 1.0
    for l in legs:
        combined *= float(l["decimal"])
        joint *= float(l["prob"])   # independent — different matches enforced
    lane = _lane(combined)
    if lane is None:
        return None
    v = lint([{"decimal": l["decimal"], "selection": l["selection"]} for l in legs])
    if v.status != "ACCEPT":
        return None
    # min_odds = lowest price at YOUR book (Stake) where the bet stays +EV.
    # The feed's price found the edge; Stake's on-screen price decides the bet.
    return {
        "legs": [{**l, "min_odds": _ceil2(1.0 / float(l["prob"]))} for l in legs],
        "combined": round(combined, 2),
        "joint_prob": round(joint, 4),
        "min_combined": _ceil2(1.0 / joint),
        "ev_pct": round((joint * combined - 1.0) * 100, 1),
        "lane": lane,
        "verdict": v.status,
    }


def build_tickets(candidates: list[dict], n_tickets: int = DEFAULT_TICKETS) -> dict:
    """Best 2-3 leg cross-match tickets from model edges, win-prob ranked.

    Returned tickets never share a leg (Jodar rule: a leg cloned across slips
    is one bet bought N times — one soft leg dies, every slip dies).
    """
    pool = [c for c in candidates if _leg_ok(c)]
    scored = []
    for n in LEG_COUNTS:
        for legs in combinations(pool, n):
            if len({l["match"] for l in legs}) < n:   # one leg per match
                continue
            t = _ticket(legs)
            if t:
                scored.append(t)

    # Win-prob first (the directive), target lane before fallback, EV last.
    scored.sort(key=lambda t: (t["lane"] != "target", -t["joint_prob"], -t["ev_pct"]))

    picked: list[dict] = []
    used: set = set()
    for t in scored:
        keys = {(l["match"], l["selection"]) for l in t["legs"]}
        if keys & used:
            continue
        picked.append(t)
        used |= keys
        if len(picked) >= n_tickets:
            break

    return {
        "tickets": picked,
        "pass": not picked,
        "note": ("no combo makes the 2.3-6.0 lane with >=56% legs — "
                 "disciplined PASS, force nothing") if not picked else
                f"lane {TARGET_MIN}-{TARGET_MAX}x preferred; 'pattern' = proven "
                f"{PATTERN_MIN}-{PATTERN_MAX} range but off-target",
    }


def strong_singles(candidates: list[dict], bankroll: float | None = None) -> list[dict]:
    """Singles worth betting MORE on: 1.75+ odds AND >=58% model prob AND
    >=+5% EV. Stake = quarter-Kelly, capped at KELLY_CAP_PCT of bankroll.

    Honest math: at 1.75-2.2 a qualifying pick wins ~58-65% — the best value
    zone on a board, NOT a lock. Quarter-Kelly is how "bet more" stays safe.
    """
    out = []
    for c in candidates:
        dec, prob = float(c["decimal"]), float(c["prob"])
        ev = prob * dec - 1.0
        if not gate.allows_standalone(c.get("sport") or ""):
            continue                      # rule 30 — model loses to the price
        if dec < SINGLE_MIN_ODDS or prob < NORMAL_MIN or ev < SINGLE_MIN_EV:
            continue
        kelly = ev / (dec - 1.0)                      # full Kelly fraction
        stake_pct = round(min(kelly * KELLY_FRACTION * 100, KELLY_CAP_PCT), 2)
        single = {
            "match": c["match"],
            "selection": c["selection"],
            "decimal": dec,
            "prob": prob,
            "ev_pct": round(ev * 100, 1),
            "stake_pct": stake_pct,
            # bet on Stake only if its price >= this — keeps the +5% edge
            "min_odds": _ceil2((1.0 + SINGLE_MIN_EV) / prob),
            "kill": c.get("kill"),   # top model-priced way this leg dies
        }
        if bankroll is not None:
            single["stake_usd"] = round(bankroll * stake_pct / 100, 2)
        out.append(single)
    out.sort(key=lambda s: (-s["prob"], -s["ev_pct"]))  # win-prob first
    # One single per match: two sub-markets of one game as "singles" is a
    # stacked bet on the same game script (the Suiza-Argelia leak).
    seen: set = set()
    deduped = []
    for s in out:
        if s["match"] in seen:
            continue
        seen.add(s["match"])
        deduped.append(s)
    return deduped


# Per-match verdict gates: BET clears the scan flag gate on a probable event;
# LEAN is fair-or-better but thin; NO_BET is -EV — shown with the flip price,
# never staked. "A bet on every match" stays honest this way: every match gets
# an answer, only positive answers get money.
VERDICT_BET_EV = 0.02
VERDICT_BET_PROB = 0.56


def _verdict(prob: float, ev: float) -> str:
    if prob >= VERDICT_BET_PROB and ev >= VERDICT_BET_EV:
        return "BET"
    if ev >= 0.0:
        return "LEAN"
    return "NO_BET"


# ── Data gates (global rules 16 + 19) ────────────────────────────────────────
# /predict caps a pick's grade when the ratings behind it are stale or predate
# the season, and when the league has no MEASURED model skill. The day card used
# its own verdict and consulted neither, so the same fixture could read LEAN in
# /predict and a full BET here — two paths to one decision, disagreeing. These
# apply the same gates so the card can't be the loose one.

# Sport key (Odds-API style or plain) -> data_freshness keys it prices on.
_FRESHNESS_KEYS = {
    "soccer": ("soccer_club", "soccer_intl"),
    "tennis": ("tennis", "tennis_form"),
    "americanfootball_nfl": ("nfl",), "nfl": ("nfl",),
    "baseball_mlb": ("mlb",), "mlb": ("mlb",),
    "basketball_nba": ("nba",), "nba": ("nba",),
    "basketball_wnba": ("wnba",), "wnba": ("wnba",),
    "icehockey_nhl": (), "nhl": (),
}


def _freshness_flag(sport_key: str | None) -> str | None:
    """Worst freshness status for this sport, or None when it can't be judged."""
    if not sport_key:
        return None
    keys: tuple = ()
    for prefix, ks in _FRESHNESS_KEYS.items():
        if sport_key == prefix or sport_key.startswith(prefix):
            keys = ks
            break
    if not keys:
        return None
    try:
        import data_freshness as dfr
        sports = dfr.audit()["sports"]
    except Exception:
        return None
    statuses = [sports.get(k, {}).get("status") for k in keys if k in sports]
    for bad in ("MISSING", "SEASON_BOUNDARY", "STALE"):
        if bad in statuses:
            return bad
    return None


def apply_data_gate(rows: list[dict], sport_key: str | None) -> list[dict]:
    """Downgrade BET -> LEAN where the DATA doesn't support a confident call.

    Never upgrades, and never touches NO_BET. Returns new rows (no mutation).
    """
    flag = _freshness_flag(sport_key)
    if not flag:
        return rows
    reason = ("ratings predate the current season — roster/promotion changes not modelled"
              if flag == "SEASON_BOUNDARY" else
              f"ratings are {flag.lower()} — refresh before staking on this")
    out = []
    for r in rows:
        r = dict(r)
        if r.get("verdict") == "BET":
            r["verdict"] = "LEAN"
            r["data_gate"] = f"BET->LEAN (rule 16): {reason}"
        elif r.get("verdict") == "LEAN":
            r["data_gate"] = f"rule 16: {reason}"
        out.append(r)
    return out


def apply_model_gate(rows: list[dict], sport_key: str | None) -> list[dict]:
    """Force verdict -> NO_BET wherever rule 30 has this sport's model blocked.

    Stronger than apply_data_gate: a measured loss against the market is a
    negative-expectation finding, not a data-quality caveat, so a blocked
    sport never shows BET or LEAN here — only NO_BET, description only.
    """
    st = gate.status(_gate_sport(sport_key))
    if st["standalone_allowed"]:
        return rows
    out = []
    for r in rows:
        r = dict(r)
        if r.get("verdict") != "NO_BET":
            r["verdict"] = "NO_BET"
        r["model_gate"] = ("rule 30: model measured losing to the market price — "
                            "description only, not a bet")
        out.append(r)
    return out


def best_per_match(candidates: list[dict]) -> list[dict]:
    """EVERY match -> its single best option + honest verdict.

    Money-first ranking: among non-negative-EV options take the highest win
    probability; if the whole board is -EV take the least-bad (max EV) and
    mark it NO_BET. min_odds is the Stake price that flips the row to a BET
    (clears the +2% gate) — check the board, don't force the bet.
    """
    by_match: dict = {}
    for c in candidates:
        by_match.setdefault(c["match"], []).append(c)
    out = []
    for match, cands in by_match.items():
        scored = [(float(c["prob"]), float(c["prob"]) * float(c["decimal"]) - 1.0, c)
                  for c in cands]
        positive = [t for t in scored if t[1] >= 0.0]
        prob, ev, c = (max(positive, key=lambda t: (t[0], t[1])) if positive
                       else max(scored, key=lambda t: t[1]))
        out.append({
            "match": match,
            "selection": c["selection"],
            "decimal": float(c["decimal"]),
            "prob": round(prob, 4),
            "ev_pct": round(ev * 100, 1),
            "verdict": _verdict(prob, ev),
            "min_odds": _ceil2((1.0 + VERDICT_BET_EV) / prob),
            "kill": c.get("kill"),
        })
    out.sort(key=lambda m: (-m["prob"], -m["ev_pct"]))
    return out


def _gate_sport(sport_key: str | None) -> str:
    """Normalise an odds-api / UI sport key to the name model_gate.py measures.

    _leg_ok/strong_singles only block a candidate that CARRIES a "sport" —
    candidates built here previously had none, so the gate was silently a
    no-op for the live day card (both soccer's Poisson board and tennis's
    2-way feed). This is what tags them.
    """
    s = (sport_key or "").upper()
    if s.startswith("SOCCER"):
        return "SOCCER"
    if s.startswith("TENNIS"):
        return "TENNIS"
    return s


def candidates_from_slate(games: list[dict]) -> list[dict]:
    """Whole slate -> candidate legs, priced by the BOOK (never invented).

    Runs the same Dixon-Coles engine as /predict-soccer over every game
    (scan_slate.scan_game) and flattens each priced edge into the candidate
    shape build_tickets/strong_singles consume. Always soccer — tagged so
    rule 30 (model_gate.py) can see it.
    """
    from scan_slate import scan_game  # deferred: keeps CLI import cheap
    cands = []
    for g in games:
        r = scan_game(g)
        for mkt, _ev, prob, price in r["edges"]:
            cands.append({"match": r["name"], "selection": mkt,
                          "decimal": float(price), "prob": float(prob),
                          "sport": "SOCCER",
                          "kill": r.get("kill_paths", {}).get(mkt)})
    return cands


def _mlb_model_read(g: dict) -> dict | None:
    """Pitcher-adjusted model probs for an MLB game (mlb_game_model, 59.0% ML
    acc backtested w/ pitchers). Context only — never crashes the card."""
    try:
        import mlb_game_model as mgm
        r = mgm.predict(g["home"], g["away"])
        if r.get("error"):
            return None
        ps = (r.get("context") or {}).get("probable_starters") or {}
        return {"home": float(r["ml"]["home"]), "away": float(r["ml"]["away"]),
                "starters": {s: (ps.get(s) or {}).get("name")
                             for s in ("home", "away")}}
    except Exception:                                          # noqa: BLE001
        return None


MLB_FADE_DELTA = -0.10   # model this far under sharp = pitcher-driven fade flag


def candidates_from_2way(games: list[dict], sport_key: str | None = None) -> list[dict]:
    """Sharp-anchored 2-way candidates (NBA/NFL/MLB/NHL/tennis).

    prob = devigged PINNACLE fair probability; decimal = best available
    price across books. EV > 0 exists only when a soft book beats the
    sharp fair line — the classic +EV method, no invented model.

    MLB extra: each side also carries the pitcher-adjusted model prob and its
    delta vs the sharp anchor. The SHARP prob still prices the bet (the model
    is a validated signal, not a validated closing line); a big negative delta
    surfaces as model_warn so a starter mismatch is visible before LOG."""
    from soccer_markets import devig_2way
    cands = []
    sport = _gate_sport(sport_key)
    for g in games:
        dv = devig_2way(g["pinnacle"][0], g["pinnacle"][1])
        model = _mlb_model_read(g) if sport_key == "baseball_mlb" else None
        for key, side, prob, price in (("home", g["home"], dv["a"], g["best"][0]),
                                       ("away", g["away"], dv["b"], g["best"][1])):
            c = {"match": g["name"], "selection": f"{side} ML",
                 "decimal": float(price), "prob": float(prob), "sport": sport}
            if model:
                delta = model[key] - float(prob)
                c["model_prob"] = round(model[key], 4)
                c["model_delta"] = round(delta, 4)
                c["starters"] = model["starters"]
                if delta <= MLB_FADE_DELTA:
                    c["model_warn"] = (f"pitcher model has {side} at "
                                       f"{model[key]:.0%} vs sharp {prob:.0%} — fade signal")
            cands.append(c)
    return cands


def day_card(games: list[dict], n_tickets: int = DEFAULT_TICKETS,
             bankroll: float | None = None, mode: str = "soccer",
             sport_key: str | None = None) -> dict:
    """One call: slate in, day card out — 3-5x tickets + Kelly-sized singles.
    mode="soccer" runs the Poisson board; mode="2way" runs sharp-anchored ML."""
    cands = (candidates_from_2way(games, sport_key) if mode == "2way"
             else candidates_from_slate(games))
    gate_sport_key = "SOCCER" if mode == "soccer" else sport_key
    per_match = apply_model_gate(
        apply_data_gate(best_per_match(cands), sport_key), gate_sport_key)
    return {**build_tickets(cands, n_tickets),
            "singles": strong_singles(cands, bankroll),
            "per_match": per_match}


def _main() -> None:
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    bankroll = payload.get("bankroll")
    bank = float(bankroll) if bankroll is not None else None
    n = int(payload.get("n_tickets", DEFAULT_TICKETS))
    if payload.get("live"):                  # REAL runs only — Odds API quota
        sport = str(payload.get("sport", "soccer_fifa_world_cup"))
        if sport.startswith("soccer"):       # 3-way -> full Poisson board
            from scan_slate import fetch_slate_oddsapi
            out = day_card(fetch_slate_oddsapi(sport), n, bank, sport_key=sport)
        elif sport == "tennis":              # active tournaments discovered live
            from scan_slate import discover_tennis_keys, fetch_slate_2way_oddsapi
            games = [g for k in discover_tennis_keys() for g in fetch_slate_2way_oddsapi(k)]
            out = day_card(games, n, bank, mode="2way", sport_key="tennis")
        else:                                # NBA/NFL/MLB/NHL... -> sharp-anchored ML
            from scan_slate import fetch_slate_2way_oddsapi
            out = day_card(fetch_slate_2way_oddsapi(sport), n, bank, mode="2way",
                           sport_key=sport)
    elif payload.get("games"):               # whole slate -> auto-fed day card
        out = day_card(payload["games"], n, bank,
                       sport_key=payload.get("sport"))
    else:
        cands = payload.get("candidates", [])
        out = {**build_tickets(cands, n), "singles": strong_singles(cands, bank)}
    if "--json" in sys.argv:
        print(json.dumps(out, indent=2))
        return
    if out["pass"] and not out["singles"]:
        print("[PASS] " + out["note"])
        return
    for i, t in enumerate(out["tickets"], 1):
        print(f"ticket #{i}  [{t['lane']}]  x{t['combined']}  "
              f"win {t['joint_prob']*100:.0f}%  EV {t['ev_pct']:+.1f}%")
        for l in t["legs"]:
            print(f"    {l['selection']} @ {l['decimal']}  ({l['match']})")
    for s in out["singles"]:
        usd = f"  ${s['stake_usd']}" if "stake_usd" in s else ""
        print(f"single  {s['selection']} @ {s['decimal']}  win {s['prob']*100:.0f}%  "
              f"EV {s['ev_pct']:+.1f}%  stake {s['stake_pct']}% of bank{usd}  ({s['match']})")


if __name__ == "__main__":
    _main()
