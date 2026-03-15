import { pgTable, text, timestamp, boolean, doublePrecision } from "drizzle-orm/pg-core";

export const predictions = pgTable("predictions", {
  id: text("id").primaryKey(),
  matchup: text("matchup").notNull(),
  sport: text("sport").notNull(),
  status: text("status").notNull().default("pending"),
  awayTeam: text("away_team"),
  homeTeam: text("home_team"),
  predictedWinner: text("predicted_winner"),
  evEdge: doublePrecision("ev_edge"),
  kellyStake: doublePrecision("kelly_stake"),
  tiltTensor: doublePrecision("tilt_tensor"),
  circadianFrictionHome: doublePrecision("circadian_friction_home"),
  circadianFrictionAway: doublePrecision("circadian_friction_away"),
  signal: text("signal"),
  gameDate: timestamp("game_date", { mode: "date" }),
  createdAt: timestamp("created_at", { mode: "date" }).defaultNow(),
});

export const evSignals = pgTable("ev_signals", {
  id: text("id").primaryKey(),
  predictionId: text("prediction_id").references(() => predictions.id),
  homeTeam: text("home_team").notNull(),
  awayTeam: text("away_team").notNull(),
  sport: text("sport").notNull(),
  betSide: text("bet_side").notNull(),
  signal: text("signal").notNull(), // SHARP, FADE, NEUTRAL
  evEdgePct: doublePrecision("ev_edge_pct").notNull(),
  makerPrice: doublePrecision("maker_price").notNull(),
  kellyFraction: doublePrecision("kelly_fraction").notNull(),
  createdAt: timestamp("created_at", { mode: "date" }).defaultNow(),
});

export const lineMovements = pgTable("line_movements", {
  id: text("id").primaryKey(),
  bookmaker: text("bookmaker").notNull(),
  lineType: text("line_type").notNull(),
  openingLine: doublePrecision("opening_line"),
  currentLine: doublePrecision("current_line"),
  sharpAction: text("sharp_action").default("NONE"),
  steamMove: boolean("steam_move").default(false),
  reverseLineMovement: boolean("reverse_line_movement").default(false),
  publicBettingPct: doublePrecision("public_betting_pct"),
  moneyPct: doublePrecision("money_pct"),
  recordedAt: timestamp("recorded_at", { mode: "date" }).defaultNow(),
});

// Teams long term performance 
export const teamPerformance = pgTable("team_performance", {
  id: text("id").primaryKey(),
  teamId: text("team_id").notNull(),
  name: text("name").notNull(),
  sport: text("sport").notNull(),
  conference: text("conference"),
  division: text("division"),
  wins: doublePrecision("wins").default(0),
  losses: doublePrecision("losses").default(0),
  draws: doublePrecision("draws").default(0),
  atsRecord: text("ats_record"),
  overUnderRecord: text("over_under_record"),
  offensiveRating: doublePrecision("offensive_rating"),
  defensiveRating: doublePrecision("defensive_rating"),
  pace: doublePrecision("pace"),
  streakType: text("streak_type"), // W or L
  streakCount: doublePrecision("streak_count"),
  updatedAt: timestamp("updated_at", { mode: "date" }).defaultNow(),
});

export const matchups = pgTable("matchups", {
  id: text("id").primaryKey(),
  homeTeam: text("home_team").notNull(),
  awayTeam: text("away_team").notNull(),
  sport: text("sport").notNull(),
  matchupEdge: text("matchup_edge"),
  homeOffenseRating: doublePrecision("home_offense_rating"),
  awayOffenseRating: doublePrecision("away_offense_rating"),
  homeDefenseRating: doublePrecision("home_defense_rating"),
  awayDefenseRating: doublePrecision("away_defense_rating"),
  homePace: doublePrecision("home_pace"),
  awayPace: doublePrecision("away_pace"),
  homeTurnoversPerGame: doublePrecision("home_turnovers_per_game"),
  awayTurnoversPerGame: doublePrecision("away_turnovers_per_game"),
  homeShotQuality: doublePrecision("home_shot_quality"),
  awayShotQuality: doublePrecision("away_shot_quality"),
  homeReboundingRating: doublePrecision("home_rebounding_rating"),
  awayReboundingRating: doublePrecision("away_rebounding_rating"),
  matchupNotes: text("matchup_notes"),
  createdAt: timestamp("created_at", { mode: "date" }).defaultNow(),
});

export const trades = pgTable("trades", {
  id: text("id").primaryKey(), // Using ID text for UUID or let default serial, but keeping text for consistency
  timestamp: timestamp("timestamp", { mode: "date" }).defaultNow(),
  matchup: text("matchup"),
  mathEv: doublePrecision("math_ev"),
  dissonanceScore: doublePrecision("dissonance_score"),
  prospectTheoryRead: text("prospect_theory_read"),
  selection: text("selection"),
  alphaEdge: text("alpha_edge"),
  kellySizing: text("kelly_sizing"),
  actualOutcome: text("actual_outcome"),
});

export const engineTelemetry = pgTable("engine_telemetry", {
  id: text("id").primaryKey(), // Using text for UUIDs
  timestamp: timestamp("timestamp", { mode: "date" }).defaultNow(),
  gameId: text("game_id"),
  targetTeam: text("target_team"),
  marketSpread: doublePrecision("market_spread"),
  bernoulliEdge: doublePrecision("bernoulli_edge"),
  injuryScore: doublePrecision("injury_score"),
  smiScore: doublePrecision("smi_score"),
  rlmActive: boolean("rlm_active"),
  regressionDelta: doublePrecision("regression_delta"),
  schemeFriction: doublePrecision("scheme_friction"),
  systemLockPlay: text("system_lock_play"),
});
