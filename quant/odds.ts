// Odds / probability conversions. Report order everywhere: P(win) -> odds/payout -> EV.

export const americanToDecimal = (a: number): number => (a >= 0 ? a / 100 + 1 : 100 / -a + 1);
export const decimalToAmerican = (d: number): number => (d >= 2 ? Math.round((d - 1) * 100) : Math.round(-100 / (d - 1)));
export const impliedFromDecimal = (d: number): number => 1 / d;

// Proportional (multiplicative) devig for an n-way market. Returns fair probs summing to 1 and overround %.
export function devigProportional(decimalOdds: number[]): { probs: number[]; overroundPct: number } {
  const raw = decimalOdds.map(impliedFromDecimal);
  const s = raw.reduce((a, b) => a + b, 0);
  return { probs: raw.map(p => p / s), overroundPct: (s - 1) * 100 };
}

export const evPerUnit = (p: number, decimalOdds: number): number => p * (decimalOdds - 1) - (1 - p);

// Quarter-Kelly stake as fraction of bankroll, capped (default 5%).
export function kellyFraction(p: number, decimalOdds: number, fraction = 0.25, cap = 0.05): number {
  const b = decimalOdds - 1;
  if (b <= 0) return 0;
  const f = (b * p - (1 - p)) / b;
  return f <= 0 ? 0 : Math.min(f * fraction, cap);
}
