import analyze_capture as A


def ev(**k):
    return {"kind": "fetch", "method": "POST", "url": "https://x.test/_api/v1/graphql?", **k}


def test_groups_by_path_and_operation_and_sums_bytes():
    inv = A.inventory([ev(op="A", bytes=100), ev(op="A", bytes=50), ev(op="B", bytes=10)])
    a = next(r for r in inv if r["op"] == "A")
    assert a["calls"] == 2 and a["bytes"] == 150 and len(inv) == 2


def test_flags_price_bearing_group_and_ranks_it_first():
    inv = A.inventory([ev(op="meta", bytes=9000, odds_hits=0), ev(op="markets", bytes=500, odds_hits=12)])
    assert inv[0]["op"] == "markets" and inv[0]["carries_odds"]
    assert A.verdict(inv).startswith("odds-bearing")


def test_verdict_points_to_dom_when_no_prices_and_no_socket():
    inv = A.inventory([ev(op="meta", bytes=9000, odds_hits=0)])
    assert "DOM" in A.verdict(inv)
