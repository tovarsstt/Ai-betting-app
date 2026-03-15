import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPercentage(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`;
}

export function formatOdds(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value > 0 ? `+${value}` : `${value}`;
}
