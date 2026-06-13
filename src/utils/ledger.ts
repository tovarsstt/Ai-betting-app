// ── Pick ledger — the proven-record engine ────────────────────────────────────
// Every pick logged at post time, settled with result + closing odds.
// Stats prove (or disprove) the edge: record, units, ROI, CLV beat rate.

import { promises as fs } from 'fs';
import path from 'path';
import { randomUUID } from 'crypto';
import { toDecimal } from './mathUtils.js';

export type PickResult = 'W' | 'L' | 'P' | 'PENDING';

export interface LedgerPick {
  id: string;
  created_at: string;        // ISO — when pick was posted
  sport: string;
  game: string;
  selection: string;         // e.g. "Celtics -4.5"
  odds: number;              // American odds at post time
  stake_units: number;
  closing_odds: number | null; // American odds at game start — for CLV
  result: PickResult;
  settled_at: string | null;
  source: string;            // 'prophet' | 'analyze' | 'manual'
  // Structured market identity — lets the CLV cron re-find the exact line at
  // kickoff. Nullable: legacy picks and unparseable selections (AH/props) lack it.
  market_key?: string | null;  // 'h2h' | 'spreads'
  outcome?: string | null;     // outcome/team name as it appears in the odds feed
  point?: number | null;       // spread handicap (null for moneyline)
}

export interface LedgerStats {
  total: number;
  pending: number;
  wins: number;
  losses: number;
  pushes: number;
  win_rate_pct: number | null;
  units_staked: number;
  units_profit: number;
  roi_pct: number | null;
  avg_clv_pct: number | null;     // mean closing line value across settled picks
  clv_beat_rate_pct: number | null; // % of picks that beat the close
  max_drawdown_units: number;     // worst peak-to-trough dip of cumulative profit
  profit_factor: number | null;   // gross units won / gross units lost (>1 = profitable)
  current_streak: string;          // e.g. "W4" / "L2"
  by_sport: Record<string, { wins: number; losses: number; units_profit: number }>;
}

const LEDGER_PATH = path.resolve(process.cwd(), 'data/pick_ledger.json');

export async function loadLedger(): Promise<LedgerPick[]> {
  try {
    const raw = await fs.readFile(LEDGER_PATH, 'utf8');
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed as LedgerPick[] : [];
  } catch {
    return [];
  }
}

// Atomic write: tmp file + rename so a crash can't corrupt the record
async function saveLedger(picks: LedgerPick[]): Promise<void> {
  const tmp = `${LEDGER_PATH}.tmp`;
  await fs.writeFile(tmp, JSON.stringify(picks, null, 2), 'utf8');
  await fs.rename(tmp, LEDGER_PATH);
}

export interface NewPickInput {
  sport: string;
  game: string;
  selection: string;
  odds: number;
  stake_units?: number;
  source?: string;
  market_key?: string | null;
  outcome?: string | null;
  point?: number | null;
}

// True if an identical engine pick is already logged and pending — prevents
// the auto-logger from double-counting cached/repeated prophet responses.
export async function hasPendingDuplicate(selection: string, game: string): Promise<boolean> {
  const ledger = await loadLedger();
  const norm = (s: string) => s.toLowerCase().trim();
  return ledger.some(p =>
    p.result === 'PENDING' &&
    norm(p.selection) === norm(selection) &&
    norm(p.game) === norm(game)
  );
}

export async function addPick(input: NewPickInput): Promise<LedgerPick> {
  const pick: LedgerPick = {
    id: randomUUID().slice(0, 8),
    created_at: new Date().toISOString(),
    sport: input.sport.toUpperCase(),
    game: input.game,
    selection: input.selection,
    odds: input.odds,
    stake_units: input.stake_units ?? 1,
    closing_odds: null,
    result: 'PENDING',
    settled_at: null,
    source: input.source ?? 'manual',
    market_key: input.market_key ?? null,
    outcome: input.outcome ?? null,
    point: input.point ?? null,
  };
  const ledger = await loadLedger();
  await saveLedger([...ledger, pick]);
  return pick;
}

export type SettleError = 'NOT_FOUND' | 'ALREADY_SETTLED';

export async function settlePick(
  id: string,
  result: Exclude<PickResult, 'PENDING'>,
  closingOdds?: number,
): Promise<LedgerPick | SettleError> {
  const ledger = await loadLedger();
  const idx = ledger.findIndex(p => p.id === id);
  if (idx === -1) return 'NOT_FOUND';
  // Record integrity: a settled pick is IMMUTABLE. Allowing W→L rewrites
  // would make the public track record falsifiable — credibility death.
  if (ledger[idx].result !== 'PENDING') return 'ALREADY_SETTLED';
  const settled: LedgerPick = {
    ...ledger[idx],
    result,
    closing_odds: closingOdds ?? ledger[idx].closing_odds,
    settled_at: new Date().toISOString(),
  };
  const next = [...ledger.slice(0, idx), settled, ...ledger.slice(idx + 1)];
  await saveLedger(next);
  return settled;
}

