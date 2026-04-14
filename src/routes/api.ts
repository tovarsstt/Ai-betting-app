import { Router } from 'express';
import { z } from 'zod';
import { db } from '../db/index.js';
import { predictions, evSignals, lineMovements, teamPerformance, matchups, trades } from '../db/schema.js';
import { desc, eq } from 'drizzle-orm';
import { v4 as uuidv4 } from 'uuid';

export const apiRouter = Router();

// --- VALIDATION SCHEMAS ---

export const PredictionQuerySchema = z.object({
  sport: z.string().optional(),
  status: z.string().optional(),
  limit: z.coerce.number().min(1).max(100).default(20),
});

export const EVSignalQuerySchema = z.object({
  sport: z.string().optional(),
  signal: z.enum(['SHARP', 'FADE', 'NEUTRAL', 'ALL']).optional().default('ALL'),
  limit: z.coerce.number().min(1).max(100).default(20),
});

export const IngestPayloadSchema = z.object({
  sport: z.string(),
  matchup: z.string(),
  trueProbability: z.number().min(0).max(1),
  marketDecimalOdds: z.number().min(1)
});

export const PlaySchema = z.object({
  matchup: z.string(),
  selection: z.string(),
  alphaEdge: z.string().optional(),
  kellySizing: z.string().optional(),
  mathEv: z.number().optional(),
  actualOutcome: z.enum(['WIN', 'LOSS', 'PENDING', 'VOID']).default('PENDING'),
  prospectTheoryRead: z.string().optional(),
});

export const UpdatePlaySchema = z.object({
  actualOutcome: z.enum(['WIN', 'LOSS', 'PENDING', 'VOID']),
});

// --- PREDICTIONS ---

apiRouter.get('/predictions', async (req, res) => {
  try {
    const query = PredictionQuerySchema.parse(req.query);
    const results = await db.query.predictions.findMany({
      orderBy: [desc(predictions.createdAt)],
      limit: query.limit,
    });
    res.json({ success: true, data: results });
  } catch (err: any) {
    res.status(400).json({ success: false, error: err.message });
  }
});

// --- EV SIGNALS ---

apiRouter.get('/ev-signals', async (req, res) => {
  try {
    const query = EVSignalQuerySchema.parse(req.query);
    const results = await db.query.evSignals.findMany({
      orderBy: [desc(evSignals.createdAt)],
      limit: query.limit,
    });
    res.json({ success: true, data: results });
  } catch (err: any) {
    res.status(400).json({ success: false, error: err.message });
  }
});

// --- INGEST ---

