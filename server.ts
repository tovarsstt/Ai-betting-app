import express from 'express';
// @ts-expect-error - no types
import cors from 'cors';
import dotenv from 'dotenv';
import { GoogleGenerativeAI, GenerativeModel } from '@google/generative-ai';
import path from 'path';

dotenv.config();

const app = express();
const port = Number(process.env.PORT) || 3001;

app.use(cors());
app.use(express.json({ limit: '1mb' }));

// ── Simple in-memory rate limit ───────────────────────────────────────────────
const rateCounts = new Map<string, { count: number; reset: number }>();
function rateLimit(ip: string, max: number, windowMs: number): boolean {
  const now = Date.now();
  const entry = rateCounts.get(ip);
  if (!entry || now > entry.reset) {
    rateCounts.set(ip, { count: 1, reset: now + windowMs });
    return false; // not limited
  }
  entry.count++;
  return entry.count > max;
}

// ── Types ─────────────────────────────────────────────────────────────────────
export interface SGPLeg {
  label: string;
  value: string;
  rationale: string;
  espn_id: string;
}

export interface SwarmAgentData {
  primary_single: string;
  value_gap: string;
  sgp_blueprint: SGPLeg[];
  multi_parlay_anchor: string;
  omni_report: string;
  confidence_score: number;
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

// ── Parser ────────────────────────────────────────────────────────────────────
const parseJSON = (raw: string): unknown => {
  const clean = raw.replace(/```json|```/g, "").trim();
  try { return JSON.parse(clean); } catch { /* fall through */ }
  const match = clean.match(/\{[\s\S]*\}|\[[\s\S]*\]/);
  if (match) { try { return JSON.parse(match[0]); } catch { /* fall through */ } }
  throw new Error("JSON_PARSE_FAILED");
};

// ── Gemini helper ─────────────────────────────────────────────────────────────
const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY || "");

async function ask(prompt: string, model = "gemini-2.5-flash"): Promise<string> {
  const m: GenerativeModel = genAI.getGenerativeModel({ model });
  const result = await m.generateContent(prompt);
  return result.response.text().replace(/```json|```/g, "").trim();
}

