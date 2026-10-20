// Soccer (UCL) model: Dixon-Coles-style Poisson goal model, three base views, market blend.
//   A) strength : attack/defence from goals for/against per game, shrunk to league mean
//   B) form     : same, from last-5 goals for/against
//   C) context  : home edge, rest days, midweek congestion
// Final 1X2 = blend(model, devigged market). Without historical soccer data in the repo the
// blend weights are FIXED priors (not learned) — see MODEL_WEIGHT. NBA is the only learned stacker.
import { clamp } from './math.ts';

export interface TeamForm {
  name: string;
  gf: number; ga: number; gp: number;          // season (domestic + UCL) goals for/against, games played
  l5gf?: number; l5ga?: number;                // last-5 per-game averages, if known
  restDays?: number;                           // days since last match
  injuredKeyPlayers?: number;                  // count of confirmed key absences (0-3)
}
export interface SoccerInput { home: TeamForm; away: TeamForm; leagueAvgGoals?: number; neutral?: boolean }

const LG_AVG = 1.45;         // goals per team per match, UCL league phase (prior; override via input)
const HOME_ADV = 1.12;       // multiplicative home goal boost
const PRIOR_GAMES = 8;       // pseudo-games of league-average performance (shrinkage)
const RHO = -0.06;           // Dixon-Coles low-score dependence
const MAXG = 9;
export const MODEL_WEIGHT = 0.35; // share of model vs devigged market in the final probability

const shrink = (per: number, gp: number, mean: number): number => (per * gp + mean * PRIOR_GAMES) / (gp + PRIOR_GAMES);

function poissonPmf(k: number, lam: number): number {
  let p = Math.exp(-lam);
  for (let i = 1; i <= k; i++) p *= lam / i;
  return p;
}
function tau(x: number, y: number, lh: number, la: number): number {
  if (x === 0 && y === 0) return 1 - lh * la * RHO;
  if (x === 0 && y === 1) return 1 + lh * RHO;
  if (x === 1 && y === 0) return 1 + la * RHO;
  if (x === 1 && y === 1) return 1 - RHO;
  return 1;
}

export interface ScoreGrid { pH: number; pD: number; pA: number; over25: number; btts: number; top: Array<{ score: string; p: number }>; lh: number; la: number }
export function scoreGrid(lh: number, la: number): ScoreGrid {
  let pH = 0, pD = 0, pA = 0, over = 0, btts = 0, tot = 0;
  const cells: Array<{ score: string; p: number }> = [];
  for (let i = 0; i <= MAXG; i++) for (let j = 0; j <= MAXG; j++) {
    const p = poissonPmf(i, lh) * poissonPmf(j, la) * tau(i, j, lh, la);
    tot += p;
    if (i > j) pH += p; else if (i === j) pD += p; else pA += p;
    if (i + j > 2) over += p;
    if (i > 0 && j > 0) btts += p;
    cells.push({ score: `${i}-${j}`, p });
  }
  cells.sort((a, b) => b.p - a.p);
  return { pH: pH / tot, pD: pD / tot, pA: pA / tot, over25: over / tot, btts: btts / tot, top: cells.slice(0, 3).map(c => ({ score: c.score, p: c.p / tot })), lh, la };
}

function lambdas(i: SoccerInput, useForm: boolean, ctx: boolean): { lh: number; la: number } {
  const lg = i.leagueAvgGoals ?? LG_AVG;
  const att = (t: TeamForm) => shrink(useForm && t.l5gf != null ? t.l5gf : t.gf / Math.max(t.gp, 1), useForm && t.l5gf != null ? 5 : t.gp, lg) / lg;
  const def = (t: TeamForm) => shrink(useForm && t.l5ga != null ? t.l5ga : t.ga / Math.max(t.gp, 1), useForm && t.l5ga != null ? 5 : t.gp, lg) / lg;
  let lh = lg * att(i.home) * def(i.away) * (i.neutral ? 1 : HOME_ADV);
  let la = lg * att(i.away) * def(i.home) / (i.neutral ? 1 : Math.sqrt(HOME_ADV));
  if (ctx) {
    const rest = (t: TeamForm) => clamp(t.restDays ?? 4, 2, 7);
    const fat = (t: TeamForm) => 1 - 0.015 * clamp(4 - rest(t), 0, 2);       // <4 days rest: slight output drop
    const inj = (t: TeamForm) => 1 - 0.04 * clamp(t.injuredKeyPlayers ?? 0, 0, 3);
    lh *= fat(i.home) * inj(i.home);
    la *= fat(i.away) * inj(i.away);
    // opponent missing defenders/keepers raises own scoring a touch
    lh *= 1 + 0.015 * clamp(i.away.injuredKeyPlayers ?? 0, 0, 3);
    la *= 1 + 0.015 * clamp(i.home.injuredKeyPlayers ?? 0, 0, 3);
  }
  return { lh: clamp(lh, 0.2, 4.5), la: clamp(la, 0.2, 4.5) };
}

export interface SoccerOut {
  pHome: number; pDraw: number; pAway: number;   // final (market-blended if market given)
  modelOnly: { pHome: number; pDraw: number; pAway: number };
  base: { strength: ScoreGrid; form: ScoreGrid; context: ScoreGrid };
  grid: ScoreGrid; over25: number; btts: number; lambdas: { home: number; away: number };
}
export function predictSoccer(i: SoccerInput, market?: { pHome: number; pDraw: number; pAway: number }): SoccerOut {
  const a = lambdas(i, false, false), b = lambdas(i, true, false), c = lambdas(i, false, true);
  const gA = scoreGrid(a.lh, a.la), gB = scoreGrid(b.lh, b.la), gC = scoreGrid(c.lh, c.la);
  // Meta combination: average the lambdas with fixed weights (strength-heavy; form is noisy over 5 games).
  const lh = 0.5 * a.lh + 0.2 * b.lh + 0.3 * c.lh, la = 0.5 * a.la + 0.2 * b.la + 0.3 * c.la;
  const g = scoreGrid(lh, la);
  const model = { pHome: g.pH, pDraw: g.pD, pAway: g.pA };
  const fin = market
    ? { pHome: MODEL_WEIGHT * g.pH + (1 - MODEL_WEIGHT) * market.pHome, pDraw: MODEL_WEIGHT * g.pD + (1 - MODEL_WEIGHT) * market.pDraw, pAway: MODEL_WEIGHT * g.pA + (1 - MODEL_WEIGHT) * market.pAway }
    : model;
  return { ...fin, modelOnly: model, base: { strength: gA, form: gB, context: gC }, grid: g, over25: g.over25, btts: g.btts, lambdas: { home: lh, away: la } };
}
