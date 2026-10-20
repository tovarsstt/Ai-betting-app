// Glue: builds NBA state + fitted stacker from data/nba_historical.csv, exposes predictions.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { NbaState, fitEnsemble, predictEnsemble, type Game, type Row, type Fitted } from './nba.ts';
import { predictSoccer, type SoccerInput } from './soccer.ts';
import { devigProportional, americanToDecimal } from './odds.ts';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
let state: NbaState | null = null;
let fitted: Fitted | null = null;
const extra: Game[] = []; // results ingested at runtime

function build(): void {
  const rows = fs.readFileSync(path.join(root, 'data/nba_historical.csv'), 'utf8').trim().split('\n').slice(1);
  const games: Game[] = rows.map(l => { const c = l.split(','); return { date: c[1], home: c[2], away: c[3], hs: +c[4], as: +c[5], season: +c[6] }; })
    .concat(extra).sort((a, b) => a.date.localeCompare(b.date));
  const st = new NbaState();
  const train: Row[] = [];
  for (const g of games) {
    if (g.season !== st.season) st.newSeason(g.season, st.season < 0 ? 0 : g.season - st.season);
    train.push({ ctx: st.context(g.home, g.away, g.date), y: g.hs > g.as ? 1 : 0 });
    st.update(g);
  }
  state = st; fitted = fitEnsemble(train.slice(300));
}

export function ingestNbaResult(g: Game): void { extra.push(g); build(); }

function findTeam(q: string): string | null {
  if (!state) build();
  const s = q.toLowerCase().trim();
  const names = [...state!.teams.keys()];
  return names.find(n => n.toLowerCase() === s) ?? names.find(n => n.toLowerCase().includes(s) || s.includes(n.toLowerCase().split(' ').pop()!)) ?? null;
}

export interface NbaQuery { home: string; away: string; date?: string; homeMlAmerican?: number; awayMlAmerican?: number }
export function nbaPredict(q: NbaQuery) {
  if (!state) build();
  const h = findTeam(q.home), a = findTeam(q.away);
  if (!h || !a) return { error: `unknown team: ${!h ? q.home : q.away}` };
  const date = q.date ?? new Date().toISOString().slice(0, 10);
  const gapDays = (Date.parse(date) - Date.parse(state!.asOf)) / 86400000;
  // If the target date is in a later season than the data, regress ratings (without mutating shared state).
  let st = state!;
  if (gapDays > 120) { st = Object.assign(new NbaState(), { teams: new Map([...state!.teams].map(([k, v]) => [k, { ...v, recent: [...v.recent] }])), season: state!.season, asOf: state!.asOf }); const gap = Math.floor(gapDays / 365) + 1; st.newSeason(st.season + gap, gap); }
  const ctx = st.context(h, a, date);
  const out = predictEnsemble(fitted!, ctx);
  let market: undefined | { pHome: number; pAway: number; holdPct: number };
  if (q.homeMlAmerican != null && q.awayMlAmerican != null) {
    const d = devigProportional([americanToDecimal(q.homeMlAmerican), americanToDecimal(q.awayMlAmerican)]);
    market = { pHome: d.probs[0], pAway: d.probs[1], holdPct: d.overroundPct };
  }
  // Market is the stronger prior when our ratings are stale: blend model with devigged market.
  const stale = gapDays > 30;
  const wModel = market ? (stale ? 0.25 : 0.5) : 1;
  const pHome = market ? wModel * out.pHome + (1 - wModel) * market.pHome : out.pHome;
  return { home: h, away: a, pHome, pAway: 1 - pHome, modelOnlyPHome: out.pHome, wModel, base: out.base, weights: out.weights, market,
    ratingsAsOf: state!.asOf, stale: gapDays > 30, warning: gapDays > 30 ? `Ratings last updated ${state!.asOf} (${Math.round(gapDays)}d ago); post-2025 results not ingested — treat as low-confidence prior.` : undefined };
}

export function uclPredict(i: SoccerInput, market?: { homeDecimal: number; drawDecimal: number; awayDecimal: number }) {
  let m;
  if (market) { const d = devigProportional([market.homeDecimal, market.drawDecimal, market.awayDecimal]); m = { pHome: d.probs[0], pDraw: d.probs[1], pAway: d.probs[2] }; }
  return { ...predictSoccer(i, m), market: m };
}
