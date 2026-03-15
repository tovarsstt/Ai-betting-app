"""
VIDEO-INSPIRED UPGRADE: INJURY LINE-GAP DETECTOR
Source: YouTube Video 4 (AI Edge Detection) — NBA example: Mobley + Hunter out.
Books don't adjust lines fast enough when injuries are confirmed late.
This module detects that gap and flags HIGH_EDGE opportunities.

Key insight from video: "Our AI spotted that Evan Mobley and DeAndre Hunter were
very likely to miss game 2. The books had Jarrett Allen at 21.5 pts+reb and
Max Strus at 9.5 pts — assuming both starters played."

-> Injury report + market line = EDGE DETECTOR.
"""
import requests
import json
from datetime import datetime

# Impact tables based on video insight:
# Key player out -> Other players get +minutes/+usage
NBA_USAGE_BUMP = {
    "star":        {"bench_1": +0.18, "bench_2": +0.12, "starter_adj": +0.08},
    "starter":     {"bench_1": +0.10, "bench_2": +0.07, "starter_adj": +0.04},
    "rotation":    {"bench_1": +0.04, "bench_2": +0.02, "starter_adj": +0.01},
}

class InjuryLineGapDetector:
    """
    Detects when a book's prop line hasn't adjusted to reflect a confirmed injury.
    This is the #1 edge described in video 4 — books are slow by 30-90 minutes.
    """

    ESPN_INJURIES = "https://site.api.espn.com/apis/site/v2/sports/{path}/injuries"
    SPORT_MAP = {
        "NBA": "basketball/nba",
        "NFL": "football/nfl",
        "MLB": "baseball/mlb",
        "NHL": "hockey/nhl",
    }

    def scrape_espn_injuries(self, sport="NBA"):
        """Pull live ESPN injury report."""
        path = self.SPORT_MAP.get(sport.upper(), "basketball/nba")
        url = self.ESPN_INJURIES.format(path=path)
        try:
            r = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                return r.json().get("injuries", [])
        except:
            pass
        return []

    def calculate_line_gap(self, injured_player: dict, teammates: list, current_book_line: float) -> dict:
        """
        Given an injured star, calculate how much the remaining players' lines
        should move — then compare to current book line to detect the edge.

        Args:
            injured_player: {"name": "Evan Mobley", "tier": "star", "ppg": 18.0}
            teammates: [{"name": "Jarrett Allen", "ppg": 14.0, "role": "bench_1"}]
            current_book_line: The current prop line the book is offering

        Returns:
            Dict with edge opportunity assessment
        """
        tier = injured_player.get("tier", "starter")
        bumps = NBA_USAGE_BUMP.get(tier, NBA_USAGE_BUMP["starter"])
        
        gaps = []
        for player in teammates:
            role = player.get("role", "bench_1")
            bump = bumps.get(role, 0.05)
            ppg = player.get("ppg", 10.0)
            
            # Calculate projected output with injury bump
            projected = ppg * (1 + bump)
            book_line = player.get("book_line", current_book_line)
            gap = projected - book_line
            gap_pct = (gap / book_line * 100) if book_line > 0 else 0
            
            edge = "STRONG_OVER" if gap > 2.0 else ("OVER" if gap > 0.5 else "NEUTRAL")
            
            gaps.append({
                "player": player.get("name", "Unknown"),
                "ppg_baseline": ppg,
                "usage_bump": f"+{int(bump * 100)}%",
                "projected_output": round(projected, 1),
                "book_line": book_line,
                "line_gap": round(gap, 1),
                "gap_pct": f"+{round(gap_pct, 1)}%",
                "signal": edge
            })
        
        return {
            "INJURED": injured_player.get("name"),
            "TIER": tier,
            "LINE_GAPS": gaps,
            "DETECTIVE_NOTE": f"Books likely set lines assuming {injured_player['name']} plays. Gap = edge.",
            "TIMESTAMP": datetime.now().strftime("%H:%M:%S")
        }

    def quick_scan(self, sport: str, injured_name: str, injured_tier: str,
                   impacted_players: list) -> dict:
        """
        Express interface: pass injured player + list of impacted teammates,
        get back a full line-gap analysis report.

        Example:
            detector.quick_scan(
                sport="NBA",
                injured_name="Evan Mobley",
                injured_tier="star",
                impacted_players=[
                    {"name": "Jarrett Allen",  "ppg": 14.0, "book_line": 21.5, "role": "bench_1"},
                    {"name": "Max Strus",      "ppg": 8.5,  "book_line": 9.5,  "role": "bench_2"},
                ]
            )
        """
        injured = {"name": injured_name, "tier": injured_tier}
        result = self.calculate_line_gap(injured, impacted_players, 0)
        result["SPORT"] = sport
        result["ENGINE"] = "INJURY_LINE_GAP_DETECTOR v1.0"
        return result