// ── Date helper ───────────────────────────────────────────────────────────────
function todayStr() {
  return new Date().toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
    timeZone: 'America/New_York'
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// PROPHET — single best pick of the day
// ─────────────────────────────────────────────────────────────────────────────
app.get('/api/prophet', async (req: express.Request, res: express.Response) => {
  const ip = req.ip || 'unknown';
  if (rateLimit(ip, 10, 60_000)) return res.status(429).json({ error: "RATE_LIMIT" });

  try {
    const today = todayStr();
    const prompt = `
You are a sharp professional sports bettor with 15 years of experience beating closing lines.
Today is ${today} (Eastern Time).

Your job: identify TODAY's single highest-conviction bet from real games scheduled tonight or this evening.

Reasoning process (think step by step, don't include these steps in output):
1. Identify 2-3 real games scheduled tonight (NBA playoffs, MLB, tennis, soccer, UFC — whatever is actually on)
2. For each, identify the sharpest betting angle: player prop with proven line inefficiency, team spread backed by recent ATS trend, or total with pace/weather/bullpen edge
3. Score each angle by: closing line value potential, sample size of supporting trend, public fade opportunity
4. Output the top one as JSON

Output ONLY a raw JSON object — no markdown, no commentary:
{
  "selection": "e.g. Anthony Edwards Over 28.5 Points or Celtics -4.5",
  "odds": "American odds string e.g. -115 or +130",
  "game_name": "Team A vs Team B — League — Tonight TIME ET",
  "value_gap": "+X.X% EV",
  "recommended_unit": "1 UNIT or 2 UNITS",
  "logic_bullets": [
    "Specific stat or trend #1 with numbers",
    "Specific matchup or situational edge #2 with numbers",
    "Sharp money / line movement or injury context #3"
  ],
  "correlated_insight": "If bet wins, correlated SGP leg or same-game parlay suggestion"
}

Be specific. Use real player names, real team names, real stats. No filler phrases.
`.trim();

    const raw = await ask(prompt);
    const parsed = parseJSON(raw) as Record<string, unknown>;
    res.json({ ...parsed, hash: "Σ_" + Math.random().toString(36).substring(7).toUpperCase() });

  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("PROPHET_FAILURE:", msg);
    res.status(500).json({ error: "PROPHET_FAILURE", message: msg });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// ANALYZE-UNIFIED — full swarm analysis for a specific matchup
// ─────────────────────────────────────────────────────────────────────────────
app.post('/api/analyze-unified', async (req: express.Request, res: express.Response) => {
  const ip = req.ip || 'unknown';
  if (rateLimit(ip, 5, 60_000)) return res.status(429).json({ error: "RATE_LIMIT" });

  try {
    const { matchup, sport } = req.body;
    if (!matchup) return res.status(400).json({ error: "MATCHUP_REQUIRED" });

    const today = todayStr();
    const league = (sport || 'NBA').toUpperCase();

    // AGENT 1 — Quant model
    const quantPrompt = `
You are a quantitative sports betting analyst. Today is ${today}.
Analyze: ${matchup} (${league})

Focus exclusively on:
- Line value: Where is the market mispriced vs true probability?
- Recent form: Last 5-10 games ATS, totals, pace, efficiency splits
- Situational: Back-to-back, travel fatigue, revenge spot, trap game, playoff seeding irrelevance
- Injury impact: Any key player out or limited? How does that move the line?

Output ONLY this raw JSON:
{
  "primary_single": "Best single bet e.g. 'Lakers +3.5' or 'Curry Over 29.5 Points -110'",
  "value_gap": "e.g. '+6.2% EV' or '+8.1% EDGE'",
  "confidence_score": 0.78,
  "sgp_blueprint": [
    { "label": "Leg 1 Label", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "3975" },
    { "label": "Leg 2 Label", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "3202" },
    { "label": "Leg 3 Label", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "6450" }
  ],
  "multi_parlay_anchor": "Best parlay anchor team/player for multi-game slate",
  "omni_report": "2-3 sentence quant summary of the edge. Cite specific numbers."
}
`.trim();

    // AGENT 2 — Situational/narrative model
    const simPrompt = `
You are a sharp sports analyst specializing in game-flow and situational betting. Today is ${today}.
Analyze: ${matchup} (${league})

Focus exclusively on:
- Narrative edge: Motivation, emotional spots, divisional rivalry
- Coaching tendencies: Pace, lineup rotations, timeout usage, foul trouble management
- Game-flow prediction: Likely game script (blowout vs close game, high vs low scoring)
- Public fade: Is the public hammering one side? Where is sharp action?

Output ONLY this raw JSON:
{
  "primary_single": "Best single bet from situational angle e.g. 'Game Total Under 221.5 -110'",
  "value_gap": "e.g. '+5.3% EV' or '+9.0% EDGE'",
  "confidence_score": 0.72,
  "sgp_blueprint": [
    { "label": "Leg 1 Label", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "3975" },
    { "label": "Leg 2 Label", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "3202" },
    { "label": "Leg 3 Label", "value": "Pick + odds", "rationale": "1 sentence why", "espn_id": "6450" }
  ],
  "multi_parlay_anchor": "Best parlay anchor from game-flow perspective",
  "omni_report": "2-3 sentence situational summary. Mention specific coaching or narrative factors."
}
`.trim();

    const [quantRaw, simRaw] = await Promise.all([ask(quantPrompt), ask(simPrompt)]);
    const quant = parseJSON(quantRaw) as SwarmAgentData;
    const simulation = parseJSON(simRaw) as SwarmAgentData;

    // AGENT 3 — Executive synthesis
    const execPrompt = `
You are the final arbiter — a senior portfolio manager at a sports betting hedge fund.
Today is ${today}. Matchup: ${matchup} (${league}).

You've received two independent analyses:

QUANT AGENT:
- Pick: ${quant.primary_single}
- Edge: ${quant.value_gap}
- Confidence: ${quant.confidence_score}
- Report: ${quant.omni_report}

SITUATIONAL AGENT:
- Pick: ${simulation.primary_single}
- Edge: ${simulation.value_gap}
- Confidence: ${simulation.confidence_score}
- Report: ${simulation.omni_report}

Your job:
1. If both agents agree on direction → confirm with high confidence
2. If they disagree → identify which has the stronger edge and explain why
3. Produce the final executable bet

Output ONLY this raw JSON:
{
  "primary_single": "Final best bet (be specific with line and odds)",
  "value_gap": "Final EV estimate",
  "confidence_score": 0.80,
  "sgp_blueprint": [
    { "label": "SGP Leg 1", "value": "Pick + odds", "rationale": "Why this leg", "espn_id": "3975" },
    { "label": "SGP Leg 2", "value": "Pick + odds", "rationale": "Why this leg", "espn_id": "6450" },
    { "label": "SGP Leg 3", "value": "Pick + odds", "rationale": "Why this leg", "espn_id": "3202" }
  ],
  "multi_parlay_anchor": "Best anchor for a slate parlay",
  "omni_report": "Final 2-3 sentence verdict. State your conviction level and the single biggest risk to this pick."
}
`.trim();

    const execRaw = await ask(execPrompt);
    const exec = parseJSON(execRaw) as SwarmAgentData;

    const payload: SwarmFinalPayload = {
      ...exec,
      swarm_report: {
        quant,
        simulation,
        audit_verdict: exec.omni_report || "CONVERGENCE_LOCKED"
      },
      hash: "Σ_" + Math.random().toString(36).substring(7).toUpperCase(),
      timestamp: new Date().toLocaleTimeString()
    };

    res.json(payload);

  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("ANALYZE_FAILURE:", msg);
    res.status(500).json({ error: "ANALYZE_FAILURE", message: msg });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// ALPHA SHEETS — today's top props cheat sheet
// ─────────────────────────────────────────────────────────────────────────────
export async function generateAlphaSheet(sport: string): Promise<AlphaSheetContainer> {
  const today = todayStr();
  const s = sport.toUpperCase();

  const prompt = `
You are a sharp sports betting analyst building a prop betting cheat sheet.
Today is ${today}.

Generate a cheat sheet of the 10 highest-value player prop bets for ${s} games scheduled TODAY.

For each player:
- Pick a real player with a game tonight
- Identify the most mispriced prop line (points, rebounds, assists, strikeouts, hits, etc.)
- ai_score = your confidence this is +EV (0-10 scale, be realistic — 6-8 range is good, 9+ is rare)
- status_color: #22c55e (strong edge), #eab308 (moderate edge), #f97316 (speculative)
- espn_id: use a realistic ESPN player ID number (e.g. NBA players: LeBron=1966, Curry=3975, Jokic=3112335, Giannis=3032977, SGA=4277905)

Output ONLY a raw JSON array of exactly 10 objects:
[
  {
    "rank": 1,
    "team_logo": "NBA team abbreviation e.g. GSW",
    "player_name": "Full Player Name",
    "metric_label": "e.g. POINTS PROP or STRIKEOUTS",
    "metric_value": "e.g. Over 27.5 -115",
    "season_stat": "e.g. 29.4 PPG L10 or .312 BA",
    "ai_score": 7.8,
    "status_color": "#22c55e",
    "espn_id": "3975"
  }
]

Be specific. Real players, real prop lines, real reasoning baked into metric_value.
`.trim();

  const raw = await ask(prompt);
  const data = parseJSON(raw) as AlphaSheetItem[];

  const titles: Record<string, string> = {
    NBA: "NBA PROP HEATBOARD", MLB: "DINGER & STRIKEOUT SHEET",
    NFL: "NFL PROP SHEET", NHL: "PUCK LINE PROPS",
    TENNIS: "TENNIS EDGE SHEET", SOCCER: "SOCCER PROP SHEET",
  };

  return {
    title: titles[s] || `${s} PROP SHEET`,
    subtitle: `@winwithtovy AI Edge — ${today}`,
    data,
    timestamp: new Date().toLocaleDateString()
  };
}

app.post('/api/alpha-sheets', async (req: express.Request, res: express.Response) => {
  const ip = req.ip || 'unknown';
  if (rateLimit(ip, 5, 60_000)) return res.status(429).json({ error: "RATE_LIMIT" });

  try {
    const { sport } = req.body;
    const data = await generateAlphaSheet(sport || 'NBA');
    res.json(data);
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("ALPHA_SHEET_FAILURE:", msg);
    res.status(500).json({ error: msg });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// IMAGE PROXY — ESPN headshots for html2canvas (ESPN domains only)
// ─────────────────────────────────────────────────────────────────────────────
const ALLOWED_HOSTS = ['a.espncdn.com', 'cdn.nba.com', 'img.mlbstatic.com'];

app.get('/api/proxy-image', async (req: express.Request, res: express.Response) => {
  try {
    const raw = req.query.url as string;
    if (!raw) return res.status(400).send('url required');

    let parsed: URL;
    try { parsed = new URL(decodeURIComponent(raw)); }
    catch { return res.status(400).send('invalid url'); }

    if (!ALLOWED_HOSTS.includes(parsed.hostname)) {
      return res.status(403).send('host not allowed');
    }

    const response = await fetch(parsed.toString(), { signal: AbortSignal.timeout(5000) });
    if (!response.ok) throw new Error(`upstream ${response.status}`);

    const buf = Buffer.from(await response.arrayBuffer());
    res.set('Access-Control-Allow-Origin', '*');
    res.set('Content-Type', response.headers.get('content-type') || 'image/png');
    res.set('Cache-Control', 'public, max-age=86400');
    res.send(buf);
  } catch (e) {
    res.status(500).send('proxy error');
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// SERVE BUILT FRONTEND in production
// ─────────────────────────────────────────────────────────────────────────────
const distPath = path.resolve(process.cwd(), 'dist');
app.use(express.static(distPath));
app.get('/{*splat}', (_req, res) => {
  res.sendFile(path.join(distPath, 'index.html'));
});

app.listen(port, '0.0.0.0', () => {
  console.log(`🚀 WinWithTovy Engine live → http://localhost:${port}`);
});
