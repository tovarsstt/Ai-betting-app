// ── Pure betting math — no I/O, fully unit-tested (lib/betting-math.test.ts) ──
//
// Everything here is deterministic so the server can check the LLM's numbers
// instead of trusting them (combined parlay odds, EV, Kelly, overconfidence).

// American odds → raw implied probability (vig included)
export function impliedProb(americanOdds: number): number {
  if (americanOdds < 0) return (-americanOdds) / (-americanOdds + 100);
  return 100 / (americanOdds + 100);
}

// Remove bookmaker vig from a 2-way market → fair (no-vig) probabilities
export function devig(p1Raw: number, p2Raw: number): { p1: number; p2: number; vig: number } {
  const sum = p1Raw + p2Raw;
  return { p1: p1Raw / sum, p2: p2Raw / sum, vig: (sum - 1) * 100 };
}

// N-way devig (soccer 3-way h2h has a Draw outcome — a 2-way devig is wrong there)
export function devigMulti(rawProbs: number[]): { fair: number[]; vig: number } {
  const sum = rawProbs.reduce((a, b) => a + b, 0);
  return { fair: rawProbs.map(p => p / sum), vig: (sum - 1) * 100 };
}

// American odds → decimal odds
export function toDecimal(americanOdds: number): number {
  return americanOdds >= 0 ? americanOdds / 100 + 1 : 100 / (-americanOdds) + 1;
}

// Decimal odds → American odds (rounded to the nearest integer)
export function decimalToAmerican(decimal: number): number {
  if (decimal <= 1) throw new Error("decimal odds must be > 1");
  return decimal >= 2 ? Math.round((decimal - 1) * 100) : Math.round(-100 / (decimal - 1));
}

// Fair probability → fair American price (what a no-vig book would charge)
export function probToAmerican(p: number): number {
  if (p <= 0 || p >= 1) throw new Error("probability must be in (0, 1)");
  return decimalToAmerican(1 / p);
}

export function formatAmerican(n: number): string {
  return n > 0 ? `+${n}` : `${n}`;
}

// "+130" | "-115" | "EVEN" | "EV" | "PK" → number. Returns null for anything unparseable.
export function parseAmerican(raw: unknown): number | null {
  if (typeof raw === "number") return Number.isFinite(raw) && Math.abs(raw) >= 100 ? raw : null;
  if (typeof raw !== "string") return null;
  const s = raw.trim().toUpperCase();
  if (s === "EVEN" || s === "EV" || s === "EVENS") return 100;
  const m = s.match(/^([+-]?)(\d{3,6})$/);
  if (!m) return null;
  const n = Number(m[2]) * (m[1] === "-" ? -1 : 1);
  return Math.abs(n) >= 100 ? n : null;
}

// Expected value per 1 unit staked (0.05 = +5%)
export function ev(p: number, americanOdds: number): number {
  const b = toDecimal(americanOdds) - 1;
  return p * b - (1 - p);
}

// Half-Kelly fraction of bankroll (capped 0–25% for ruin prevention)
export function halfKelly(p: number, americanOdds: number): number {
  const b = toDecimal(americanOdds) - 1;
  if (b <= 0 || p <= 0) return 0;
  const fullKelly = (b * p - (1 - p)) / b;
  return Math.max(0, Math.min(fullKelly / 2, 0.25));
}

// Parlay price from independent legs. Books price SGPs with their own correlation
// adjustment, so for same-game legs this is only the independence baseline.
export function parlayPrice(legs: number[]): { decimal: number; american: number } {
  if (legs.length === 0) throw new Error("parlay needs at least one leg");
  const decimal = legs.reduce((acc, o) => acc * toDecimal(o), 1);
  return { decimal, american: decimalToAmerican(decimal) };
}

// Standard normal CDF — Abramowitz & Stegun 26.2.17, |error| < 7.5e-8
export function normalCDF(z: number): number {
  if (z < -8) return 0;
  if (z >  8) return 1;
  const p = 0.2316419;
  const b = [0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429];
  const t   = 1 / (1 + p * Math.abs(z));
  const y   = ((((b[4]*t + b[3])*t + b[2])*t + b[1])*t + b[0]) * t;
  const pdf = Math.exp(-0.5 * z * z) / Math.sqrt(2 * Math.PI);
  return z >= 0 ? 1 - pdf * y : pdf * y;
}

// Point margin → win probability via normal distribution
// sigma: std-dev of final margin around the expected margin (NBA ~11.5, NFL ~13.5)
export function marginToWinProb(margin: number, sigma = 11.5): number {
  return normalCDF(margin / sigma);
}

// ── NFL margin model ─────────────────────────────────────────────────────────
// Final margins cluster on key numbers (3, 7, 10, 14, 6) and almost never tie.
// A plain normal curve misprices -2.5 vs -3.5 badly, so we reweight a discrete
// normal by approximate historical frequencies of each absolute margin.
// These weights are rough public-knowledge approximations, NOT fitted to data
// in this repo — treat outputs as a market-consistency tool, not a forecast.
export const NFL_MARGIN_SIGMA = 13.5;
export const NFL_TOTAL_SIGMA = 10;

const NFL_KEY_WEIGHTS: Record<number, number> = {
  0: 0.05, 1: 0.7, 2: 0.6, 3: 2.6, 4: 0.9, 5: 0.65, 6: 1.1, 7: 1.8, 8: 0.9,
  9: 0.8, 10: 1.3, 11: 0.7, 12: 0.75, 13: 0.7, 14: 1.4, 15: 0.8, 16: 0.9, 17: 1.1,
};

export type Pmf = Map<number, number>;

