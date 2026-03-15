import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

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
