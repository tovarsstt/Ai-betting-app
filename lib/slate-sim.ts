// ── Slate simulator — market-consistency model + Monte Carlo ─────────────────
//
// What this does (and does not) claim:
//  * It builds each game's margin distribution FROM THE MARKET (moneylines + spread),
//    so "fair" probabilities are the market's own no-vig view — not an independent forecast.
//  * Real, bettable edges can only come from (a) one book's price beating the consensus
//    (line shopping) or (b) a book's ML and spread disagreeing with each other.
//  * Monte Carlo treats games as independent and margin/total as independent within a game.
import {
  impliedProb, devig, ev, halfKelly, toDecimal, parlayPrice, formatAmerican, round,
  nflMarginPmf, pmfWinProb, pmfCover, noPushProb, fitMuToWinProb, fitMuToSpread,
  totalOverProb, fitTotalMean, NFL_MARGIN_SIGMA, NFL_TOTAL_SIGMA, rng, pmfSampler, gaussian,
} from "./betting-math.ts";

export interface BookMoneyline { book: string; home: number | null; away: number | null }

export interface SlateGame {
  id: string;
  away: string;
  home: string;
  kickoff_et?: string;
  neutral?: boolean;
  spread?: { home: number; home_price?: number; away_price?: number };
  total?: { points: number; over_price?: number; under_price?: number };
  moneylines?: BookMoneyline[];
  notes?: string[];
  sources?: string[];
}

export interface Slate {
  slate: string;
  sport: string;
  captured_at?: string;
  capture_method?: string;
  default_price?: number;
  games: SlateGame[];
}

export interface BetOption {
  game: string;
  market: "ML" | "SPREAD" | "TOTAL";
  selection: string;
  price: number;
  book: string;
  fair_prob: number;        // model prob of winning (spreads/totals: win given no push)
  push_prob: number;
  ev_pct: number;
  half_kelly_pct: number;
  price_assumed: boolean;   // true when the price wasn't in the source data (defaulted to -110)
  // for Monte Carlo grading
  side: "home" | "away" | "over" | "under";
  line: number | null;
}

export interface GameAnalysis {
  id: string;
  away: string;
  home: string;
  kickoff_et?: string;
  consensus_home_ml_prob: number | null;   // devigged, averaged across books
  books_with_ml: number;
  spread_home: number | null;
  spread_implied_home_win: number | null;  // what the spread says the ML should be
  ml_vs_spread_gap_pct: number | null;     // consensus ML prob − spread-implied, % points
  mu: number;                              // expected home margin used by the sim
  total_mean: number | null;
  fair_home_ml: string;                    // fair American price
  fair_spread_line: number;                // -mu rounded to nearest half point
  options: BetOption[];
  flags: string[];
  notes: string[];
}

export interface ParlayEval {
  legs: string[];
  price: string;
  analytic_prob: number;
  mc_prob: number;
  ev_pct: number;
}

export interface SlateReport {
  slate: string;
  sport: string;
  captured_at?: string;
  capture_method?: string;
  sigma: number;
  sigma_calibrated_from: number;
  sims: number;
  seed: number;
  games: GameAnalysis[];
  ranked: BetOption[];
  upsets: { expected: number; p_at_least: Record<number, number> };
  favorites_covering: { expected: number; distribution: Record<number, number> };
  parlays: ParlayEval[];
}

function consensusMl(g: SlateGame): { p: number | null; n: number } {
  const probs: number[] = [];
  for (const b of g.moneylines ?? []) {
    if (b.home == null || b.away == null) continue;
    probs.push(devig(impliedProb(b.home), impliedProb(b.away)).p1);
  }
  if (probs.length === 0) return { p: null, n: 0 };
  return { p: probs.reduce((a, b) => a + b, 0) / probs.length, n: probs.length };
}

function bestPrice(g: SlateGame, side: "home" | "away"): { price: number; book: string } | null {
  let best: { price: number; book: string } | null = null;
  for (const b of g.moneylines ?? []) {
    const p = b[side];
    if (p == null) continue;
    if (!best || toDecimal(p) > toDecimal(best.price)) best = { price: p, book: b.book };
  }
  return best;
}

function spreadHomeCoverProb(g: SlateGame, defaultPrice: number): number | null {
  if (!g.spread) return null;
  const hp = g.spread.home_price ?? defaultPrice;
  const ap = g.spread.away_price ?? defaultPrice;
  return devig(impliedProb(hp), impliedProb(ap)).p1;
}