// Discrete PMF of (home score − away score), mean ≈ mu
export function nflMarginPmf(mu: number, sigma = NFL_MARGIN_SIGMA): Pmf {
  const pmf: Pmf = new Map();
  let total = 0;
  for (let m = -70; m <= 70; m++) {
    const base = normalCDF((m + 0.5 - mu) / sigma) - normalCDF((m - 0.5 - mu) / sigma);
    const w = NFL_KEY_WEIGHTS[Math.abs(m)] ?? 1;
    const mass = base * w;
    pmf.set(m, mass);
    total += mass;
  }
  for (const [m, v] of pmf) pmf.set(m, v / total);
  return pmf;
}

// P(home wins) counting ties as half (ties are ~0.3% in the NFL)
export function pmfWinProb(pmf: Pmf): number {
  let p = 0;
  for (const [m, v] of pmf) p += m > 0 ? v : m === 0 ? v / 2 : 0;
  return p;
}

// P(win/push/loss) for a bet on the home side at `line` (home -3 → line = -3)
export function pmfCover(pmf: Pmf, line: number): { win: number; push: number; loss: number } {
  let win = 0, push = 0, loss = 0;
  for (const [m, v] of pmf) {
    const r = m + line;
    if (r > 1e-9) win += v; else if (r < -1e-9) loss += v; else push += v;
  }
  return { win, push, loss };
}

// Win probability conditional on no push — the right number to compare to a devigged spread price
export function noPushProb(r: { win: number; push: number; loss: number }): number {
  return r.win / (r.win + r.loss);
}

// Bisection: find expected margin mu so that f(mu) hits the target probability.
function bisect(f: (mu: number) => number, target: number, lo = -40, hi = 40): number {
  for (let i = 0; i < 80; i++) {
    const mid = (lo + hi) / 2;
    if (f(mid) < target) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
}

// mu such that the model's home win prob equals the (devigged) market ML prob
export function fitMuToWinProb(homeWinProb: number, sigma = NFL_MARGIN_SIGMA): number {
  return bisect(mu => pmfWinProb(nflMarginPmf(mu, sigma)), homeWinProb);
}

// mu such that P(home covers `line`, no-push basis) equals the devigged spread price
export function fitMuToSpread(line: number, homeCoverProb: number, sigma = NFL_MARGIN_SIGMA): number {
  return bisect(mu => noPushProb(pmfCover(nflMarginPmf(mu, sigma), line)), homeCoverProb);
}

// Totals: continuous normal around the market total. Integer totals push.
export function totalOverProb(mean: number, line: number, sigma = NFL_TOTAL_SIGMA): { over: number; push: number; under: number } {
  if (Number.isInteger(line)) {
    const push = normalCDF((line + 0.5 - mean) / sigma) - normalCDF((line - 0.5 - mean) / sigma);
    const under = normalCDF((line - 0.5 - mean) / sigma);
    return { over: 1 - under - push, push, under };
  }
  const under = normalCDF((line - mean) / sigma);
  return { over: 1 - under, push: 0, under };
}

export function fitTotalMean(line: number, overProb: number, sigma = NFL_TOTAL_SIGMA): number {
  return bisect(mu => {
    const r = totalOverProb(mu, line, sigma);
    return r.over / (r.over + r.under);
  }, overProb, 0, 120);
}

// ── Pick audit — check an LLM pick against the math ──────────────────────────
export interface PickAudit {
  odds: number | null;
  breakeven_prob: number | null;   // implied prob of the price (vig included)
  model_prob: number | null;       // what the pick claimed
  edge_pct: number | null;         // model_prob − breakeven, in % points
  ev_pct: number | null;           // EV per unit, %
  half_kelly_pct: number | null;   // % of bankroll
  flags: string[];
}

// Anything claiming >10 points of edge over the price is almost always a miscalibrated model.
export const MAX_CREDIBLE_EDGE = 0.10;

export function auditPick(oddsRaw: unknown, winProbRaw: unknown): PickAudit {
  const odds = parseAmerican(oddsRaw);
  const p = typeof winProbRaw === "number" && winProbRaw > 0 && winProbRaw < 1 ? winProbRaw : null;
  const flags: string[] = [];
  if (odds === null) flags.push("ODDS_UNPARSEABLE");
  if (p === null) flags.push("NO_WIN_PROB");
  if (odds === null || p === null) {
    return { odds, breakeven_prob: odds === null ? null : round(impliedProb(odds), 4), model_prob: p, edge_pct: null, ev_pct: null, half_kelly_pct: null, flags };
  }
  const be = impliedProb(odds);
  const edge = p - be;
  if (edge > MAX_CREDIBLE_EDGE) flags.push("OVERCONFIDENT_EDGE");
  if (edge <= 0) flags.push("NEGATIVE_EV");
  return {
    odds,
    breakeven_prob: round(be, 4),
    model_prob: p,
    edge_pct: round(edge * 100, 1),
    ev_pct: round(ev(p, odds) * 100, 1),
    half_kelly_pct: round(halfKelly(p, odds) * 100, 2),
    flags,
  };
}

export function round(x: number, dp: number): number {
  const f = 10 ** dp;
  return Math.round(x * f) / f;
}

// Deterministic PRNG (mulberry32) so simulations are reproducible
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Sample an integer from a PMF via its CDF
export function pmfSampler(pmf: Pmf): (u: number) => number {
  const keys = [...pmf.keys()].sort((a, b) => a - b);
  const cdf: number[] = [];
  let acc = 0;
  for (const k of keys) { acc += pmf.get(k)!; cdf.push(acc); }
  return (u: number) => {
    let lo = 0, hi = cdf.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (cdf[mid] < u) lo = mid + 1; else hi = mid;
    }
    return keys[lo];
  };
}

// Box–Muller standard normal from a uniform generator
export function gaussian(next: () => number): number {
  let u = 0;
  while (u === 0) u = next();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * next());
}
