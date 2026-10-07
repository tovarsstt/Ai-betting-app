#!/usr/bin/env python3
"""
tennis_slate_scan.py — price EVERY posted market of every match on a pasted board.

Per match: point-by-point Bernoulli simulation (level-anchored to the devigged ML,
serve stats from tennis_serve.json), margin-tail widening from
data/tennis_margin_calibration.json, full per-sim records (winner, set scores, set-1
winner/games, games each side). Every market is read off the same simulations:
ML, set 1, wins-a-set, set handicap, game handicap ladder, match total, set-1 total,
winner&total combos, set1/match double.

Final probability = 50/50 blend of model and the market's own devigged price when
the market quotes both sides (held-out price test: model alone only reaches PARITY
with the market, the blend is best). Combos/doubles have no second side to devig,
so they are MODEL-ONLY and labelled so.
"""
from __future__ import annotations

import multiprocessing as mp
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import tennis_games_model as tgm  # noqa: E402

N_SIM, CAL = 24000, 800


def _simulate(a, b, target_a, n=N_SIM, seed=5):
    doc = tgm.load()["players"]
    ka, kb = tgm.player_key(a, doc), tgm.player_key(b, doc)
    if not ka or not kb:
        return None
    pa, pb = tgm.point_prob(doc[ka]), tgm.point_prob(doc[kb])
    d = 0.0
    if target_a is not None:
        lo, hi = -0.08, 0.08
        for _ in range(11):
            d = (lo + hi) / 2
            m = tgm.simulate_match(pa + d, pb - d, 3, n_sims=CAL, seed=tgm.SEED)["match_prob_a"]
            lo, hi = (d, hi) if m < target_a else (lo, d)
        d = (lo + hi) / 2
    rng = random.Random(seed)
    rows = np.zeros((n, 7), dtype=np.int16)   # winner, setsA, setsB, set1w, set1games, gamesA, gamesB
    for i in range(n):
        sets, g, server, s1 = [0, 0], [0, 0], rng.randint(0, 1), None
        while max(sets) < 2:
            w, ga, gb, server = tgm._sim_set(pa + d, pb - d, rng, server)
            sets[w] += 1
            g[0] += ga
            g[1] += gb
            if s1 is None:
                s1 = (w, ga + gb)
        rows[i] = (0 if sets[0] == 2 else 1, sets[0], sets[1], s1[0], s1[1], g[0], g[1])
    off = tgm.totals_offset(doc[ka].get("tour") or "")
    return {"rows": rows, "off": off, "ka": ka, "kb": kb, "serve": (pa, pb),
            "n_pts": (doc[ka].get("n", 0), doc[kb].get("n", 0))}


def probs(s):
    r = s["rows"].astype(np.int32)
    k = s.get("k", tgm.margin_scale())
    mar = np.rint((r[:, 5] - r[:, 6]) * k)
    tot = r[:, 5] + r[:, 6] + s["off"]
    win, sa, sb, s1w, s1g = r[:, 0], r[:, 1], r[:, 2], r[:, 3], r[:, 4]
    A, B = (win == 0), (win == 1)
    f = lambda m: float(np.mean(m))
    P = {"ml": {"A": f(A), "B": f(B)}, "set1": {"A": f(s1w == 0), "B": f(s1w == 1)},
         "wins_set": {"A": f(sa >= 1), "B": f(sb >= 1), "A_no": f(sa == 0), "B_no": f(sb == 0)}}
    P["set_h"] = {"A-1.5": f((sa == 2) & (sb == 0)), "B-1.5": f((sb == 2) & (sa == 0)),
                  "A+1.5": 1 - f((sb == 2) & (sa == 0)), "B+1.5": 1 - f((sa == 2) & (sb == 0))}
    P["mar"], P["tot"], P["s1g"], P["A"], P["B"], P["s1w"] = mar, tot, s1g, A, B, s1w
    return P


