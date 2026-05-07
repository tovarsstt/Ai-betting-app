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
