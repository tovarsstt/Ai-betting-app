export const SPORT_KEYS: Record<string, string[]> = {
  NBA:    ["basketball_nba"],
  WNBA:   ["basketball_wnba"],
  NFL:    ["americanfootball_nfl"],
  CFB:    ["americanfootball_ncaaf"], // college football — sharp-anchor engine, no local model
  MLB:    ["baseball_mlb"],
  NHL:    ["icehockey_nhl"],
  UFC:    ["mma_mixed_martial_arts"], // UFC fight nights + PPV
  F1:     [], // No Odds API coverage — circuit context from local data
  // 2026-27 club season live (WC 2026 over) — big-5 domestic + UCL first.
  SOCCER: [
    "soccer_uefa_champs_league",
    "soccer_epl",
    "soccer_italy_serie_a",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
  ],
  UCL: ["soccer_uefa_champs_league"], // own tab: Champions League day card
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
