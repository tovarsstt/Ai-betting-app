#!/usr/bin/env python3
"""
analyze_slips.py — turn a pasted Stake bet history into P/L, ROI, and the
breakdowns that actually improve pick quality.

Why: the user's results are the ground truth the models get calibrated against.
This reads data/slips_raw.txt (raw Stake slip text), extracts every settled
ticket's (odds, stake, payout), and reports:
  - bankroll P/L + ROI (raw AND deduped — pasted history often double-counts)
  - win rate, and a profit/loss split by leg-count (parlay size) and odds band

Outcome is INFERRED from payout, not the status label (leg labels say "Ganador"
too, so the label is unreliable): payout 0 = lost; payout >= stake = won;
0 < payout < stake = cashout/partial (net loss, some recovered).

Stake/Pago use dot decimals (10.00000000); Cuotas uses comma (2,77).
Re-run after pasting fresh history. Never fabricates a number.
"""
import re
from collections import defaultdict
from pathlib import Path

RAW = Path(__file__).parent.parent / "data" / "slips_raw.txt"

# Each ticket ends: Cuotas <c> Apuesta <stake> [Multi Boost +N% <x>] Pago <payout>
TICKET = re.compile(
    r"Cuotas\s+([\d.,]+)\s+Apuesta\s+([\d.]+).*?Pago\s+([\d.]+)", re.S)
# Ticket header "<n> Multi tramo" is the OUTER leg count and always wins: a combo's
# legs can themselves be same-game blocks ("Multi apuesta del mismo partido (2/(3"),
# and taking an inner block's count mislabels a 7-leg combo as 3-leg.
MULTI_TRAMO = re.compile(r"(\d+)\s+Multi tramo")
SGM = re.compile(r"Multi apuesta del mismo partido\s*\((\d+)")

# Market markers for ticket_type — matched against the ticket's own block text.
SOCCER_MARKERS = ("1x2", "Ambos equipos marcan", "Totales asiáticos",
                  "Tiros de esquina", "Doble Oportunidad", "Goleador")
TENNIS_MARKERS = ("Hándicap de Set", "Total sets", "juego")
# "Surname, Firstname Ganador <odds>" — a tennis match-winner leg.
TENNIS_ML = re.compile(r"[^\W\d_][^\s,]*,\s+[^\W\d_][^\s]*\s+Ganador", re.U)
# Baseball: "(incl. extra innings)" is on every MLB market; hits props too.
BASEBALL_MARKERS = ("extra innings", "Hits")
# Basketball (WNBA/NBA): winner "(incl. prórroga)" = overtime. Checked after
# soccer so a soccer knockout tie doesn't get miscounted as hoops.
BASKETBALL_MARKERS = ("prórroga", "prorroga")


def ticket_type(block: str) -> str:
    """Heuristic sport/shape tag for one ticket's raw block text.

    Previously only soccer/tennis were tagged, so MLB/WNBA/NBA tickets — the bulk
    of the user's volume — all fell into "unknown" and the by-type P/L breakdown
    was blind to them. Baseball ("extra innings", hits props) and basketball
    ("prórroga" OT) are now recognized too.
    """
    is_soccer = any(m in block for m in SOCCER_MARKERS)
    is_tennis = bool(any(m in block for m in TENNIS_MARKERS) or TENNIS_ML.search(block))
    is_baseball = any(m in block for m in BASEBALL_MARKERS)
    is_basketball = any(m in block for m in BASKETBALL_MARKERS)
    if sum([is_soccer, is_tennis, is_baseball, is_basketball]) > 1:
        return "mixed sports"
    if is_tennis:
        return "tennis stack" if MULTI_TRAMO.search(block) else "tennis single"
    if is_soccer:
        if MULTI_TRAMO.search(block):
            return "soccer cross-match combo"
        if SGM.search(block):
            return "soccer same-game (1 match)"
        return "soccer single"
    if is_baseball:
        return "baseball stack" if MULTI_TRAMO.search(block) else "baseball single"
    if is_basketball:
        return "basketball stack" if MULTI_TRAMO.search(block) else "basketball single"
    return "unknown"


def odds_band(dec: float) -> str:
    # Banded by WIN PROBABILITY, not just price (win-prob-first directive):
    #   <1.50  ~67%+  the safe, high-prob anchor — the leg that carries a parlay.
    #   1.50-1.90 ~53-67%  a SOFT FAVOURITE — wins more than it loses but NOT a lock
    #                      (a 1.64 at 61% misses ~2 in 5). Not a "coin-flip" (=2.00/50%);
    #                      the trap is treating it like a lock. Cap one per ticket.
    #   1.90-2.50 ~40-53%  genuine pick-em/value.
    #   2.50-5.0  longshot.   5.0+  lottery.
    if dec < 1.50:
        return "chalk anchor (<1.50)"
    if dec < 1.90:
        return "soft favorite (1.50-1.90)"
    if dec < 2.50:
        return "value band (1.90-2.50)"
    if dec < 5.0:
        return "longshot (2.50-5.0)"
    return "lottery (5.0+)"


