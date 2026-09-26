// ── Pure betting math utilities ──────────────────────────────────────────────

// American odds → raw implied probability (vig included)
export function impliedProb(americanOdds: number): number {
  if (americanOdds < 0) return (-americanOdds) / (-americanOdds + 100);
  return 100 / (americanOdds + 100);
}

// Remove bookmaker vig from a 2-way market → fair (true) probabilities
export function devig(p1Raw: number, p2Raw: number): { p1: number; p2: number; vig: number } {
  const sum = p1Raw + p2Raw;
  return { p1: p1Raw / sum, p2: p2Raw / sum, vig: (sum - 1) * 100 };
}

// American odds → decimal odds
export function toDecimal(americanOdds: number): number {
  return americanOdds >= 0 ? americanOdds / 100 + 1 : 100 / (-americanOdds) + 1;
}

// Half-Kelly fraction — how much of bankroll to bet (capped 0–25% for ruin prevention)
// p = true win probability, americanOdds = line being bet
export function halfKelly(p: number, americanOdds: number): number {
  const b = toDecimal(americanOdds) - 1;
  if (b <= 0 || p <= 0 || p >= 1) return 0;
  const fullKelly = (b * p - (1 - p)) / b;
  return Math.max(0, Math.min(fullKelly / 2, 0.25));
}

// Expected Value as decimal (positive = +EV)
export function ev(p: number, americanOdds: number): number {
  const b = toDecimal(americanOdds) - 1;
  return p * b - (1 - p);
}

// Standard normal CDF — Hart approximation, accurate to 5 decimal places
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
// sigma: std-dev of final margin (NBA ~11.5, NFL ~13.5, MLB ~3.0 runs)
export function marginToWinProb(margin: number, sigma = 11.5): number {
  return normalCDF(margin / sigma);
}
