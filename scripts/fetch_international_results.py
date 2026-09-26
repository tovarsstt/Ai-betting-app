"""
fetch_international_results.py — download + cache REAL national-team match
results for the soccer Poisson regression + eigenvector ratings fit.

Source: github.com/martj42/international_results (public domain, no API key,
49k+ verified men's full-international matches from 1872 to present, INCLUDING
World Cup 2026 group-stage results already played as of this WC). Verified
live and reachable at the time this was written — this is a real, dated data
source, not a placeholder.

Run manually (like train_all_sports.py) — NOT called from the live API path,
and NEVER during tests (tests read the cached CSV / a fixture, never network).

    python3 scripts/fetch_international_results.py
"""
from __future__ import annotations

import csv
import io
import sys
import urllib.request
from pathlib import Path

SOURCE_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
CACHE = Path(__file__).parent.parent / "data" / "soccer" / "international_results.csv"


def fetch(url: str = SOURCE_URL, timeout: int = 30) -> str:
    """Network call — only invoked by main()/CLI, never at import time or in tests."""
    req = urllib.request.Request(url, headers={"User-Agent": "caveman-locks/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def save_cache(csv_text: str, path: Path = CACHE) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(csv_text)
    reader = csv.DictReader(io.StringIO(csv_text))
    return sum(1 for _ in reader)


def load_cached(path: Path = CACHE) -> list[dict]:
    """Read the cached CSV — this is what the rating fitters actually use."""
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def main() -> None:
    print(f"Fetching {SOURCE_URL} ...")
    text = fetch()
    n = save_cache(text)
    print(f"Cached {n} matches -> {CACHE}")


if __name__ == "__main__":
    main()