def parse(text: str | None = None) -> list:
    if text is None:
        text = RAW.read_text()
    out = []
    prev_end = 0
    for m in TICKET.finditer(text):
        dec = float(m.group(1).replace(".", "").replace(",", "."))
        stake, payout = float(m.group(2)), float(m.group(3))
        # leg count from THIS ticket's own block only (since the previous ticket end),
        # so singles aren't tagged with a neighbouring parlay's leg count.
        head = text[prev_end:m.start()]
        tramo = MULTI_TRAMO.search(head)           # outer header beats inner SGM blocks
        if tramo:
            legs = int(tramo.group(1))
        else:
            sgm = SGM.findall(head)
            legs = int(sgm[-1]) if sgm else 1
        out.append({"dec": dec, "stake": stake, "payout": payout, "legs": legs,
                    "type": ticket_type(head)})
        prev_end = m.end()
    return out


def dedupe(items: list) -> list:
    """Drop repeated (odds, stake, payout) tuples — pasted history often double-counts.
    Single source of truth so the analyzer and the linter bucket identical data."""
    seen = set(); out = []
    for r in items:
        k = (r["dec"], r["stake"], r["payout"])
        if k in seen:
            continue
        seen.add(k); out.append(r)
    return out


def summarize(items: list, label: str) -> None:
    staked = sum(i["stake"] for i in items)
    returned = sum(i["payout"] for i in items)
    net = returned - staked
    roi = net / staked * 100 if staked else 0.0
    won = [i for i in items if i["payout"] >= i["stake"] and i["payout"] > 0]
    cashout = [i for i in items if 0 < i["payout"] < i["stake"]]
    lost = [i for i in items if i["payout"] == 0]
    print(f"\n== {label}: {len(items)} tickets ==")
    print(f"  staked   ${staked:,.2f}")
    print(f"  returned ${returned:,.2f}")
    print(f"  net      ${net:+,.2f}   ROI {roi:+.1f}%")
    print(f"  won {len(won)} | cashout/partial {len(cashout)} | lost {len(lost)}"
          f"  (hit rate {len(won)/len(items)*100:.0f}%)")


def breakdown(items: list, key, title: str) -> None:
    buckets = defaultdict(lambda: {"n": 0, "stake": 0.0, "ret": 0.0, "won": 0})
    for i in items:
        b = buckets[key(i)]
        b["n"] += 1; b["stake"] += i["stake"]; b["ret"] += i["payout"]
        b["won"] += 1 if i["payout"] >= i["stake"] and i["payout"] > 0 else 0
    print(f"\n-- {title} --")
    for k in sorted(buckets):
        b = buckets[k]
        net = b["ret"] - b["stake"]
        roi = net / b["stake"] * 100 if b["stake"] else 0
        print(f"  {str(k):22} n={b['n']:3} | staked ${b['stake']:7.2f} | "
              f"net ${net:+8.2f} | ROI {roi:+6.1f}% | won {b['won']}/{b['n']}")


def main() -> None:
    rows = parse()
    if not rows:
        raise SystemExit("no tickets parsed — is data/slips_raw.txt populated?")
    uniq = dedupe(rows)
    summarize(rows, "RAW (paste as-is — may double-count duplicated sections)")
    summarize(uniq, "DEDUPED (unique odds+stake+payout — best estimate)")
    breakdown(uniq, lambda i: ("single" if i["legs"] == 1 else
                               "2-3 legs" if i["legs"] <= 3 else
                               "4-6 legs" if i["legs"] <= 6 else "7+ legs"),
              "By parlay size (deduped)")
    # TICKET-combined band: a parlay's odds are its whole ticket, NOT one leg.
    breakdown(uniq, lambda i: odds_band(i["dec"]),
              "By TICKET combined odds (parlays settle as a unit — not per-leg)")
    # LEG band: a single bet IS one leg, so its ROI is a TRUE per-leg ROI. This is
    # the table the linter gates each proposed leg against (see slip_linter._history_rois).
    singles = [i for i in uniq if i["legs"] == 1]
    if singles:
        breakdown(singles, lambda i: odds_band(i["dec"]),
                  "By LEG odds — singles only (true per-leg ROI; what the linter gates on)")
    breakdown(uniq, lambda i: i.get("type", "unknown"),
              "By ticket TYPE (sport + shape — where the money actually comes from)")


if __name__ == "__main__":
    main()
