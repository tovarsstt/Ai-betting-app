#!/usr/bin/env python3
"""
kill_test.py — ONE command fires EVERY engine for a pick and prints the tiered
report. Exists because both 2026-07-19 losses were orchestration failures, not
engine failures: the serve model was never run on Darderi, and a model split
was misread as "no bet" on Gstaad. One entrypoint = no forgotten engine.

Usage:
  python3 kill_test.py tennis "Andrey Rublev" "Luciano Darderi" \
      [--surface Clay] [--best-of 3] [--crowd home|away] \
      [--sets-home N --sets-away N] [--price-home 1.68] [--price-away 2.10]
  python3 kill_test.py soccer "Spain" "Argentina" [--home-venue] \
      [--price-home 2.27 --price-draw 3.00 --price-away 3.55]
  python3 kill_test.py mlb "Toronto Blue Jays" "Chicago White Sox" [--total-line 8.5]

Every probability printed comes from a real engine; every verdict names the
tier it holds at (WORST-LENS SAFE > BLEND > SINGLE-LENS). No bare no-bets:
when nothing clears its floor, the floors themselves are the report.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import edge_api as ea  # noqa: E402


def dec2am(d: float) -> float:
    return (d - 1) * 100 if d >= 2 else -100 / (d - 1)


def _tier_line(name: str, prob: float, price: float | None) -> str:
    floor = 1.05 / prob if prob > 0 else float("inf")
    if price is None:
        return f"  {name:28s} P {prob:5.1%}  bet at >= {floor:.2f}"
    ev = prob * price - 1
    verdict = "BET" if price >= floor else ("thin" if ev > 0 else "PASS")
    return f"  {name:28s} P {prob:5.1%}  @ {price:.2f}  EV {ev:+6.1%}  {verdict}"


def tennis(a: argparse.Namespace) -> None:
    req = ea.PredictReq(
        sport="TENNIS", home_team=a.home, away_team=a.away,
        home_odds=dec2am(a.price_home) if a.price_home else -100,
        away_odds=dec2am(a.price_away) if a.price_away else -100,
        surface=a.surface, best_of=a.best_of, crowd=a.crowd,
        recent_sets_home=a.sets_home, recent_sets_away=a.sets_away)
    out = ea.predict(req)
    if out.get("bet_signal") == "NO_DATA":
        print(f"NO DATA: {out.get('model_note')}")
        return
    hcp = out["home_cover_prob"]
    print(f"== TENNIS KILL-TEST: {a.home} vs {a.away} ({a.surface}) ==")
    print(f"points model (form/surface/context): {a.home} {hcp:.1%}"
          f"  [{out.get('method')}]")
    if out.get("serve_model_home_prob") is not None:
        print(f"serve model second opinion:          {a.home} "
              f"{out['serve_model_home_prob']:.1%}")
    if out.get("context"):
        print(f"context nudges: {out['context']}")
    if out.get("ranks_stale"):
        print(f"WARNING: {out['ranks_stale']}")
    split = out.get("model_split")
    if split:
        print(f"\nMODEL SPLIT -> ROUTER (never a bare no-bet):\n  {split}")
        print(f"  {'market':26s} {'points':>7} {'serve':>7} {'blend':>7} "
              f"{'floor':>6} {'blend-floor':>11}")
        for mkt, r in out["split_robust_markets"].items():
            print(f"  {mkt:26s} {r['points']:7.1%} {r['serve']:7.1%} "
                  f"{r['blend']:7.1%} {r['floor_odds']:6.2f} {r['blend_floor_odds']:11.2f}")
        print("  rule: price >= floor = safe at WORST lens; >= blend-floor = "
              "blend-EV tier; market-agreeing lens is the tiebreaker")
    else:
        import tennis_live as tlive
        ps = tlive.implied_set_prob(hcp, a.best_of)
        print("\nengines AGREE — pick ladder:")
        print(_tier_line(f"{a.home} ML", hcp, a.price_home))
        print(_tier_line(f"{a.away} ML", 1 - hcp, a.price_away))
        print(_tier_line(f"{a.home} wins a set", 1 - (1 - ps) ** 2, None))
        print(_tier_line(f"{a.away} wins a set", 1 - ps ** 2, None))
    if a.price_home:
        print(f"\nmarket devig check: {a.home} implied "
              f"{1/a.price_home:.1%} vs model {hcp:.1%}"
              f"{'  << model-market gap, ranks suspect' if abs(hcp - 1/a.price_home) > ea.STALE_RANK_GAP else ''}")


def soccer(a: argparse.Namespace) -> None:
    req = ea.SoccerMarketReq(
        home_team=a.home, away_team=a.away, neutral=not a.home_venue,
        home_odds=dec2am(a.price_home) if a.price_home else None,
        draw_odds=dec2am(a.price_draw) if a.price_draw else None,
        away_odds=dec2am(a.price_away) if a.price_away else None)
    out = ea.predict_soccer(req)
    if out.get("status") != "OK":
        print(f"NO DATA: {out}")
        return
    m = out["markets"]
    print(f"== SOCCER KILL-TEST: {a.home} vs {a.away}"
          f" ({'home venue' if a.home_venue else 'neutral'}) ==")
    print(f"lambdas {out['lambda_home']:.2f}/{out['lambda_away']:.2f} "
          f"({out['lambda_source']}) | xG total {m['expected_total_goals']}")
    x = m["1x2"]
    print(f"1x2: home {x['home']:.1%} draw {x['draw']:.1%} away {x['away']:.1%}")
    print(_tier_line("home ML", x["home"], a.price_home))
    print(_tier_line("draw", x["draw"], a.price_draw))
    print(_tier_line("away ML", x["away"], a.price_away))
    dc = m["double_chance"]
    print(_tier_line("DC 1X", dc["1X"], None))
    print(_tier_line("DC X2", dc["X2"], None))
    print(_tier_line("under 2.5", m["totals"]["2.5"]["under"], None))
    print(_tier_line("BTTS No", m["btts"]["no"], None))
    top = m["correct_score"][:3]
    print("top scores: " + ", ".join(f"{s['score']} {s['prob']:.1%}" for s in top))
    print("REMINDER: props via player_props.py (ET-aware); joint-sim any multi-leg")


def mlb(a: argparse.Namespace) -> None:
    out = ea.predict_mlb(ea.MLBGameReq(home=a.home, away=a.away,
                                       total_line=a.total_line))
    print(f"== MLB KILL-TEST: {a.away} @ {a.home} ==")
    er = out.get("expected_runs", {})
    print(f"expected runs: home {er.get('home')} away {er.get('away')} "
          f"total {er.get('total')}")
    ml = out.get("ml") or {}
    if ml:
        print(f"ML: {ml}")
    t = out.get("total") or {}
    if t:
        print(f"total {a.total_line}: over {t.get('p_over')} under {t.get('p_under')} "
              f"push {t.get('p_push')}")
    ctx = out.get("context", {})
    starters = ctx.get("probable_starters") or {}
    for side, p in starters.items():
        if isinstance(p, dict) and p.get("starts", 99) < 8:
            print(f"WARNING: {side} starter {p.get('name')} ra9 {p.get('ra9')} on "
                  f"only {p.get('starts')} starts — small sample, haircut the edge")
    print("REMINDER: devig Pinnacle board for the sharp-anchor lens before betting")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sport", choices=["tennis", "soccer", "mlb"])
    ap.add_argument("home")
    ap.add_argument("away")
    ap.add_argument("--surface", default="Hard")
    ap.add_argument("--best-of", type=int, default=3)
    ap.add_argument("--crowd", choices=["home", "away"], default=None)
    ap.add_argument("--sets-home", type=int, default=None)
    ap.add_argument("--sets-away", type=int, default=None)
    ap.add_argument("--price-home", type=float, default=None)
    ap.add_argument("--price-draw", type=float, default=None)
    ap.add_argument("--price-away", type=float, default=None)
    ap.add_argument("--total-line", type=float, default=None)
    ap.add_argument("--home-venue", action="store_true",
                    help="soccer: real home venue (default neutral)")
    a = ap.parse_args()
    ea.load_all()
    {"tennis": tennis, "soccer": soccer, "mlb": mlb}[a.sport](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
