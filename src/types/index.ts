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

export interface SwarmFinalPayload extends SwarmAgentData {
  bet_structure?: string;         // math-computed
  implied_prob?: number;          // math-computed from primary_odds
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
