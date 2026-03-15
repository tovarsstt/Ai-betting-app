import { Router } from 'express';
import { z } from 'zod';
import { db } from '../db/index.ts';
import { predictions, evSignals } from '../db/schema.ts';
import { eq, desc } from 'drizzle-orm';
import { EVMarketFilter } from '../services/evMarketFilter.ts';

export const apiRouter = Router();

// Zod Schemas for Validation
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

// --- ROUTES ---

/**
 * GET /api/predictions
 * Fetch model predictions from the memory matrix.
 */
apiRouter.get('/predictions', async (req, res) => {
  try {
    const query = PredictionQuerySchema.parse(req.query);
    
    // In a real scenario, we'd build the where clause dynamically based on sport/status.
    // For now, return the most recent predictions.
    const results = await db.query.predictions.findMany({
      orderBy: [desc(predictions.createdAt)],
      limit: query.limit,
    });
    
    res.json({ success: true, data: results });
  } catch (error) {
    res.status(400).json({ success: false, error: error.message });
  }
});

/**
 * GET /api/ev-signals
 * Fetch Sharp/Fade EV signals. 
 */
apiRouter.get('/ev-signals', async (req, res) => {
  try {
    const query = EVSignalQuerySchema.parse(req.query);
    
    const results = await db.query.evSignals.findMany({
      orderBy: [desc(evSignals.createdAt)],
      limit: query.limit,
    });
    
    res.json({ success: true, data: results });
  } catch (error) {
    res.status(400).json({ success: false, error: error.message });
  }
});

/**
 * POST /api/ingest
 * Trigger live game data ingestion and EV calculation.
 */
apiRouter.post('/ingest', async (req, res) => {
  try {
    const payload = IngestPayloadSchema.parse(req.body);
    
    // Extract true/soft odds
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

    // Call the internal /api/analyze route 3 times for Standard, SGP, and Slate Parlay
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
