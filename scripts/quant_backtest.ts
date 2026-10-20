// Walk-forward backtest of the NBA stacked ensemble on data/nba_historical.csv.
// Run: node --experimental-strip-types scripts/quant_backtest.ts
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { NbaState, fitEnsemble, predictEnsemble, baseA, baseB, type Game, type Row, type Ctx } from '../quant/nba.ts';
import { logLoss, brier, accuracy } from '../quant/math.ts';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const lines = fs.readFileSync(path.join(root, 'data/nba_historical.csv'), 'utf8').trim().split('\n').slice(1);
const games: Game[] = lines.map(l => {
  const c = l.split(',');
  return { date: c[1], home: c[2], away: c[3], hs: +c[4], as: +c[5], season: +c[6] };
}).sort((a, b) => a.date.localeCompare(b.date));
console.log(`games=${games.length} range=${games[0].date}..${games[games.length - 1].date}`);

const TEST_SEASON = 2024, REFIT_EVERY = 100, WARMUP = 300;
const st = new NbaState();
const train: Row[] = [];
let fit: ReturnType<typeof fitEnsemble> | null = null;
const P: Record<string, number[]> = { home_always: [], elo_only: [], form_only: [], simple_avg: [], stacked: [] };
const Y: number[] = [];
let sinceFit = 0;
const wSample: { early: number[][]; late: number[][] } = { early: [], late: [] };

for (const g of games) {
  if (g.season !== st.season) st.newSeason(g.season, st.season < 0 ? 0 : g.season - st.season);
  const ctx: Ctx = st.context(g.home, g.away, g.date);
  const y = g.hs > g.as ? 1 : 0;
  if (g.season === TEST_SEASON && fit) {
    const out = predictEnsemble(fit, ctx);
    const a = baseA(ctx), b = baseB(ctx);
    P.home_always.push(train.length ? train.reduce((a, r) => a + r.y, 0) / train.length : 0.5); // running home-win rate
    P.elo_only.push(a); P.form_only.push(b); P.simple_avg.push((a + b + out.base.context) / 3);
    P.stacked.push(out.pHome); Y.push(y);
    (ctx.early ? wSample.early : wSample.late).push([out.weights.strength, out.weights.form, out.weights.context]);
  }
  if (g.season < TEST_SEASON || fit) train.push({ ctx, y }); // only past games enter training
  if (g.season === TEST_SEASON) { /* test games appended after prediction -> walk-forward */ }
  st.update(g);
  sinceFit++;
  if (train.length >= WARMUP && (!fit || sinceFit >= REFIT_EVERY) && g.season >= TEST_SEASON - 1) { fit = fitEnsemble(train); sinceFit = 0; }
}
const avg = (a: number[][]) => a[0].map((_, i) => (a.reduce((s, r) => s + r[i], 0) / a.length).toFixed(3));
console.log(`\nWALK-FORWARD on season ${TEST_SEASON} (n=${Y.length}); fit only on games before each prediction`);
console.log('model'.padEnd(13), 'logloss'.padStart(8), 'brier'.padStart(8), 'acc'.padStart(7));
for (const [k, p] of Object.entries(P)) console.log(k.padEnd(13), logLoss(p, Y).toFixed(4).padStart(8), brier(p, Y).toFixed(4).padStart(8), (accuracy(p, Y) * 100).toFixed(1).padStart(6) + '%');
console.log(`\nmean meta weights [strength, form, context]  early-season: ${avg(wSample.early)}  | rest: ${avg(wSample.late)}`);
// paired bootstrap on per-game log-loss difference (stacked - elo_only); negative = stacked better
const ll = (p: number, y: number) => -(y * Math.log(p) + (1 - y) * Math.log(1 - p));
const d = Y.map((y, i) => ll(P.stacked[i], y) - ll(P.elo_only[i], y));
let seed = 12345; const rnd = () => (seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296;
const boots: number[] = [];
for (let b = 0; b < 2000; b++) { let s = 0; for (let i = 0; i < d.length; i++) s += d[(rnd() * d.length) | 0]; boots.push(s / d.length); }
boots.sort((a, b) => a - b);
console.log(`stacked - elo_only logloss diff = ${(d.reduce((a, b) => a + b, 0) / d.length).toFixed(4)}  95% CI [${boots[50].toFixed(4)}, ${boots[1949].toFixed(4)}]`);
console.log(`home win rate in test = ${(Y.reduce((a, b) => a + b, 0) / Y.length * 100).toFixed(1)}%`);