// Pick the margin sigma that best reconciles each game's spread with its moneyline.
export function calibrateSigma(slate: Slate): { sigma: number; n: number } {
  const def = slate.default_price ?? -110;
  const pairs = slate.games
    .map(g => ({ g, ml: consensusMl(g).p, cover: spreadHomeCoverProb(g, def) }))
    .filter(x => x.ml !== null && x.cover !== null && x.g.spread) as Array<{ g: SlateGame; ml: number; cover: number }>;
  if (pairs.length < 3) return { sigma: NFL_MARGIN_SIGMA, n: pairs.length };
  let best = { sigma: NFL_MARGIN_SIGMA, err: Infinity };
  for (let s = 9; s <= 16.001; s += 0.25) {
    let err = 0;
    for (const { g, ml, cover } of pairs) {
      const mu = fitMuToSpread(g.spread!.home, cover, s);
      err += (pmfWinProb(nflMarginPmf(mu, s)) - ml) ** 2;
    }
    if (err < best.err) best = { sigma: round(s, 2), err };
  }
  return { sigma: best.sigma, n: pairs.length };
}

function option(
  base: Omit<BetOption, "ev_pct" | "half_kelly_pct">,
): BetOption {
  return {
    ...base,
    fair_prob: round(base.fair_prob, 4),
    push_prob: round(base.push_prob, 4),
    ev_pct: round(ev(base.fair_prob, base.price) * (1 - base.push_prob) * 100, 2),
    half_kelly_pct: round(halfKelly(base.fair_prob, base.price) * 100, 2),
  };
}

export function analyzeGame(g: SlateGame, sigma: number, defaultPrice = -110): GameAnalysis {
  const flags: string[] = [];
  const { p: mlProb, n } = consensusMl(g);
  const coverProb = spreadHomeCoverProb(g, defaultPrice);

  const muMl = mlProb !== null ? fitMuToWinProb(mlProb, sigma) : null;
  const muSpread = g.spread && coverProb !== null ? fitMuToSpread(g.spread.home, coverProb, sigma) : null;
  if (muMl === null && muSpread === null) throw new Error(`${g.id}: needs a moneyline or a spread`);
  const mu = muMl !== null && muSpread !== null ? (muMl + muSpread) / 2 : (muMl ?? muSpread)!;
  const pmf = nflMarginPmf(mu, sigma);
  const homeWin = pmfWinProb(pmf);

  const spreadImplied = muSpread !== null ? pmfWinProb(nflMarginPmf(muSpread, sigma)) : null;
  const gap = mlProb !== null && spreadImplied !== null ? (mlProb - spreadImplied) * 100 : null;
  if (gap !== null && Math.abs(gap) >= 3) {
    const juiceNote = g.spread?.home_price == null ? " (spread juice not in source — assumed -110; confirm before acting)" : "";
    flags.push(`ML_SPREAD_DISAGREE: ML says ${(mlProb! * 100).toFixed(1)}% vs spread-implied ${(spreadImplied! * 100).toFixed(1)}% — the cheaper market is on the ${gap > 0 ? "home spread / away ML" : "home ML / away spread"}${juiceNote}`);
  }
  if (n === 0) flags.push("NO_TWO_SIDED_MONEYLINE");
  if (!g.spread?.home_price) flags.push("SPREAD_PRICE_ASSUMED_-110");

  const options: BetOption[] = [];
  for (const side of ["home", "away"] as const) {
    const bp = bestPrice(g, side);
    if (!bp) continue;
    const p = side === "home" ? homeWin : 1 - homeWin;
    options.push(option({ game: g.id, market: "ML", selection: `${side === "home" ? g.home : g.away} ML`, price: bp.price, book: bp.book, fair_prob: p, push_prob: 0, price_assumed: false, side, line: null }));
  }
  if (g.spread) {
    const line = g.spread.home;
    const r = pmfCover(pmf, line);
    const pHome = noPushProb(r);
    const hp = g.spread.home_price ?? defaultPrice;
    const ap = g.spread.away_price ?? defaultPrice;
    const assumed = g.spread.home_price == null;
    options.push(option({ game: g.id, market: "SPREAD", selection: `${g.home} ${line > 0 ? "+" : ""}${line}`, price: hp, book: "spread source", fair_prob: pHome, push_prob: r.push, price_assumed: assumed, side: "home", line }));
    options.push(option({ game: g.id, market: "SPREAD", selection: `${g.away} ${-line > 0 ? "+" : ""}${-line}`, price: ap, book: "spread source", fair_prob: 1 - pHome, push_prob: r.push, price_assumed: assumed, side: "away", line: -line }));
  }
  let totalMean: number | null = null;
  if (g.total) {
    const op = g.total.over_price ?? defaultPrice;
    const up = g.total.under_price ?? defaultPrice;
    const overFair = devig(impliedProb(op), impliedProb(up)).p1;
    totalMean = fitTotalMean(g.total.points, overFair);
    const r = totalOverProb(totalMean, g.total.points);
    const pOver = r.over / (r.over + r.under);
    const assumed = g.total.over_price == null;
    options.push(option({ game: g.id, market: "TOTAL", selection: `${g.id} Over ${g.total.points}`, price: op, book: "total source", fair_prob: pOver, push_prob: r.push, price_assumed: assumed, side: "over", line: g.total.points }));
    options.push(option({ game: g.id, market: "TOTAL", selection: `${g.id} Under ${g.total.points}`, price: up, book: "total source", fair_prob: 1 - pOver, push_prob: r.push, price_assumed: assumed, side: "under", line: g.total.points }));
  }

  return {
    id: g.id, away: g.away, home: g.home, kickoff_et: g.kickoff_et,
    consensus_home_ml_prob: mlProb !== null ? round(mlProb, 4) : null,
    books_with_ml: n,
    spread_home: g.spread?.home ?? null,
    spread_implied_home_win: spreadImplied !== null ? round(spreadImplied, 4) : null,
    ml_vs_spread_gap_pct: gap !== null ? round(gap, 2) : null,
    mu: round(mu, 2),
    total_mean: totalMean !== null ? round(totalMean, 2) : null,
    fair_home_ml: formatAmerican(homeWin >= 0.5 ? Math.round(-100 * homeWin / (1 - homeWin)) : Math.round(100 * (1 - homeWin) / homeWin)),
    fair_spread_line: Math.round(-mu * 2) / 2,
    options,
    flags,
    notes: g.notes ?? [],
  };
}