apiRouter.post('/ingest', async (req, res) => {
  try {
    const payload = IngestPayloadSchema.parse(req.body);

    const p = Math.max(0.01, Math.min(0.99, payload.trueProbability));
    const sharpOdds = 1 / p;
    const softOdds = payload.marketDecimalOdds;

    const baseBody = {
      sport: payload.sport,
      sharpOdds: sharpOdds.toString(),
      softOdds: softOdds.toString(),
      context: ""
    };

    const port = process.env.PORT || 3001;

    const [standardRes, sgpRes, slateRes] = await Promise.all([
      fetch(`http://127.0.0.1:${port}/api/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...baseBody, matchup: payload.matchup })
      }).then(r => r.json()),
      fetch(`http://127.0.0.1:${port}/api/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...baseBody, matchup: `${payload.matchup} [SGP_MODE]` })
      }).then(r => r.json()),
      fetch(`http://127.0.0.1:${port}/api/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...baseBody, matchup: `${payload.matchup} [SLATE_PARLAY_MODE]` })
      }).then(r => r.json())
    ]);

    res.json({
      success: true,
      message: "Omni-Vector generation complete",
      standard: standardRes,
      sgp: sgpRes,
      slate: slateRes
    });
  } catch (error: any) {
    res.status(400).json({ success: false, error: error.message });
  }
});

// --- TEAMS (teamPerformance table) ---

apiRouter.get('/teams', async (req, res) => {
  try {
    const sport = req.query.sport as string | undefined;
    const results = await db.query.teamPerformance.findMany({
      orderBy: [desc(teamPerformance.updatedAt)],
      limit: 200,
    });
    const filtered = sport && sport !== 'ALL'
      ? results.filter(t => t.sport?.toUpperCase() === sport.toUpperCase())
      : results;
    res.json({ success: true, data: filtered });
  } catch (err: any) {
    res.status(400).json({ success: false, error: err.message });
  }
});

apiRouter.get('/teams/:id', async (req, res) => {
  try {
    const result = await db.query.teamPerformance.findFirst({
      where: eq(teamPerformance.id, req.params.id),
    });
    if (!result) return res.status(404).json({ success: false, error: 'Team not found' });
    res.json({ success: true, data: result });
  } catch (err: any) {
    res.status(400).json({ success: false, error: err.message });
  }
});

// --- LINE MOVEMENTS ---

apiRouter.get('/line-movements', async (req, res) => {
  try {
    const limit = Math.min(Number(req.query.limit) || 50, 100);
    const results = await db.query.lineMovements.findMany({
      orderBy: [desc(lineMovements.recordedAt)],
      limit,
    });
    res.json({ success: true, data: results });
  } catch (err: any) {
    res.status(400).json({ success: false, error: err.message });
  }
});

// --- MATCHUPS ---

apiRouter.get('/matchups', async (req, res) => {
  try {
    const limit = Math.min(Number(req.query.limit) || 50, 100);
    const results = await db.query.matchups.findMany({
      orderBy: [desc(matchups.createdAt)],
      limit,
    });
    res.json({ success: true, data: results });
  } catch (err: any) {
    res.status(400).json({ success: false, error: err.message });
  }
});

// --- PLAYS (Stake bet tracker using trades table) ---

apiRouter.get('/plays', async (req, res) => {
  try {
    const limit = Math.min(Number(req.query.limit) || 100, 200);
    const results = await db.query.trades.findMany({
      orderBy: [desc(trades.timestamp)],
      limit,
    });
    res.json({ success: true, data: results });
  } catch (err: any) {
    res.status(400).json({ success: false, error: err.message });
  }
});

apiRouter.post('/plays', async (req, res) => {
  try {
    const payload = PlaySchema.parse(req.body);
    const id = uuidv4();
    await db.insert(trades).values({
      id,
      matchup: payload.matchup,
      selection: payload.selection,
      alphaEdge: payload.alphaEdge || null,
      kellySizing: payload.kellySizing || null,
      mathEv: payload.mathEv || null,
      actualOutcome: payload.actualOutcome,
      prospectTheoryRead: payload.prospectTheoryRead || null,
    });
    res.json({ success: true, data: { id } });
  } catch (err: any) {
    res.status(400).json({ success: false, error: err.message });
  }
});

apiRouter.patch('/plays/:id', async (req, res) => {
  try {
    const payload = UpdatePlaySchema.parse(req.body);
    await db
      .update(trades)
      .set({ actualOutcome: payload.actualOutcome })
      .where(eq(trades.id, req.params.id));
    res.json({ success: true });
  } catch (err: any) {
    res.status(400).json({ success: false, error: err.message });
  }
});

// --- TODAY'S GAMES (proxies BallDontLie) ---

apiRouter.get('/today-games', async (req, res) => {
  try {
    const sport = ((req.query.sport as string) || 'NBA').toUpperCase();
    const apiKey = process.env.BALLDONTLIE_API_KEY;
    if (!apiKey) {
      return res.json({ success: true, data: [], message: 'BALLDONTLIE_API_KEY not set' });
    }

    const today = new Date().toISOString().split('T')[0];
    let url = `https://api.balldontlie.io/v1/games?dates[]=${today}&per_page=100`;
    if (sport === 'NFL') url = `https://api.balldontlie.io/nfl/v1/games?dates[]=${today}&per_page=100`;
    if (sport === 'MLB') url = `https://api.balldontlie.io/mlb/v1/games?dates[]=${today}&per_page=100`;

    const resp = await fetch(url, {
      headers: { Authorization: apiKey },
      signal: AbortSignal.timeout(6000),
    });
    if (!resp.ok) return res.json({ success: true, data: [] });
    const json = await resp.json();

    const games = (json.data || []).map((g: any) => ({
      id: g.id,
      sport,
      date: g.date,
      status: g.status,
      homeTeam: g.home_team?.full_name || g.home_team?.name,
      awayTeam: g.visitor_team?.full_name || g.visitor_team?.name,
      homeScore: g.home_team_score,
      awayScore: g.visitor_team_score,
    }));

    res.json({ success: true, data: games });
  } catch (err: any) {
    res.status(400).json({ success: false, error: err.message });
  }
});
