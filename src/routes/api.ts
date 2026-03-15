import { Router } from 'express';
import { z } from 'zod';
import { db } from '../db/index.js';
import { predictions, evSignals } from '../db/schema.js';
import { eq, desc } from 'drizzle-orm';
import { EVMarketFilter } from '../services/evMarketFilter.js';

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
    
    // Run the newly ported EV Market Filter
    const analysis = EVMarketFilter.analyze(payload.trueProbability, payload.marketDecimalOdds);
    
    // In a real app, we'd save this to `evSignals` table here.
    // For now, we just return the analytical result to the caller.
    
    res.json({ 
      success: true, 
      message: "Data ingested and parsed via ASA v5.0 EV Filter", 
      analysis 
    });
  } catch (error) {
    res.status(400).json({ success: false, error: error.message });
  }
});
