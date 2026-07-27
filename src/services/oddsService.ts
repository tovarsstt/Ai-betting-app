export const SPORT_KEYS: Record<string, string[]> = {
  NBA:    ["basketball_nba"],
  WNBA:   ["basketball_wnba"],
  NFL:    ["americanfootball_nfl"],
  MLB:    ["baseball_mlb"],
  NHL:    ["icehockey_nhl"],
  UFC:    ["mma_mixed_martial_arts"], // UFC fight nights + PPV
  F1:     [], // No Odds API coverage — circuit context from local data
  // World Cup 2026 live — prioritized first
  // World Cup 2026 (June) is primary. EPL/MLS/La Liga offseason — swapped for
  // CONMEBOL cups (active, LatAm audience). uefa_euro/copa_america = 404 on Odds API.
  SOCCER: [
    "soccer_fifa_world_cup",
    "soccer_conmebol_copa_libertadores",
    "soccer_conmebol_copa_sudamericana",
  ],
  // Grass season → Wimbledon → US Open pipeline (inactive keys just return empty)
  TENNIS: [
    "tennis_wta_queens_club_champ",
    "tennis_atp_queens_club_champ",
    "tennis_atp_wimbledon",
    "tennis_wta_wimbledon",
    "tennis_atp_us_open",
    "tennis_wta_us_open",
  ],
};

// Shared type used by arbitrageService
export interface OddsEvent {
  id: string;
  sport_key: string;
  home_team: string;
  away_team: string;
  commence_time: string;
  bookmakers: Array<{
    key: string;
    title: string;
    markets: Array<{
      key: string;
      outcomes: Array<{ name: string; price: number; point?: number }>;
    }>;
  }>;
}