# ── board: A first-named. odds pairs are (A-side, B-side) or (over, under) ───────────────
BOARD = [
    dict(name="Charaeva v Q.Zheng", A="Charaeva, Alina", B="Zheng, Qinwen", ml=(4.00, 1.26),
         set1=(3.10, 1.34), wins_set=dict(A=(2.07, 1.70), B=(1.10, 6.20)), set_h={"A+1.5": 2.05, "B-1.5": 1.69},
         game_h=[(+3.5, 2.39, 1.51), (+4.5, 1.90, 1.81), (+5.5, 1.53, 2.35)],
         tot=[(18.5, 1.43, 2.70), (19.5, 1.64, 2.17), (20.5, 1.87, 1.86), (21.5, 2.09, 1.69), (22.5, 2.40, 1.53)],
         s1tot=[(7.5, 1.12, 5.20), (8.5, 1.38, 2.80), (9.5, 2.03, 1.70), (10.5, 3.80, 1.22)],
         combo=dict(Ao=5.60, Bo=2.55, Au=11.00, Bu=2.12, L=20.5), double=4.80),
    dict(name="Li v Svitolina", A="Li, Ann", B="Svitolina, Elina", ml=(3.75, 1.29),
         set1=(2.95, 1.37), wins_set=dict(A=(1.99, 1.76), B=(1.12, 5.80)), set_h={"A+1.5": 1.97, "B-1.5": 1.74},
         game_h=[(+3.5, 2.29, 1.55), (+4.5, 1.84, 1.86), (+5.5, 1.51, 2.40)],
         tot=[(19.5, 1.63, 2.19), (20.5, 1.86, 1.88), (21.5, 2.07, 1.71)],
         s1tot=[(8.5, 1.38, 2.80), (9.5, 2.03, 1.70), (10.5, 3.80, 1.22)],
         combo=dict(Ao=5.40, Bo=2.60, Au=9.80, Bu=2.19, L=20.5), double=4.40),
    dict(name="Bellucci v Zhou", A="Bellucci, Mattia", B="Zhou, Yi", ml=(1.28, 3.90),
         set1=(1.37, 2.95), wins_set=dict(A=(1.11, 6.20), B=(1.93, 1.85)), set_h={"A-1.5": 1.83, "B+1.5": 1.91, "B-1.5": 6.60, "A+1.5": 1.11},
         game_h=[(-2.5, 1.48, 2.55), (-3.5, 1.74, 2.02), (-4.5, 2.31, 1.57)],
         tot=[(20.5, 1.61, 2.23), (21.5, 1.77, 1.98), (22.5, 2.06, 1.71)],
         s1tot=[(6.5, 1.01, 12.0), (7.5, 1.06, 7.60), (8.5, 1.21, 3.95), (9.5, 1.69, 2.05), (10.5, 2.95, 1.35)],
         combo=dict(Ao=2.43, Bo=5.40, Au=2.28, Bu=11.00, L=21.5), double=1.46),
    dict(name="Halys v Wong", A="Halys, Quentin", B="Wong, Coleman", ml=(1.77, 2.11),
         set1=(1.76, 1.99), wins_set=dict(A=(1.30, 3.45), B=(1.41, 2.85)),
         set_h={"A-1.5": 2.80, "B-1.5": 3.45, "A+1.5": 1.29, "B+1.5": 1.40},
         game_h=[(-0.5, 1.78, 1.96), (-1.5, 1.94, 1.80), (-2.5, 2.25, 1.60)],
         tot=[(22.5, 1.64, 2.17), (23.5, 1.90, 1.84), (24.5, 1.93, 1.81)],
         s1tot=[(7.5, 1.02, 9.80), (8.5, 1.11, 5.60), (9.5, 1.48, 2.49), (10.5, 2.41, 1.50), (12.5, 3.05, 1.33)],
         combo=dict(Ao=3.40, Bo=3.85, Au=3.15, Bu=3.95, L=23.5), double=2.09),
    dict(name="Rune v Altmaier", A="Rune, Holger", B="Altmaier, Daniel", ml=(1.46, 2.80),
         set1=(1.53, 2.40), wins_set=dict(A=(1.19, 4.50), B=(1.64, 2.21)),
         set_h={"A-1.5": 2.19, "B+1.5": 1.63, "B-1.5": 4.60, "A+1.5": 1.18},
         game_h=[(-1.5, 1.56, 2.33), (-2.5, 1.72, 2.04), (-3.5, 2.06, 1.71)],
         tot=[(21.5, 1.69, 2.09), (22.5, 1.95, 1.80), (23.5, 2.19, 1.63)],
         s1tot=[(6.5, 1.01, 12.0), (7.5, 1.05, 7.60), (8.5, 1.20, 4.00), (9.5, 1.68, 2.06), (10.5, 2.95, 1.35)],
         combo=dict(Ao=3.00, Bo=4.70, Au=2.43, Bu=5.80, L=22.5), double=1.70),
]


def _devig(a, b):
    """Power de-vig (best log-loss on 60k tennis closing lines, scripts/math_kit_validation.py)."""
    import betting_math as bm
    return float(bm.devig_power([a, b])[0])


