// ── Shared types ──────────────────────────────────────────────────────────────

export interface SGPLeg {
  label: string;
  value: string;
  rationale: string;
  espn_id: string;
}

// Short-form content generated alongside the pick (TikTok/Reels/Shorts)
export interface TikTokContent {
  hook: string;
  script: string;
  on_screen_text: string[];
  caption: string;
  hashtags: string[];
}

export interface SwarmAgentData {
  primary_single: string;
  primary_odds?: string;          // AI outputs odds from live odds block
  bet_structure?: string;         // math-computed server-side
  sgp_blueprint: SGPLeg[];
  multi_parlay_anchor: string;
  omni_report: string;
  value_check?: string;           // AI states pick prob vs devigged implied price
  tiktok?: TikTokContent;         // short-form content for the verdict pick
  // REMOVED: value_gap (AI-invented EV), confidence_score (AI self-score)
  // Math-computed replacements injected server-side:
  implied_prob?: number;          // devigged market prob from primary_odds
}

// Structured Poisson/Dixon-Coles board for the chart (soccer only) — the same
// numbers the LLM prompt cites, passed through as DATA so the UI can render them.

// One Monte Carlo market estimate: Bernoulli hit rate + binomial Wilson 95% CI.
export interface SimHitRate {
  prob: number;
  ci_95: [number, number];
}

// Data-fit team strength: Keener eigenvector rating + Poisson-regression
// attack/defense coefficients (log scale).
export interface TeamFitRating {
  eigen_rating?: number;
  attack?: number;
  defense?: number;
  n_matches?: number;
}

export interface PoissonBoard {
  favorite?: string;
  win_draw_lose?: { win: number; draw: number; lose: number };
  correct_score: { score: string; prob: number }[];
  expected_total_goals?: number;
  totals?: Record<string, { over: number; under: number }>;
  btts?: { yes: number; no: number };
  lambda_source?: string;
  n_sims?: number;                // Monte Carlo sample count; absent = closed-form
  // Monte Carlo cross-check with Wilson CIs (binomial uncertainty on the sim).
  sim_1x2?: { home?: SimHitRate; draw?: SimHitRate; away?: SimHitRate };
  sim_over_2_5?: SimHitRate;
  sim_btts_yes?: SimHitRate;
  // Correlated same-game combos — JOINTLY simulated, not multiplied marginals.
  correlated?: Record<string, SimHitRate>;
  // Eigenvector + regression strength behind the lambdas (when a fit exists).
  ratings?: { home?: TeamFitRating | null; away?: TeamFitRating | null;
              home_team?: string; away_team?: string; league?: string };
}

// Math-computed pick grade (mirrors edge_api.pick_quality thresholds:
// LOCK >=70% win-prob, PICK >=62%, LEAN below — a LEAN never anchors a parlay).
export interface PickGrade {
  grade: 'LOCK' | 'PICK' | 'LEAN';
  win_prob: number;               // the model's own probability for the pick
  market: string;
  side: string;
}

// External CITED context (Linemate ATS/injuries + Betting Insider Pinnacle
// movement), surfaced as DATA so the page can show it rather than relying on the
// narrative to repeat it. Every field is optional: the layer degrades to a note
// when a team can't be matched or an upstream is dark.
export interface ContextTeamStats {
  team: string;
  matched: string | null;
  league: string | null;
  ats: {
    games?: number;
    ats_hit_rate?: number | null;
    home_ats_hit_rate?: number | null;
    away_ats_hit_rate?: number | null;
    total_over_hit_rate?: number | null;
  } | null;
  // null = the league has NO injury feed (absence is not a clean bill of health)
  injuries: Array<{ name?: string; position?: string; injury?: string; status?: string }> | null;
  injuries_covered?: boolean;
  note?: string | null;
}

export interface SharpMove {
  player?: string;
  market?: string;
  line?: number;
  pinnacle_over_move_pct?: number | null;   // negative = money came in
}

export interface MarketContextPayload {
  home?: ContextTeamStats;
  away?: ContextTeamStats;
  sharp_moves?: { count?: number; moves?: SharpMove[] | null; note?: string | null } | null;
}

// Every market the model priced, ranked by how often THE PICK lands.
export interface LadderRow {
  market: string;
  win_prob: number;
  verdict: "STRONG" | "PLAYABLE" | "THIN" | "LOTTERY";
  min_odds?: number | null;
  note?: string;
}

export interface ModelSkill {
  league?: string; accuracy?: number; baseline?: number;
  n_games?: number; skill_demonstrated?: boolean; warning?: string | null;
}

// Counted club form (rule 13) — real results, never model output.
export interface ClubProfilePayload {
  home?: Record<string, unknown>;
  away?: Record<string, unknown>;
  h2h?: Record<string, unknown>;
  note?: string;
}

export interface SwarmFinalPayload extends SwarmAgentData {
  bet_structure?: string;         // math-computed
  implied_prob?: number;          // math-computed from primary_odds
  pick_grade?: PickGrade;         // soccer: math grade on the model's primary pick
  poisson?: PoissonBoard;         // soccer: real model distribution for the chart
  market_context?: MarketContextPayload;  // cited external stats (never model output)
  simulated_ladder?: LadderRow[];         // win prob of every market priced
  most_likely_pick?: LadderRow;           // highest-win-prob market
  model_skill?: ModelSkill | null;        // measured league skill (rule 19)
  club_profile?: ClubProfilePayload | null;
  swarm_report: {
    quant?: SwarmAgentData;
    simulation?: SwarmAgentData;
    audit_verdict: string;
  };
  hash: string;
  timestamp: string;
}

export interface AlphaSheetItem {
  rank: number;
  team_logo: string;
  player_name: string;
  metric_label: string;
  metric_value: string;           // "Over 27.5 -115"
  rationale: string;              // sourced from data blocks, not invented
  implied_prob: number;           // math-computed from odds in metric_value
  ai_score: number;               // math-computed signal score (not AI opinion)
  status_color: string;           // derived from implied_prob
  espn_id: string;
  // REMOVED: season_stat (AI invented player stats)
}

export interface AlphaSheetContainer {
  title: string;
  subtitle: string;
  data: AlphaSheetItem[];
  timestamp: string;
}

export interface ParlayLeg {
  pick: string;
  odds: string;
  why: string;
  game?: string;
}

export interface ParlayBlock {
  legs: ParlayLeg[];
  combined_odds: string;
  why: string;
  // REMOVED: ev (AI-invented EV percentage)
  game?: string;
}

export interface ParlaysPayload {
  sport: string;
  best_pick: {
    selection: string;
    odds: string;
    why: string;
    // REMOVED: ev (AI-invented)
    units: string;
    game: string;
  };
  sgp: ParlayBlock;
  multi_parlay: ParlayBlock;
  ev_parlay: ParlayBlock;
  correlation_parlay: ParlayBlock;
}