// Did a bet win in one simulated outcome? Returns 1 win, 0 loss, 0.5 push (treated as no-action)
function grade(o: BetOption, margin: number, total: number): 1 | 0 | 0.5 {
  if (o.market === "ML") {
    if (margin === 0) return 0.5;
    return (o.side === "home" ? margin > 0 : margin < 0) ? 1 : 0;
  }
  if (o.market === "SPREAD") {
    const r = (o.side === "home" ? margin : -margin) + o.line!;
    return r > 0 ? 1 : r < 0 ? 0 : 0.5;
  }
  const r = o.side === "over" ? total - o.line! : o.line! - total;
  return r > 0 ? 1 : r < 0 ? 0 : 0.5;
}

export function simulateSlate(slate: Slate, opts: { sims?: number; seed?: number; sigma?: number } = {}): SlateReport {
  const sims = opts.sims ?? 100_000;
  const seed = opts.seed ?? 20260927;
  const cal = calibrateSigma(slate);
  const sigma = opts.sigma ?? cal.sigma;
  const def = slate.default_price ?? -110;
  const games = slate.games.map(g => analyzeGame(g, sigma, def));

  const ranked = games.flatMap(g => g.options).sort((a, b) => b.ev_pct - a.ev_pct);

  // Monte Carlo: sample every game `sims` times
  const next = rng(seed);
  const samplers = games.map(g => pmfSampler(nflMarginPmf(g.mu, sigma)));
  const upsetCounts = new Map<number, number>();
  const coverCounts = new Map<number, number>();
  // Candidate parlays: top-EV leg per game, then best 2- and 3-leg combos across different games
  const bestPerGame = new Map<string, BetOption>();
  for (const o of ranked) if (!bestPerGame.has(o.game) && !o.price_assumed) bestPerGame.set(o.game, o);
  const legPool = [...bestPerGame.values()].slice(0, 6);
  const combos: BetOption[][] = [];
  for (let i = 0; i < legPool.length; i++)
    for (let j = i + 1; j < legPool.length; j++) {
      combos.push([legPool[i], legPool[j]]);
      for (let k = j + 1; k < legPool.length; k++) combos.push([legPool[i], legPool[j], legPool[k]]);
    }
  // A push leg is counted as a parlay miss here (conservative: books would shorten the parlay instead)
  const comboWins = combos.map(() => 0);

  const gameIndex = new Map(games.map((g, i) => [g.id, i]));
  const margins = new Array<number>(games.length);
  const totals = new Array<number>(games.length);
  let expectedUpsets = 0, expectedCovers = 0;

  for (let s = 0; s < sims; s++) {
    let upsets = 0, covers = 0;
    for (let i = 0; i < games.length; i++) {
      const g = games[i];
      const m = samplers[i](next());
      margins[i] = m;
      totals[i] = g.total_mean !== null ? Math.max(0, Math.round(g.total_mean + NFL_TOTAL_SIGMA * gaussian(next))) : 0;
      const homeFav = g.mu >= 0;
      if (m !== 0 && (homeFav ? m < 0 : m > 0)) upsets++;
      if (g.spread_home !== null) {
        const favSide = g.spread_home <= 0 ? 1 : -1;
        const r = favSide * m + (favSide === 1 ? g.spread_home : -g.spread_home);
        if (r > 0) covers++;
      }
    }
    upsetCounts.set(upsets, (upsetCounts.get(upsets) ?? 0) + 1);
    coverCounts.set(covers, (coverCounts.get(covers) ?? 0) + 1);
    expectedUpsets += upsets; expectedCovers += covers;
    for (let c = 0; c < combos.length; c++) {
      let allWin = true;
      for (const leg of combos[c]) {
        const i = gameIndex.get(leg.game)!;
        if (grade(leg, margins[i], totals[i]) !== 1) { allWin = false; break; }
      }
      if (allWin) comboWins[c]++;
    }
  }

  const pAtLeast: Record<number, number> = {};
  const sortedUpsets = [...upsetCounts.keys()].sort((a, b) => a - b);
  for (const k of sortedUpsets) {
    let c = 0;
    for (const [u, n] of upsetCounts) if (u >= k) c += n;
    pAtLeast[k] = round(c / sims, 4);
  }
  const coverDist: Record<number, number> = {};
  for (const k of [...coverCounts.keys()].sort((a, b) => a - b)) coverDist[k] = round(coverCounts.get(k)! / sims, 4);

  const parlays: ParlayEval[] = combos.map((legs, c) => {
    const price = parlayPrice(legs.map(l => l.price));
    const analytic = legs.reduce((acc, l) => acc * l.fair_prob, 1);
    const mc = comboWins[c] / sims;
    return {
      legs: legs.map(l => `${l.selection} (${formatAmerican(l.price)}, ${l.book})`),
      price: formatAmerican(price.american),
      analytic_prob: round(analytic, 4),
      mc_prob: round(mc, 4),
      ev_pct: round((mc * price.decimal - 1) * 100, 2),
    };
  }).sort((a, b) => b.ev_pct - a.ev_pct).slice(0, 5);

  return {
    slate: slate.slate, sport: slate.sport, captured_at: slate.captured_at, capture_method: slate.capture_method,
    sigma, sigma_calibrated_from: cal.n, sims, seed,
    games, ranked,
    upsets: { expected: round(expectedUpsets / sims, 2), p_at_least: pAtLeast },
    favorites_covering: { expected: round(expectedCovers / sims, 2), distribution: coverDist },
    parlays,
  };
}

