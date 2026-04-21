CREATE TABLE IF NOT EXISTS predictions (
    id TEXT PRIMARY KEY,
    matchup TEXT NOT NULL,
    sport TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    predicted_winner TEXT,
    actual_outcome TEXT,
    ev_edge FLOAT,
    kelly_stake FLOAT,
    alpha_edge TEXT,
    game_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS engine_telemetry (
    id TEXT PRIMARY KEY,
    target_team TEXT,
    injury_score FLOAT,
    smi_score FLOAT,
    bernoulli_edge FLOAT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
