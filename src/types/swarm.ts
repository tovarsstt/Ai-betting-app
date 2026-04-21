export interface SGPBlueprint {
  label: string;
  value: string;
  rationale: string;
  espn_id: string;
}

export interface SwarmAgentData {
  primary_single?: string;
  value_gap?: string;
  sgp_blueprint?: SGPBlueprint[];
  multi_parlay_anchor?: string;
  omni_report?: string;
  confidence_score?: number;
  [key: string]: unknown;
}

export interface SwarmFinalPayload extends SwarmAgentData {
  swarm_report: {
    quant: SwarmAgentData;
    simulation: SwarmAgentData;
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
  metric_value: string;
  season_stat: string;
  ai_score: number;
  status_color: string;
  espn_id: string;
}

export interface AlphaSheetContainer {
  title: string;
  subtitle: string;
  data: AlphaSheetItem[];
  timestamp: string;
}

export interface SocialPick {
  lock_type: string;
  tier: string;
  lock_text: string;
  lock_data: string;
  headshot_url: string | null;
  display_label?: string;
}

export interface IntelligencePick {
  label: string;
  true_probability_percent: number;
  expected_value_usd: number;
  kelly_sizing_usd: number;
  headshot_url: string | null;
  analysis_rationale?: string;
  edge?: number;
}

export interface TeamData {
  id: string;
  name: string;
  sport: string;
  conference?: string;
  division?: string;
  logo_url?: string;
}

export interface TeamPerformance {
  wins: number;
  losses: number;
  draws?: number;
  atsRecord?: string;
  overUnderRecord?: string;
  offensiveRating?: number;
  defensiveRating?: number;
  pace?: number;
  streakType?: string;
  streakCount?: number;
}