export type StampError = 'NOT_FOUND' | 'ALREADY_SET' | 'SETTLED';

// Stamp the closing line on a still-PENDING pick (CLV capture, pre-settle).
// Won't touch a settled pick or overwrite a close already recorded — the record
// stays tamper-evident.
export async function stampClosingOdds(id: string, closingOdds: number): Promise<LedgerPick | StampError> {
  const ledger = await loadLedger();
  const idx = ledger.findIndex(p => p.id === id);
  if (idx === -1) return 'NOT_FOUND';
  if (ledger[idx].result !== 'PENDING') return 'SETTLED';
  if (ledger[idx].closing_odds != null) return 'ALREADY_SET';
  const updated: LedgerPick = { ...ledger[idx], closing_odds: closingOdds };
  await saveLedger([...ledger.slice(0, idx), updated, ...ledger.slice(idx + 1)]);
  return updated;
}

// CLV%: how much better your odds were than the close. Positive = beat the market.
export function clvPct(betOdds: number, closingOdds: number): number {
  return (toDecimal(betOdds) / toDecimal(closingOdds) - 1) * 100;
}

function profitUnits(p: LedgerPick): number {
  if (p.result === 'W') return p.stake_units * (toDecimal(p.odds) - 1);
  if (p.result === 'L') return -p.stake_units;
  return 0; // push or pending
}

export function computeStats(ledger: LedgerPick[]): LedgerStats {
  const settled = ledger.filter(p => p.result !== 'PENDING');
  const wins = settled.filter(p => p.result === 'W').length;
  const losses = settled.filter(p => p.result === 'L').length;
  const pushes = settled.filter(p => p.result === 'P').length;
  const decided = wins + losses;

  const unitsStaked = settled.reduce((s, p) => s + p.stake_units, 0);
  const unitsProfit = settled.reduce((s, p) => s + profitUnits(p), 0);

  const withClose = settled.filter(p => p.closing_odds != null);
  const clvs = withClose.map(p => clvPct(p.odds, p.closing_odds as number));
  const avgClv = clvs.length ? clvs.reduce((a, b) => a + b, 0) / clvs.length : null;
  const beatRate = clvs.length ? (clvs.filter(c => c > 0).length / clvs.length) * 100 : null;

  // Profit factor: gross wins / gross losses — stability measure beyond raw ROI
  const grossWon = settled.reduce((s, p) => s + Math.max(0, profitUnits(p)), 0);
  const grossLost = settled.reduce((s, p) => s + Math.max(0, -profitUnits(p)), 0);
  const profitFactor = grossLost > 0 ? grossWon / grossLost : null;

  // Max drawdown: worst peak-to-trough dip of cumulative profit, chronological order
  const chronological = [...settled].sort((a, b) => (a.settled_at ?? '').localeCompare(b.settled_at ?? ''));
  let peak = 0;
  let cumulative = 0;
  let maxDrawdown = 0;
  for (const p of chronological) {
    cumulative += profitUnits(p);
    peak = Math.max(peak, cumulative);
    maxDrawdown = Math.max(maxDrawdown, peak - cumulative);
  }

  // Streak: walk settled picks newest-first until result changes
  let streak = '';
  const decidedSorted = settled
    .filter(p => p.result === 'W' || p.result === 'L')
    .sort((a, b) => (b.settled_at ?? '').localeCompare(a.settled_at ?? ''));
  if (decidedSorted.length) {
    const r = decidedSorted[0].result;
    let n = 0;
    for (const p of decidedSorted) { if (p.result === r) n++; else break; }
    streak = `${r}${n}`;
  }

  const bySport: LedgerStats['by_sport'] = {};
  for (const p of settled) {
    const cur = bySport[p.sport] ?? { wins: 0, losses: 0, units_profit: 0 };
    bySport[p.sport] = {
      wins: cur.wins + (p.result === 'W' ? 1 : 0),
      losses: cur.losses + (p.result === 'L' ? 1 : 0),
      units_profit: Math.round((cur.units_profit + profitUnits(p)) * 100) / 100,
    };
  }

  return {
    total: ledger.length,
    pending: ledger.length - settled.length,
    wins, losses, pushes,
    win_rate_pct: decided ? Math.round((wins / decided) * 1000) / 10 : null,
    units_staked: Math.round(unitsStaked * 100) / 100,
    units_profit: Math.round(unitsProfit * 100) / 100,
    roi_pct: unitsStaked ? Math.round((unitsProfit / unitsStaked) * 1000) / 10 : null,
    avg_clv_pct: avgClv != null ? Math.round(avgClv * 100) / 100 : null,
    clv_beat_rate_pct: beatRate != null ? Math.round(beatRate * 10) / 10 : null,
    max_drawdown_units: Math.round(maxDrawdown * 100) / 100,
    profit_factor: profitFactor != null ? Math.round(profitFactor * 100) / 100 : null,
    current_streak: streak,
    by_sport: bySport,
  };
}
