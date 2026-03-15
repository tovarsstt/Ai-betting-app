import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import { GoogleGenerativeAI } from "@google/generative-ai";
import { db } from '../../src/db/index.js';
import { predictions, results, betLedger } from '../../src/db/schema.js';
import { desc, eq } from 'drizzle-orm';
import { v4 as uuidv4 } from 'uuid';

dotenv.config();

const app = express();
app.use(cors());
app.use(express.json());

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);

/**
 * V12 REBIRTH BRIDGE
 * Orchestrates between User Input -> Gemini Analysis -> Quant Engine -> Memory Matrix
 */

/**
 * Narrative-to-Tensor (The Neuro-Link)
 * Extracts psychological state from team news.
 */
async function getGeminiPsychScore(teamName, newsText) {
    try {
        const model = genAI.getGenerativeModel({ model: "gemini-1.5-pro" });
        const prompt = `Analyze the following news/interviews for the team "${teamName}". 
        Quantify the "Coach Confidence" and "Player Friction" on a combined scale of -1 to 1.
        -1 is extreme friction/low confidence.
        1 is perfect harmony/high confidence.
        Return ONLY a JSON object with the score.
        Example: {"psych_score": 0.45}
        
        TEXT: ${newsText}`;

        const result = await model.generateContent(prompt);
        const response = await result.response;
        const text = response.text();
        const jsonMatch = text.match(/\{.*\}/);
        if (jsonMatch) {
            const data = JSON.parse(jsonMatch[0]);
            return data.psych_score || 0;
        }
    } catch (e) {
        console.error("Neuro-Link Error:", e);
    }
    return 0;
}

app.post('/api/v12/analyze', async (req, res) => {
    try {
        const { matchup, sport, newsContext } = req.body;
        
        // 1. Contextual Intelligence (Gemini Neuro-Link)
        console.log("🧠 Activating Neuro-Link for:", matchup);
        const psychScore = newsContext ? await getGeminiPsychScore(matchup, newsContext) : 0;
        
        // 2. feature Extraction (Mocked for now, will pull from ELO/CF/Tilt engines)
        const features = {
            cf: 1.25,
            elo_diff: 50,
            tilt: 0.2,
            fatigue: 0.3,
            ref_bias: 0.02
        };

        // 3. Quant Engine Request (Python)
        // Note: Using dynamic port or hardcoded 8001 for now
        const pythonRes = await fetch('http://localhost:8001/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                matchup,
                sport,
                features,
                narrative_psych_score: psychScore
            })
        });
        
        const quantData = await pythonRes.json();
        
        // 4. Memory Matrix Logging
        await db.insert(predictions).values({
            id: `v12_pred_${Date.now()}`,
            matchup: matchup,
            sport: sport,
            status: 'active'
        });
        
        res.json({
            status: "OMNISCIENCE_ALPHA_ACTIVE",
            composite_probability: quantData.composite_probability,
            neuro_link_score: psychScore,
            mc_details: quantData.mc_details,
            matchup: matchup,
            primary_lock: quantData.primary_lock
        });
    } catch (error) {
        console.error("Bridge Error:", error);
        res.status(500).json({ error: error.message });
    }
});

/**
 * V12 Accountability Ledger API (For TikTok Dashboard)
 */
app.get('/api/v12/ledger', async (req, res) => {
    try {
        const history = await db
            .select({
                prediction: predictions,
                pnlUsd: results.pnlUsd
            })
            .from(predictions)
            .leftJoin(results, eq(predictions.id, results.predictionId))
            .orderBy(desc(predictions.createdAt))
            .limit(50);
            
        // Flatten for frontend
        const flatHistory = history.map(row => ({
            ...row.prediction,
            pnl_usd: row.pnlUsd 
        }));
        res.json(flatHistory);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/v12/log-bet', async (req, res) => {
    const { prediction_id, amount, odds } = req.body;
    try {
        await db.insert(betLedger).values({
            id: uuidv4(),
            predictionId: prediction_id,
            amountUsd: amount,
            placedOdds: odds
        });
        res.json({ success: true, message: "Bet logged for accountability." });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

const PORT = process.env.V12_PORT || 3005;
app.listen(PORT, () => {
    console.log(`📡 V12 Omniscience Bridge listening on port ${PORT}`);
});