// ── The Odds API → Slate (for --live runs) ───────────────────────────────────
export interface OddsApiEvent {
  id: string;
  commence_time: string;
  home_team: string;
  away_team: string;
  bookmakers: Array<{ key: string; title?: string; markets: Array<{ key: string; outcomes: Array<{ name: string; price: number; point?: number }> }> }>;
}

export function oddsEventsToSlate(events: OddsApiEvent[], slateName: string, sport: string, spreadBookPriority = ["pinnacle", "draftkings", "fanduel"]): Slate {
  const games: SlateGame[] = events.map(e => {
    const moneylines: BookMoneyline[] = [];
    for (const b of e.bookmakers) {
      const h2h = b.markets.find(m => m.key === "h2h");
      if (!h2h) continue;
      moneylines.push({
        book: b.title ?? b.key,
        home: h2h.outcomes.find(o => o.name === e.home_team)?.price ?? null,
        away: h2h.outcomes.find(o => o.name === e.away_team)?.price ?? null,
      });
    }
    const pick = (key: string) => {
      for (const bk of spreadBookPriority) {
        const m = e.bookmakers.find(b => b.key === bk)?.markets.find(mk => mk.key === key);
        if (m) return m;
      }
      return e.bookmakers.map(b => b.markets.find(mk => mk.key === key)).find(Boolean);
    };
    const sp = pick("spreads");
    const hs = sp?.outcomes.find(o => o.name === e.home_team);
    const as = sp?.outcomes.find(o => o.name === e.away_team);
    const tot = pick("totals");
    const ov = tot?.outcomes.find(o => o.name === "Over");
    const un = tot?.outcomes.find(o => o.name === "Under");
    return {
      id: `${e.away_team} @ ${e.home_team}`,
      away: e.away_team,
      home: e.home_team,
      kickoff_et: new Date(e.commence_time).toLocaleString("en-US", { timeZone: "America/New_York", weekday: "short", hour: "2-digit", minute: "2-digit" }),
      spread: hs?.point != null ? { home: hs.point, home_price: hs.price, away_price: as?.price } : undefined,
      total: ov?.point != null ? { points: ov.point, over_price: ov.price, under_price: un?.price } : undefined,
      moneylines,
    };
  });
  return { slate: slateName, sport, captured_at: new Date().toISOString(), capture_method: "The Odds API (live)", games };
}
