// ── CLV capture — find the closing line for a pending pick ────────────────────
// Pure functions: the server injects the fetched odds events so this is fully
// testable without touching the Odds API. We only stamp a close when the pick's
// structured market identity matches an event exactly — never a fuzzy guess that
// would pollute the CLV metric.

import type { LedgerPick } from './ledger.js';

export interface CaptureOutcome { name: string; price: number; point?: number }
export interface CaptureMarket { key: string; outcomes: CaptureOutcome[] }
export interface CaptureBook { key: string; title: string; markets: CaptureMarket[] }
export interface CaptureEvent {
  home_team: string;
  away_team: string;
  commence_time: string;
  bookmakers: CaptureBook[];
}

const norm = (s: string): string =>
  s.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim();

// Locate the closing price for a pick's exact market identity. Pinnacle preferred
// (sharpest close), falling back to any book. Returns null when not matched.
export function findClose(
  pick: Pick<LedgerPick, 'game' | 'market_key' | 'outcome' | 'point'>,
  events: CaptureEvent[],
): { price: number; commence_time: string } | null {
  if (!pick.market_key || !pick.outcome) return null;
  const game = norm(pick.game);
  const wantName = norm(pick.outcome);

  for (const ev of events) {
    // Event match: both team names must appear in the pick's game string.
    if (!game.includes(norm(ev.home_team)) || !game.includes(norm(ev.away_team))) continue;

    const books = [...ev.bookmakers].sort(
      (a, b) => Number(b.key === 'pinnacle') - Number(a.key === 'pinnacle'),
    );
    for (const book of books) {
      const market = book.markets.find(m => m.key === pick.market_key);
      if (!market) continue;
      const outcome = market.outcomes.find(o =>
        norm(o.name) === wantName &&
        (pick.market_key !== 'spreads' || pick.point == null || o.point === pick.point),
      );
      if (outcome) return { price: outcome.price, commence_time: ev.commence_time };
    }
  }
  return null;
}

// Pending picks that carry structured identity and still need a closing line.
export function pendingNeedingClose(ledger: LedgerPick[]): LedgerPick[] {
  return ledger.filter(p =>
    p.result === 'PENDING' && p.closing_odds == null && !!p.market_key && !!p.outcome,
  );
}

// True when `now` is inside the pre-kickoff window — the line just before commence
// IS the close. Outside the window we skip: too early = not the close yet, after
// commence = pre-match line is gone / in-play noise.
export function inCaptureWindow(commenceISO: string, now = Date.now(), leadMin = 30): boolean {
  const t = Date.parse(commenceISO);
  if (!Number.isFinite(t)) return false;
  return now >= t - leadMin * 60_000 && now < t;
}
