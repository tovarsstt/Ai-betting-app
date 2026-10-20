// NBA stacked ensemble: 3 independent base models -> logistic meta-model.
//   A) strength  : margin-aware Elo (team quality)
//   B) form      : average margin over each team's last 5 games
//   C) context   : home court, rest-day differential, back-to-backs (small logistic fit)
// Meta-model: ridge logistic regression on [logit(A), logit(B), logit(C)] plus the same
// terms scaled by an "early season" flag, so weights shift by game context (Elo/form are
// noisier in the first ~15 games) instead of being a fixed average.
import { clamp, logit, sigmoid, normCdf, fitLogistic, predictLogistic, type LogisticModel } from './math.ts';

export interface Game { date: string; home: string; away: string; hs: number; as: number; season: number }

const K = 20, HOME_ELO = 70, CARRY = 0.75, MARGIN_SIGMA = 12.0, FORM_N = 5;
const DAY = 86400000;

export interface TeamState { elo: number; recent: number[]; lastDate: number | null; gp: number }
export interface Ctx { homeRest: number; awayRest: number; homeB2B: number; awayB2B: number; early: number; homeForm: number; awayForm: number; eloDiff: number }

export class NbaState {
  teams = new Map<string, TeamState>();
  season = -1;
  asOf = '';
  get(t: string): TeamState {
    let s = this.teams.get(t);
    if (!s) { s = { elo: 1500, recent: [], lastDate: null, gp: 0 }; this.teams.set(t, s); }
    return s;
  }
  newSeason(season: number, gapSeasons = 1): void {
    for (const s of this.teams.values()) {
      s.elo = 1500 + (s.elo - 1500) * Math.pow(CARRY, gapSeasons);
      s.recent = []; s.gp = 0; s.lastDate = null;
    }
    this.season = season;
  }
  // Pre-game features. Must be called BEFORE update() so no future information leaks.
  context(home: string, away: string, date: string): Ctx {
    const h = this.get(home), a = this.get(away), t = Date.parse(date);
    const rest = (s: TeamState) => (s.lastDate === null ? 3 : clamp(Math.round((t - s.lastDate) / DAY) - 1, 0, 4));
    const form = (s: TeamState) => (s.recent.length ? s.recent.reduce((x, y) => x + y, 0) / s.recent.length : 0);
    const hr = rest(h), ar = rest(a);
    return {
      homeRest: hr, awayRest: ar, homeB2B: hr === 0 ? 1 : 0, awayB2B: ar === 0 ? 1 : 0,
      early: Math.min(h.gp, a.gp) < 15 ? 1 : 0,
      homeForm: form(h), awayForm: form(a), eloDiff: h.elo - a.elo,
    };
  }
  update(g: Game): void {
    const h = this.get(g.home), a = this.get(g.away);
    const margin = g.hs - g.as;
    const exp = 1 / (1 + Math.pow(10, -(h.elo + HOME_ELO - a.elo) / 400));
    const win = margin > 0 ? 1 : 0;
    const eloDiffW = Math.abs(h.elo + HOME_ELO - a.elo) * (margin > 0 ? 1 : -1);
    const mov = Math.pow(Math.abs(margin) + 3, 0.8) / (7.5 + 0.006 * eloDiffW);
    const delta = K * mov * (win - exp);
    h.elo += delta; a.elo -= delta;
    h.recent.push(margin); a.recent.push(-margin);
    if (h.recent.length > FORM_N) h.recent.shift();
    if (a.recent.length > FORM_N) a.recent.shift();
    const t = Date.parse(g.date);
    h.lastDate = t; a.lastDate = t; h.gp++; a.gp++;
    this.asOf = g.date;
  }
}

// ---- base models ---------------------------------------------------------
export const baseA = (c: Ctx): number => 1 / (1 + Math.pow(10, -(c.eloDiff + HOME_ELO) / 400));
// Form: home-court worth ~2.8 pts; form margin difference shrunk x0.5 (5-game margins are noisy).
export const baseB = (c: Ctx): number => normCdf((2.8 + 0.5 * (c.homeForm - c.awayForm)) / MARGIN_SIGMA);
export const ctxFeatures = (c: Ctx): number[] => [clamp(c.homeRest - c.awayRest, -3, 3), c.homeB2B, c.awayB2B];

export interface Fitted { C: LogisticModel; meta: LogisticModel }

export const metaFeatures = (c: Ctx, pC: number): number[] => {
  const a = logit(baseA(c)), b = logit(baseB(c)), cc = logit(pC);
  return [a, b, cc, a * c.early, b * c.early, cc * c.early];
};

export interface Row { ctx: Ctx; y: number }

// Fit base model C (context) then the meta-model on the same window.
export function fitEnsemble(rows: Row[], l2 = 5): Fitted {
  const y = rows.map(r => r.y);
  const C = fitLogistic(rows.map(r => ctxFeatures(r.ctx)), y, 2);
  // Ridge toward equal-weight averaging (1/3 each, 0 interaction): with little data the stacker
  // degrades to a plain average instead of overfitting.
  const meta = fitLogistic(rows.map(r => metaFeatures(r.ctx, predictLogistic(C, ctxFeatures(r.ctx)))), y, l2, [1 / 3, 1 / 3, 1 / 3, 0, 0, 0]);
  return { C, meta };
}

export interface EnsembleOut { pHome: number; base: { strength: number; form: number; context: number }; weights: { strength: number; form: number; context: number }; ctx: Ctx }
export function predictEnsemble(f: Fitted, c: Ctx): EnsembleOut {
  const pC = predictLogistic(f.C, ctxFeatures(c));
  const x = metaFeatures(c, pC);
  const pHome = predictLogistic(f.meta, x);
  const e = c.early;
  return {
    pHome, ctx: c,
    base: { strength: baseA(c), form: baseB(c), context: pC },
    weights: { strength: f.meta.w[0] + e * f.meta.w[3], form: f.meta.w[1] + e * f.meta.w[4], context: f.meta.w[2] + e * f.meta.w[5] },
  };
}

export { sigmoid };
