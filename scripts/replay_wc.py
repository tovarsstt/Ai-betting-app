"""
Replay harness — runs the chaos engine over fixed pre-match fixtures and reports
which spots it flagged vs the actual result. Honest by design: it prints the
matches it could NOT flag rather than pretending. No network (fixtures only).
"""
from __future__ import annotations

import json
from pathlib import Path

import chaos_engine as ce

FIXTURE = Path(__file__).parent / "fixtures" / "wc_2026_jun11_15.json"


def _to_match(row: dict) -> ce.MatchInput:
    return ce.MatchInput(
        home=ce.TeamForm(**row["home"]),
        away=ce.TeamForm(**row["away"]),
        market_home=row["market_home"],
        market_draw=row["market_draw"],
        market_away=row["market_away"],
        fav_decimal_odds=row["fav_decimal_odds"],
        draw_decimal_odds=row.get("draw_decimal_odds"),
        model_home=row.get("model_home"),
        model_draw=row.get("model_draw"),
        model_away=row.get("model_away"),
        home_tag=row.get("home_tag"),
        away_tag=row.get("away_tag"),
    )


def run_replay() -> list[dict]:
    rows = json.loads(FIXTURE.read_text())
    report = []
    for row in rows:
        res = ce.assess_match(_to_match(row))
        report.append({
            "label": row["label"],
            "grade": res.grade,
            "draw_score": res.draw_score,
            "actual": row["actual"],
            "side": res.side,
            "evidence": res.evidence,
        })
    return report


def main() -> None:
    for r in run_replay():
        hit = "—"
        if r["grade"] == "LITE" and r["actual"] == "DRAW":
            hit = "draw flagged"
        elif r["grade"] == "NONE" and r["actual"] in ("HOME", "AWAY"):
            hit = "correctly quiet"
        print(f"{r['label']}: {r['grade']} (draw_score {r['draw_score']}) "
              f"actual={r['actual']} [{hit}]")
        for e in r["evidence"]:
            print(f"    - {e}")


if __name__ == "__main__":
    main()
