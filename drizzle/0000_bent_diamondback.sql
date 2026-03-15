CREATE TABLE "engine_telemetry" (
	"id" text PRIMARY KEY NOT NULL,
	"timestamp" timestamp DEFAULT now(),
	"game_id" text,
	"target_team" text,
	"market_spread" double precision,
	"bernoulli_edge" double precision,
	"injury_score" double precision,
	"smi_score" double precision,
	"rlm_active" boolean,
	"regression_delta" double precision,
	"scheme_friction" double precision,
	"system_lock_play" text
);
--> statement-breakpoint
CREATE TABLE "ev_signals" (
	"id" text PRIMARY KEY NOT NULL,
	"prediction_id" text,
	"home_team" text NOT NULL,
	"away_team" text NOT NULL,
	"sport" text NOT NULL,
	"bet_side" text NOT NULL,
	"signal" text NOT NULL,
	"ev_edge_pct" double precision NOT NULL,
	"maker_price" double precision NOT NULL,
	"kelly_fraction" double precision NOT NULL,
	"created_at" timestamp DEFAULT now()
);
--> statement-breakpoint
CREATE TABLE "line_movements" (
	"id" text PRIMARY KEY NOT NULL,
	"bookmaker" text NOT NULL,
	"line_type" text NOT NULL,
	"opening_line" double precision,
	"current_line" double precision,
	"sharp_action" text DEFAULT 'NONE',
	"steam_move" boolean DEFAULT false,
	"reverse_line_movement" boolean DEFAULT false,
	"public_betting_pct" double precision,
	"money_pct" double precision,
	"recorded_at" timestamp DEFAULT now()
);
--> statement-breakpoint
CREATE TABLE "matchups" (
	"id" text PRIMARY KEY NOT NULL,
	"home_team" text NOT NULL,
	"away_team" text NOT NULL,
	"sport" text NOT NULL,
	"matchup_edge" text,
	"home_offense_rating" double precision,
	"away_offense_rating" double precision,
	"home_defense_rating" double precision,
	"away_defense_rating" double precision,
	"home_pace" double precision,
	"away_pace" double precision,
	"home_turnovers_per_game" double precision,
	"away_turnovers_per_game" double precision,
	"home_shot_quality" double precision,
	"away_shot_quality" double precision,
	"home_rebounding_rating" double precision,
	"away_rebounding_rating" double precision,
	"matchup_notes" text,
	"created_at" timestamp DEFAULT now()
);
--> statement-breakpoint
CREATE TABLE "predictions" (
	"id" text PRIMARY KEY NOT NULL,
	"matchup" text NOT NULL,
	"sport" text NOT NULL,
	"status" text DEFAULT 'pending' NOT NULL,
	"away_team" text,
	"home_team" text,
	"predicted_winner" text,
	"ev_edge" double precision,
	"kelly_stake" double precision,
	"tilt_tensor" double precision,
	"circadian_friction_home" double precision,
	"circadian_friction_away" double precision,
	"signal" text,
	"game_date" timestamp,
	"created_at" timestamp DEFAULT now()
);
--> statement-breakpoint
CREATE TABLE "team_performance" (
	"id" text PRIMARY KEY NOT NULL,
	"team_id" text NOT NULL,
	"name" text NOT NULL,
	"sport" text NOT NULL,
	"conference" text,
	"division" text,
	"wins" double precision DEFAULT 0,
	"losses" double precision DEFAULT 0,
	"draws" double precision DEFAULT 0,
	"ats_record" text,
	"over_under_record" text,
	"offensive_rating" double precision,
	"defensive_rating" double precision,
	"pace" double precision,
	"streak_type" text,
	"streak_count" double precision,
	"updated_at" timestamp DEFAULT now()
);
--> statement-breakpoint
CREATE TABLE "trades" (
	"id" text PRIMARY KEY NOT NULL,
	"timestamp" timestamp DEFAULT now(),
	"matchup" text,
	"math_ev" double precision,
	"dissonance_score" double precision,
	"prospect_theory_read" text,
	"selection" text,
	"alpha_edge" text,
	"kelly_sizing" text,
	"actual_outcome" text
);
--> statement-breakpoint
ALTER TABLE "ev_signals" ADD CONSTRAINT "ev_signals_prediction_id_predictions_id_fk" FOREIGN KEY ("prediction_id") REFERENCES "public"."predictions"("id") ON DELETE no action ON UPDATE no action;