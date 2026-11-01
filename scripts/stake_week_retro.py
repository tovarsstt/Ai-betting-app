"""Weekly Stake retro: ROI by day / bet type / legs / odds band from rows exported with scripts/stake_history_extract.js.
Row = [date, type(single|multi|sgm), legs, odds, stake, payout, result(W|L|adj)].  Usage: python3 scripts/stake_week_retro.py data/stake_week_20261028.json"""
import sys, json
from collections import defaultdict

LEG_BANDS = ((1, "single"), (3, "2-3 legs"), (5, "4-5 legs"), (99, "6+ legs"))
ODDS_BANDS = ((2, "<2"), (5, "2-5"), (12, "5-12"), (30, "12-30"), (1e9, "30+"))


def band(v, bands):
    return next(label for lim, label in bands if v <= lim)


def table(rows, key):
    g = defaultdict(lambda: [0, 0.0, 0.0, 0])
    for r in rows:
        k = key(r)
        g[k][0] += 1; g[k][1] += r[4]; g[k][2] += r[5]; g[k][3] += r[5] > 0
    return {k: dict(n=v[0], stake=round(v[1], 2), pay=round(v[2], 2), roi=round(v[2] / v[1] - 1, 3), hits=v[3]) for k, v in g.items()}


def retro(rows):
    keys = {"total": lambda r: "all", "day": lambda r: r[0], "type": lambda r: r[1],
            "legs": lambda r: "sgm" if r[1] == "sgm" else band(r[2], LEG_BANDS), "odds": lambda r: band(r[3], ODDS_BANDS)}
    return {name: table(rows, f) for name, f in keys.items()}


def drop_largest_win(rows):
    """ROI without the single biggest payout: shows how much of the week is one ticket."""
    top = max(rows, key=lambda r: r[5])
    rest = [r for r in rows if r is not top]
    return top, sum(r[5] for r in rest) / sum(r[4] for r in rest) - 1


if __name__ == "__main__":
    rows = json.load(open(sys.argv[1]))
    out = retro(rows)
    for name, t in out.items():
        print(f"== {name}")
        for k, v in t.items():
            print(f"  {k:10s} n={v['n']:3d} stake={v['stake']:7.2f} pay={v['pay']:7.2f} ROI={v['roi']*100:6.1f}% hit={v['hits']}/{v['n']}")
    top, roi = drop_largest_win(rows)
    print(f"== sin el mayor pago ({top[5]:.2f} a cuota {top[3]}): ROI {roi*100:.1f}%")
