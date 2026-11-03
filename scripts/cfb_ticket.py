#!/usr/bin/env python3
"""
cfb_ticket.py — analiza UNO O VARIOS tickets de college football (texto de Stake) como PORTAFOLIO.
  * lineas de mercado: ESPN scoreboard (si el juego sigue "pre") o data/cfb_history.jsonl (cierre) para juegos ya jugados
  * margen de cada juego simulado UNA vez (residuos empiricos de partidos con spread parecido, line_model_cfb.json); todas las piernas del mismo juego se mueven juntas
  * resultado: probabilidad y EV por ticket, P(perder todo), EV del portafolio, y la exposicion por pierna (cuantos tickets dependen de ella)
"""
from __future__ import annotations
import json, re, sys, urllib.request
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import ticket_parser as tp
import portfolio_check as pc

DATA = Path(__file__).parent.parent / "data"


def _norm(s: str) -> set:
    return set(re.sub(r"[^a-z0-9 ]", "", s.lower().replace("&", " ")).split()) - {"the", "of", "university", "state"} | ({"state"} if "state" in s.lower() else set())


def home_spread(details: str | None, home: str, home_abbr: str, away_abbr: str) -> float | None:
    """'M-OH -6.5' -> spread del LOCAL. Compara contra la abreviatura ESPN primero: 'M-OH' vs 'Miami (OH) RedHawks' no comparte tokens y daba el signo al reves."""
    if not details or details == "EVEN":
        return None
    tok = details.rsplit(" ", 1)
    try:
        v = float(tok[1])
    except Exception:
        return None
    fav = tok[0].strip().upper()
    if fav == home_abbr.upper():
        return v
    if fav == away_abbr.upper():
        return -v
    return v if _norm(tok[0]) & _norm(home) else -v


def espn_events(iso: str) -> list[dict]:
    day = iso.replace("-", "")
    u = f"https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?groups=80&limit=300&dates={day}"
    try:
        d = json.load(urllib.request.urlopen(urllib.request.Request(u), timeout=25))
    except Exception:
        return []
    out = []
    for e in d.get("events", []):
        c = e["competitions"][0]
        h = next(x for x in c["competitors"] if x["homeAway"] == "home")["team"]["displayName"]
        a = next(x for x in c["competitors"] if x["homeAway"] == "away")["team"]["displayName"]
        o = (c.get("odds") or [{}])[0]
        ab = {x["homeAway"]: x["team"].get("abbreviation", "") for x in c["competitors"]}
        sp = home_spread(o.get("details"), h, ab.get("home", ""), ab.get("away", ""))
        out.append({"home": h, "away": a, "state": e["status"]["type"]["state"], "home_spread": sp, "total": o.get("overUnder")})
    return out


def history_lines(iso: str) -> list[dict]:
    p = DATA / "cfb_history.jsonl"
    if not p.exists():
        return []
    import datetime as _dt
    nxt = (_dt.date.fromisoformat(iso) + _dt.timedelta(days=1)).isoformat()          # el historial guarda fecha UTC: juegos de noche caen al dia siguiente
    out = []
    for l in p.open():
        r = json.loads(l)
        if str(r.get("date", ""))[:10] in (iso, nxt):
            sp = r.get("home_spread_close") if r.get("home_spread_close") is not None else r.get("spread_cur")
            out.append({"home": r["home"], "away": r["away"], "state": "post", "home_spread": sp, "total": r.get("total_cur")})
    return out


def match_game(events: list[dict], first: str, second: str):
    a, b = _norm(first), _norm(second)
    best, score = None, 0
    for e in events:
        for h, aw in ((e["home"], e["away"]), (e["away"], e["home"])):
            s = len(a & _norm(h)) / max(len(a), 1) + len(b & _norm(aw)) / max(len(b), 1)
            if s > score:
                best, score = e, s
    return best if score >= 1.6 else None


