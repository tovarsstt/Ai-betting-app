#!/usr/bin/env python3
"""nfl_game_report.py — full single-game report from a slate run: win %, score, ladders vs the Stake price, team box score, player props and ONE representative
simulated game drive by drive / play by play (the simulated game closest to the run's median score and yardage; plays are team-level, the sim does not name the ball carrier).

Usage: python3 scripts/nfl_game_report.py AWAY@HOME --dir data/sim_runs/RUN [--stake data/stake_lines_*.json] [--out report.md] [--pbp-games 400]
Three probability columns on every market: pure sim, market (de-vigged Stake price), anchored 30/70 (logit blend; props 10/90) — the walk-forward says the market is the better centre.
"""
import os, sys, json, argparse
for _k in ("NUMBA_NUM_THREADS", "OMP_NUM_THREADS"): os.environ.setdefault(_k, "1")
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; ROOT = HERE.parent
sys.path.insert(0, str(HERE))
W_SIM, W_PROP = 0.3, 0.1
_sg = lambda x: 1 / (1 + np.exp(-x))
_lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
def _dv(a, b): return (1 / a) / (1 / a + 1 / b)
def _anch(p, pm, w=W_SIM): return float(_sg(w * _lg(p) + (1 - w) * _lg(pm)))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("game"); ap.add_argument("--dir", required=True); ap.add_argument("--stake"); ap.add_argument("--out"); ap.add_argument("--pbp-games", type=int, default=400)
    a = ap.parse_args()
    import pandas as pd
    import nfl_slate_box as sb, nfl_slate_props as sp, nfl_sim_service as ns
    away, home = a.game.split("@"); D = Path(a.dir)
    X = np.load(D / f"{a.game}.npy"); s = next(x for x in json.loads((D / "slate_summary.json").read_text()) if x["home"] == home and x["away"] == away)
    K = sb.KEYS; n = len(K); hp, apt = X[:, 0], X[:, 1]; m = apt - hp; T = hp + apt
    L = []; P = L.append
    P(f"# {away} @ {home} — simulación ({len(X):,} juegos)\n")
    wx = s.get("weather")
    P(f"QB: {s['qb_away']} ({away}) vs {s['qb_home']} ({home}) | bajas de titulares en el sim: {home} {({k: v for k, v in (s.get('avail') or {}).get('home', {}).items() if v})}, {away} {({k: v for k, v in (s.get('avail') or {}).get('away', {}).items() if v})}")
    if wx: P(f"Clima: {'techo' if wx.get('indoor') else str(wx.get('wind_mph')) + ' mph viento, ' + str(wx.get('precip_pct')) + '% lluvia, ' + str(wx.get('temp_f')) + ' F'} -> ajuste al total {wx.get('shift', 0):+.1f} pts")
    ph = float(((m < 0) + .5 * (m == 0)).mean())
    P(f"\n## Resultado\n- {home} gana **{ph*100:.1f}%** | {away} gana **{(1-ph)*100:.1f}%** | tiempo extra {X[:,2].mean()*100:.1f}%")
    P(f"- Marcador medio: {away} {apt.mean():.1f} - {home} {hp.mean():.1f} | mediana {int(np.median(apt))}-{int(np.median(hp))} | total medio {T.mean():.1f} (mediana {int(np.median(T))}, sd {T.std():.1f})")
    sc = pd.Series([f"{int(x)}-{int(y)}" for x, y in zip(apt, hp)]).value_counts(normalize=True).head(5)
    P("- Marcadores más frecuentes (" + away + "-" + home + "): " + ", ".join(f"{k} {v*100:.1f}%" for k, v in sc.items()))
    st = json.loads(Path(a.stake).read_text()) if a.stake else None
    if st:
        rows = []
        def add(name, price, p, pair): pm = _dv(price, pair); rows.append((name, price, float(p), pm, _anch(p, pm)))
        if "ml" in st: add(f"{away} gana", st["ml"]["away"], 1 - ph, st["ml"]["home"]); add(f"{home} gana", st["ml"]["home"], ph, st["ml"]["away"])
        for ln, (hprice, aprice) in st.get("spread", {}).items():        # line is from the AWAY side: away covers if (away - home) > -line ... stored as away handicap
            l = float(ln); add(f"{away} {l:+g}", aprice, (m + l > 0).mean(), hprice); add(f"{home} {-l:+g}", hprice, (m + l < 0).mean(), aprice)
        for ln, (ov, un) in st.get("total", {}).items(): l = float(ln); add(f"Más de {l:g}", ov, (T > l).mean(), un); add(f"Menos de {l:g}", un, (T < l).mean(), ov)
        for side, key, arr in (("home", home, hp), ("away", away, apt)):
            for ln, (ov, un) in st.get("team_total", {}).get(side, {}).items(): l = float(ln); add(f"{key} más de {l:g}", ov, (arr > l).mean(), un); add(f"{key} menos de {l:g}", un, (arr < l).mean(), ov)
        P("\n## Mercados de Stake (probabilidad de ganar la apuesta)\n| Apuesta | Cuota | Sim pura | Mercado | Anclada 30/70 |\n|---|---|---|---|---|")
        for r in sorted(rows, key=lambda r: -r[4]): P(f"| {r[0]} | {r[1]:.2f} | {r[2]*100:.1f}% | {r[3]*100:.1f}% | {r[4]*100:.1f}% |")
    P(f"\n## Box score de equipo (media por juego)\n| | {away} | {home} |\n|---|---|---|")
    col = lambda side, k: X[:, 3 + side * n + K.index(k)]
    names = {"att": "Pases intentados", "comp": "Pases completos", "pyds": "Yardas por pase", "rush": "Acarreos", "ryds": "Yardas por tierra", "sacks": "Sacks recibidos", "ints": "Intercepciones", "td": "Touchdowns", "ptd": "TD de pase", "fgm": "Goles de campo", "fga": "Intentos de FG", "fum": "Fumbles perdidos"}
    P(f"| Puntos | {apt.mean():.1f} | {hp.mean():.1f} |")
    for k in K: P(f"| {names[k]} | {col(1,k).mean():.1f} | {col(0,k).mean():.1f} |")
    P(f"| Yardas totales | {(col(1,'pyds')+col(1,'ryds')).mean():.0f} | {(col(0,'pyds')+col(0,'ryds')).mean():.0f} |")
    calib = pd.read_csv(ROOT / "data" / "nfl_box_calib_2026_team.csv"); d = sp.load_pbp(); rng = np.random.default_rng(7)
    props = {}
    for side, tm, qb in ((1, away, s["qb_away"]), (0, home, s["qb_home"])):
        Pt, _ = sp.build_team(rng, X, side, tm, d, s["injuries_full"], calib, qb, set(s["offense"][tm]), True); props[tm] = Pt
    P("\n## Player props (media | p10 - mediana - p90)")
    order = [("passY", "Yardas de pase", 2), ("passTD", "TD de pase", 2), ("comp", "Completos", 2), ("INT", "Intercepciones", 2), ("rushY", "Yardas por tierra", 4), ("car", "Acarreos", 3), ("recY", "Yardas de recepción", 5), ("rec", "Recepciones", 5), ("ATD", "Anota TD (prob.)", 6)]
    for stat, title, top in order:
        P(f"\n**{title}**\n| Jugador | Equipo | Media | p10 | Mediana | p90 |" + (" Prob. |" if stat == "ATD" else "") + "\n|---|---|---|---|---|---|" + ("---|" if stat == "ATD" else ""))
        rows = []
        for tm, Pt in props.items():
            for k, v in Pt.items():
                if k.endswith(" " + stat) and not k.startswith("Others"): v = np.asarray(v, float); rows.append((tm, k.rsplit(" ", 1)[0], v.mean(), np.percentile(v, 10), np.median(v), np.percentile(v, 90), (v >= 1).mean()))
        for r in sorted(rows, key=lambda r: -r[2])[: top * 2]:
            P(f"| {r[1]} | {r[0]} | {r[2]:.1f} | {r[3]:.0f} | {r[4]:.0f} | {r[5]:.0f} |" + (f" {r[6]*100:.0f}% |" if stat == "ATD" else ""))
    # ---- representative game, play by play
    par = sb._par; qh = ns.qb_id_from_name(par, s["qb_home"], home) or "x"; qa = ns.qb_id_from_name(par, s["qb_away"], away) or "y"
    g = sb._nds.GameSim(par, home, away, qh, qa, eff=par.get("eff") or par["boots"][0], seed=20261112, neutral=False, avail=s.get("avail"))
    tgt = np.array([np.median(hp), np.median(apt), col(0, "pyds").mean(), col(1, "pyds").mean(), col(0, "ryds").mean(), col(1, "ryds").mean()]); scl = np.array([7, 7, 60, 60, 40, 40.])
    best = None
    for _ in range(a.pbp_games):
        o = g.play_game(trace=True)
        if o["ot"]: continue
        v = np.array([o["score"][0], o["score"][1], o["stat"][0]["pyds"], o["stat"][1]["pyds"], o["stat"][0]["ryds"], o["stat"][1]["ryds"]], float)
        dist = float((((v - tgt) / scl) ** 2).sum())
        if best is None or dist < best[0]: best = (dist, o)
    o = best[1]
    P(f"\n## Un juego simulado representativo: {away} {o['score'][1]} - {home} {o['score'][0]}\nElegido entre {a.pbp_games} juegos con registro completo por ser el más cercano a la mediana del sim. Es UN escenario posible, no una predicción jugada por jugada. El sim trabaja a nivel de equipo: no dice qué jugador lleva el balón.")
    P(f"\n### Resumen por serie\n| # | Equipo | Inicio | Jugadas | Yardas | Tiempo | Resultado | Marcador ({away}-{home}) |\n|---|---|---|---|---|---|---|---|")
    fld = lambda yl: (f"propia {int(round(100 - yl))}" if yl > 50 else f"rival {int(round(yl))}" if yl < 50 else "medio campo")
    for dr in o["drives"]:
        P(f"| {dr['n']} | {dr['team']} | {fld(dr['start_yl'])} | {dr['plays']} | {int(dr['yds'])} | {int(dr['secs'])//60}:{int(dr['secs'])%60:02d} | {dr['result']} | {dr['score'][1]}-{dr['score'][0]} |")
    P("\n### Jugada por jugada\n```")
    last = None
    for (nd, q, gs, tm, dn, ytg, yl, kind, yds, desc) in o["log"]:
        if nd != last:
            dr = next((x for x in o["drives"] if x["n"] == nd), None); P(f"\n--- Serie {nd}: {tm}" + (f" -> {dr['result']} ({away} {dr['score'][1]} - {home} {dr['score'][0]})" if dr else "")); last = nd
        qc = max(gs - (4 - q) * 900, 0) if q <= 4 else max(gs, 0)
        P(f"Q{q} {int(qc)//60:2d}:{int(qc)%60:02d}  {tm:3s} {int(dn)}&{int(round(ytg)):<2d} en {fld(yl):11s} {desc}")
    P("```")
    txt = "\n".join(L)
    if a.out: Path(a.out).write_text(txt); print("wrote", a.out, len(txt), "chars")
    else: print(txt)


if __name__ == "__main__":
    main()