def scan(m, S):
    P = probs(S)
    mar, tot, s1g, A, B = P["mar"], P["tot"], P["s1g"], P["A"], P["B"]
    out = []

    def add(label, model, odds, mkt=None, kind="blend"):
        p = model if mkt is None else (model + mkt) / 2
        out.append(dict(match=m["name"], bet=label, odds=odds, model=model, market=mkt, p=p,
                        ev=p * odds - 1, basis=("blend" if mkt is not None else "MODEL-ONLY")))

    a, b = m["ml"]
    add(f"{m['A'].split(',')[0]} ML", P["ml"]["A"], a, _devig(a, b))
    add(f"{m['B'].split(',')[0]} ML", P["ml"]["B"], b, _devig(b, a))
    a1, b1 = m["set1"]
    add(f"{m['A'].split(',')[0]} gana set 1", P["set1"]["A"], a1, _devig(a1, b1))
    add(f"{m['B'].split(',')[0]} gana set 1", P["set1"]["B"], b1, _devig(b1, a1))
    for side in ("A", "B"):
        y, n_ = m["wins_set"][side]
        nm = m[side].split(",")[0]
        add(f"{nm} gana un set", P["wins_set"][side], y, _devig(y, n_))
        add(f"{nm} NO gana un set", P["wins_set"][side + "_no"], n_, _devig(n_, y))
    sh = m["set_h"]
    pairs = [("A-1.5", "B+1.5"), ("B-1.5", "A+1.5")]
    for x, y in pairs:
        if x in sh and y in sh:
            add(f"{m[x[0]].split(',')[0]} {x[1:]} sets", P["set_h"][x], sh[x], _devig(sh[x], sh[y]))
            add(f"{m[y[0]].split(',')[0]} {y[1:]} sets", P["set_h"][y], sh[y], _devig(sh[y], sh[x]))
        else:
            for k_, o in sh.items():
                add(f"{m[k_[0]].split(',')[0]} {k_[1:]} sets", P["set_h"][k_], o, None)
    for L, oa, ob in m["game_h"]:      # A at line L, B at -L
        pa_ = float(np.mean(mar + L > 0))
        pb_ = float(np.mean(-mar - L > 0))
        add(f"{m['A'].split(',')[0]} {L:+g} games", pa_, oa, _devig(oa, ob))
        add(f"{m['B'].split(',')[0]} {-L:+g} games", pb_, ob, _devig(ob, oa))
    for L, o, u in m["tot"]:
        po = float(np.mean(tot > L))
        add(f"Over {L} games", po, o, _devig(o, u))
        add(f"Under {L} games", 1 - po, u, _devig(u, o))
    for L, o, u in m["s1tot"]:
        po = float(np.mean(s1g > L))
        add(f"Set1 Over {L}", po, o, _devig(o, u))
        add(f"Set1 Under {L}", 1 - po, u, _devig(u, o))
    c = m["combo"]
    L = c["L"]
    ov = tot > L
    for key, mask, label in (("Ao", A & ov, f"{m['A'].split(',')[0]} y Over {L}"), ("Bo", B & ov, f"{m['B'].split(',')[0]} y Over {L}"),
                             ("Au", A & ~ov, f"{m['A'].split(',')[0]} y Under {L}"), ("Bu", B & ~ov, f"{m['B'].split(',')[0]} y Under {L}")):
        add(label, float(np.mean(mask)), c[key], None)
    add(f"{m['A'].split(',')[0]}/{m['A'].split(',')[0]} (set1 y partido)", float(np.mean(A & (P['s1w'] == 0))), m["double"], None)
    return out


def _run(m):
    a, b = m["ml"]
    S = _simulate(m["A"], m["B"], _devig(a, b))
    if S is None:
        return m["name"], None, None
    meta = {"hold": (tgm.hold_prob(S["serve"][0]), tgm.hold_prob(S["serve"][1])), "n": S["n_pts"], "off": S["off"]}
    return m["name"], scan(m, S), meta


if __name__ == "__main__":
    import json
    with mp.Pool(min(len(BOARD), max(1, mp.cpu_count() - 2))) as pool:
        res = pool.map(_run, BOARD)
    allbets = []
    for name, bets, meta in res:
        print(f"{name}: matches played {meta['n']} serve data | totals offset {meta['off']:+.2f}" if bets else f"{name}: no serve data")
        allbets += bets or []
    Path(__file__).parent.parent.joinpath("data", "_slate_scan.json").write_text(json.dumps(allbets, indent=1))
    print(len(allbets), "markets priced")
