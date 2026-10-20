// Report formatting. Mandatory order: P(win) first, then odds/payout, EV last.
import { americanToDecimal, decimalToAmerican, devigProportional, evPerUnit, kellyFraction } from './odds.ts';

export interface PickLine { label: string; pWin: number; marketOdds?: number /* decimal */; marketFair?: number }

export function formatPick(p: PickLine, bankroll = 100): string {
  const lines = [`${p.label}`, `  P(win): ${(p.pWin * 100).toFixed(1)}%  (fair odds ${(1 / p.pWin).toFixed(2)} / ${fmtAm(decimalToAmerican(1 / p.pWin))})`];
  if (p.marketOdds) {
    const stake = bankroll * kellyFraction(p.pWin, p.marketOdds);
    lines.push(`  Odds: ${p.marketOdds.toFixed(2)} (${fmtAm(decimalToAmerican(p.marketOdds))}) | $10 pays $${(10 * p.marketOdds).toFixed(2)}${p.marketFair != null ? ` | market fair P ${(p.marketFair * 100).toFixed(1)}%` : ''}`);
    const ev = evPerUnit(p.pWin, p.marketOdds);
    lines.push(`  EV: ${ev >= 0 ? '+' : ''}${(ev * 100).toFixed(1)}% per unit | 1/4-Kelly stake: $${stake.toFixed(2)} of $${bankroll}${ev <= 0 ? ' -> NO BET' : ''}`);
  } else lines.push('  Odds: n/a (no live line) | EV: n/a');
  return lines.join('\n');
}
const fmtAm = (a: number): string => (a > 0 ? `+${a}` : `${a}`);
export { americanToDecimal, devigProportional };