def analyze_many(tickets: list[dict], n: int = 100_000) -> dict:
    cache, games, sims, rows, tick_out, unmatched = {}, {}, {}, [], [], []
    for t in tickets:
        for g in t["legs"]:
            iso = tp.date_iso(g.get("date"))
            if iso and iso not in cache:
                ev = espn_events(iso)
                hist = history_lines(iso)
                cache[iso] = ev if any(e["home_spread"] is not None for e in ev) else (ev + hist if not ev else [{**e, **next((h for h in hist if _norm(h["home"]) & _norm(e["home"]) and _norm(h["away"]) & _norm(e["away"])), {})} for e in ev])
            e = match_game(cache.get(iso, []), g.get("first_listed") or "", g.get("second_listed") or "") if iso else None
            if e is None or e["home_spread"] is None:
                unmatched.append(g); continue
            g["_game"] = (e["home"], e["away"]); g["_hs"] = e["home_spread"]
            games[g["_game"]] = e["home_spread"]
    if unmatched:
        return {"status": "PARTIAL", "sin_linea_o_juego": [{"team": u["team"], "date": u.get("date")} for u in unmatched], "nota": "no se analiza el portafolio con piernas sin linea de mercado (no se adivina)"}
    margins = {}
    for i, ((h, a), hs) in enumerate(games.items()):
        m = pc.margins_from_lines({"x": hs}, "cfb", n, seed=11 + i)["x"]           # margen del LOCAL
        margins[(h, a)] = m
    legs_info, T = [], []
    for t in tickets:
        legs = []
        for g in t["legs"]:
            h, a = g["_game"]; m = margins[(h, a)]
            team_is_home = _norm(g["team"]) & _norm(h) and len(_norm(g["team"]) & _norm(h)) >= len(_norm(g["team"]) & _norm(a))
            gid = f"{h}|{a}|{'H' if team_is_home else 'A'}"
            margins.setdefault(gid, m if team_is_home else -m)
            hc = 0.0 if g["kind"] == "ml" else float(g["line"])
            legs.append({"game": gid, "handicap": hc, "odds": g["odds"]})
            p = float(np.mean(margins[gid] + hc > 0))
            legs_info.append({"leg": f"{g['team']} {'ML' if g['kind']=='ml' else f'{hc:+g}'}", "juego": f"{a} @ {h}", "mercado_local": games[(h, a)], "odds": g["odds"], "p": round(p, 4), "cuota_justa": round(1 / p, 2) if p > 0 else None, "edge_pp": round(100 * (p - 1 / g["odds"]), 1)})
        T.append({"stake": t.get("stake") or 1.0, "legs": legs})
    flat = {k: v for k, v in margins.items() if isinstance(k, str)}
    port = pc.analyze_mc(T, flat)
    import itertools
    detalle = []
    for t, tk in zip(T, tickets):
        masks = [flat[l["game"]] + l["handicap"] > 0 for l in t["legs"]]
        names = [f"{g['team']} {'ML' if g['kind']=='ml' else f'{g[chr(108)+chr(105)+chr(110)+chr(101)]:+g}'}" for g in tk["legs"]]
        odds = [l["odds"] for l in t["legs"]]
        d = {"piernas": names, "quitar_una_pierna": {}, "mejores": []}
        full = np.logical_and.reduce(masks).mean()
        for i, nm in enumerate(names):
            if len(masks) > 1:
                rest = [m for j, m in enumerate(masks) if j != i]; o = float(np.prod([x for j, x in enumerate(odds) if j != i]))
                pr = float(np.logical_and.reduce(rest).mean()); d["quitar_una_pierna"][nm] = {"P": round(pr, 4), "cuota": round(o, 2), "EV_por_$1": round(pr * o - 1, 3)}
        if len(names) >= 3:
            for k in (2, 3):
                if k < len(names):
                    L = sorted(((float(np.logical_and.reduce([masks[i] for i in c]).mean()) * float(np.prod([odds[i] for i in c])) - 1, c) for c in itertools.combinations(range(len(names)), k)), reverse=True)[:2]
                    d["mejores"] += [{"piernas": [names[i] for i in c], "EV_por_$1": round(ev, 3), "P": round(float(np.logical_and.reduce([masks[i] for i in c]).mean()), 4), "cuota": round(float(np.prod([odds[i] for i in c])), 2)} for ev, c in L]
        d["P_completo"] = round(float(full), 4)
        detalle.append(d)
    port["detalle_tickets"] = detalle
    for tk, t in zip(port["tickets"], tickets):
        tk["estado_real"] = t.get("estado")
        if t.get("cashout"):
            hold = tk["p_gana"] * tk["odds"] * tk["stake"]
            tk["cashout"] = {"oferta": t["cashout"], "valor_esperado_de_mantener": round(hold, 2), "mantener_menos_cashout": round(hold - t["cashout"], 2)}
    return {"status": "OK", "portafolio": port, "piernas": legs_info}


def analyze_text(text: str, n: int = 100_000) -> dict:
    ts = tp.parse_many(text)
    return {"n_tickets": len(ts), **analyze_many(ts, n)} if ts else {"status": "EMPTY"}
