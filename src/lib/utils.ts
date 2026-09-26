import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

/**
 * Professional Kelly Criterion Calculation
 * b = decimal odds - 1
 * p = probability of winning
 * q = probability of losing (1 - p)
 * Formula: f* = (bp - q) / b
 */
export function calculateKelly(winProb: number, odds: number, fractionalKelly = 0.25): number {
  const b = odds > 0 ? (odds / 100) : (100 / Math.abs(odds));
  const p = winProb;
  const q = 1 - p;
  const rawKelly = (b * p - q) / b;
  // Apply fractional Kelly for risk management (industry standard is 0.25 aka 'Quarter Kelly')
  return Math.max(0, rawKelly * fractionalKelly);
}

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatPercentage(value: number): string {
    return new Intl.NumberFormat('en-US', {
        style: 'percent',
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
    }).format(value);
}

export function formatOdds(odds: number): string {
    if (odds >= 2.0) {
        return `+${Math.round((odds - 1) * 100)}`;
    }
    return `-${Math.round(100 / (odds - 1))}`;
}
