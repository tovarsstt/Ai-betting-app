import express from 'express';
// @ts-expect-error - Supressing missing types/cors without breaking module map
import cors from 'cors';
import dotenv from 'dotenv';
import { GoogleGenerativeAI, GenerativeModel } from '@google/generative-ai';
import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs/promises';
import path from 'path';

const execAsync = promisify(exec);

dotenv.config();

const app = express();
const port = Number(process.env.PORT) || 3001;

app.use(cors());
app.use(express.json());

// --- STRICT TYPE INTERFACES ---
interface SGPBlueprint {
  label: string;
  value: string;
  rationale: string;
  espn_id: string;
}

interface SwarmAgentData {
  primary_single: string;
  value_gap: string;
  sgp_blueprint: SGPBlueprint[];
  multi_parlay_anchor?: string;
  omni_report: string;
  confidence_score: number;
}

interface SwarmFinalPayload extends SwarmAgentData {
  swarm_report: {
    quant: SwarmAgentData;
    simulation: SwarmAgentData;
    audit_verdict: string;
  };
  hash: string;
  timestamp: string;
}

interface AlphaSheetItem {
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

interface AlphaSheetContainer {
  title: string;
  subtitle: string;
  data: AlphaSheetItem[];
  timestamp: string;
}

interface QuantumToolResult {
  tool: string;
  output: string;
  success: boolean;
  timestamp: string;
}

interface QuantumSession {
  goal: string;
  logs: QuantumToolResult[];
  final_verdict: string;
  hash: string;
}

// --- UTILITIES ---
const SafeSwarmParser = (input: string): unknown => {
  try {
    // Attempt direct parse after cleaning potential markdown noise
    const clean = input.replace(/```json|```/g, "").trim();
    return JSON.parse(clean);
  } catch {
    // Attempt to extract JSON from markdown blocks or messy text
    const jsonMatch = input.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      try {
        return JSON.parse(jsonMatch[0]);
      } catch {
        throw new Error("SWARM_PARSER_FATAL: Corrupted Payload");
      }
    }
    throw new Error("SWARM_PARSER_FATAL: No payload detected");
  }
};

// --- QUANTUM TOOLBOX (V16.0) ---
class AgentToolbox {
  async executeCommand(command: string): Promise<string> {
    // Restrict sensitive commands to maintain Institutional Security
    const forbidden = ['rm -rf /', 'sudo', 'chmod', 'chown'];
    if (forbidden.some(f => command.includes(f))) {
      return "SECURITY_VIOLATION: Command restricted.";
    }
    try {
      const { stdout, stderr } = await execAsync(command, { timeout: 30000 });
      return stdout || stderr || "SUCCESS: No output.";
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      return `EXECUTION_ERROR: ${message}`;
    }
  }

  async readFile(filePath: string): Promise<string> {
    try {
      const absolutePath = path.resolve(process.cwd(), filePath);
      const content = await fs.readFile(absolutePath, 'utf-8');
      return content;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      return `READ_ERROR: ${message}`;
    }
  }

  async writeFile(filePath: string, content: string): Promise<string> {
    try {
      const absolutePath = path.resolve(process.cwd(), filePath);
      await fs.mkdir(path.dirname(absolutePath), { recursive: true });
      await fs.writeFile(absolutePath, content);
      return "WRITE_SUCCESS: File updated.";
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      return `WRITE_ERROR: ${message}`;
    }
  }
}

// AGENT SWARM // KARPATHY-SKILLS EDITION (V14.0)
class AgentSwarm {
  private genAI: GoogleGenerativeAI;
  private model: GenerativeModel;

  constructor() {
    this.genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY || "");
    this.model = this.genAI.getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  private async runAgent(role: string, prompt: string, context: string = ""): Promise<string> {
    const fullPrompt = `ROLE: ${role}\nSKILLS: Andrej Karpathy Expert Personas // First Principles // Zero Filler.\n\nCONTEXT:\n${context}\n\nTASK:\n${prompt}\n\nGIVE OUTPUT IN RAW JSON FORMAT.`;
    const result = await this.model.generateContent(fullPrompt);
    return result.response.text().replace(/```json|```/g, "");
  }

  async analyzeUnified(matchup: string, sport: string) {
    // PHASE 1: PARALLEL EXECUTION (QUANT & RESEARCHER)
    // Behavioral: Parallelizing for speed while maintaining strict isolation.
    const [quantResult, simulationResult] = await Promise.all([
      this.runAgent(
        "GOD-ENGINE // KARPATHY_QUANT",
        `As a world-class Quantitative Researcher, analyze ${matchup} in ${sport}. 
         OMQX_PROTOCOL: 
         1. OBSERVATION: Map global liquidity vs Stake.com pricing. 
         2. HYPOTHESIS: Identify sigma-deviations in player props. 
         3. VERIFICATION: Verify technical edge against historical variance.`,
        `SYSTEM_STATE: First-Principles-Active.`
      ),
      this.runAgent(
        "GOD-ENGINE // KARPATHY_RESEARCHER",
        `As a Senior Predictive Analyst, simulate the social and game-flow outcome for ${matchup}. 
         OMQX_PROTOCOL: 
         1. OBSERVATION: Filter retail noise and injury trends. 
         2. HYPOTHESIS: Determine narrative confluence (e.g. Motivation, Fatigue). 
         3. VERIFICATION: Compare against likely coach-rotations.`,
        `SYSTEM_STATE: Scenario-Scout-Active.`
      )
    ]);

    const parsedQuant = SafeSwarmParser(quantResult) as SwarmAgentData;
    const parsedSim = SafeSwarmParser(simulationResult) as SwarmAgentData;

    // PHASE 2: OMO CONVERGENCE LOOP
    // Detecting variance between mathematical edge and narrative confluence.
    let finalAuditSource = "";
    let reconcilerResult = null;

    const varianceDetected = Math.abs(parsedQuant.confidence_score - parsedSim.confidence_score) > 0.3;

    if (varianceDetected) {
      // TRIGGER RECONCILER: Adjudicate the dispute between Quant and Researcher.
      reconcilerResult = await this.runAgent(
        "GOD-ENGINE // RECONCILER",
        `There is a high variance between Data (${parsedQuant.confidence_score}) and Narrative (${parsedSim.confidence_score}) for ${matchup}. 
         TASK: Perform a high-conviction audit. Resolve the contradiction. Identify the 'Locked Alpha'.`,
        `QUANT: ${quantResult}\nSIM: ${simulationResult}`
      );
      finalAuditSource = reconcilerResult;
    } else {
      finalAuditSource = `QUANT: ${quantResult}\nSIM: ${simulationResult}`;
    }

    // PHASE 2.5: AUTONOMOUS VERIFICATION (INSTITUTIONAL GROUND TRUTH)
    const toolbox = new AgentToolbox();
    const system_diagnostic = await toolbox.executeCommand("date && ls -F integrations/claude-bridge");
    const ground_truth = `SYSTEM_DIAGNOSTIC: ${system_diagnostic}\nENVIRONMENT: PRODUCTION_CONVERGENCE_ACTIVE`;

    // PHASE 3: THE MARKET AUDITOR (V17.0)
    const auditResult = await this.runAgent(
      "GOD-ENGINE // KARPATHY_EXECUTIVE",
      `You are a Portfolio Manager at a Tier-1 Hedge Fund. Perform the final Audit.
       
       CONSTRAINTS:
       - Every command MUST start with: 'EXECUTIVE_SUMMARY: Analysis complete. Conviction Locked.'
       - Every command MUST end with: 'EXECUTION_HASH: [SIGMA_NOTATION].'
       - OMQX_PROTOCOL: Synthesize all data into a binary execution command.
       
       TASK: Synthesize the final ${matchup} data. Provide binary execution commands (SGP legs). Use the provided GROUND_TRUTH to verify environment readiness.`,
      `${finalAuditSource}\nGROUND_TRUTH: ${ground_truth}`
    );

    const parsedAudit = SafeSwarmParser(auditResult) as SwarmAgentData;
    
    const payload: SwarmFinalPayload = {
      ...parsedAudit,
      swarm_report: {
        quant: parsedQuant,
        simulation: parsedSim,
        audit_verdict: reconcilerResult ? "RECONCILER_ACTIVE" : "CONVERGENCE_LOCKED"
      },
      hash: "Σ_" + Math.random().toString(36).substring(7).toUpperCase(),
      timestamp: new Date().toLocaleTimeString()
    };

    return payload;
  }

  async quantumMission(goal: string): Promise<QuantumSession> {
    const toolbox = new AgentToolbox();
    const logs: QuantumToolResult[] = [];
    let currentStep = 0;
    const maxSteps = 5; // Institutional safety limit

    const missionContext = `You are a CLAUDE_CODE Savant. You have tool access.
    GOAL: ${goal}
    TOOLS: executeCommand(cmd), readFile(path), writeFile(path, content).
    FORMAT: You must output a JSON command: { "tool": "toolName", "args": ["arg1", "arg2"] } or { "done": true, "summary": "result" }.`;

    while (currentStep < maxSteps) {
      const context = logs.length > 0 ? JSON.stringify(logs) : "MISSION_START";
      const resp = await this.runAgent("QUANTUM_COORDINATOR", `Plan next step. Status: ${context}`, missionContext);
      const parsed = SafeSwarmParser(resp) as { done?: boolean; summary?: string; tool?: string; args?: string[] };

      if (parsed.done) {
        return {
          goal,
          logs,
          final_verdict: parsed.summary || "SUCCESS",
          hash: "Σ_Q_" + Math.random().toString(36).substring(7).toUpperCase()
        };
      }

      let output = "";
      if (parsed.tool === 'executeCommand' && parsed.args) output = await toolbox.executeCommand(parsed.args[0]);
      if (parsed.tool === 'readFile' && parsed.args) output = await toolbox.readFile(parsed.args[0]);
      if (parsed.tool === 'writeFile' && parsed.args) output = await toolbox.writeFile(parsed.args[0], parsed.args[1]);

      logs.push({
        tool: parsed.tool || "UNKNOWN_TOOL",
        output: output.length > 500 ? output.substring(0, 500) + "..." : output,
        success: !output.includes("_ERROR"),
        timestamp: new Date().toISOString()
      });

      currentStep++;
    }

    return {
      goal,
      logs,
      final_verdict: "MAX_STEPS_REACHED: Mission paused for safety.",
      hash: "Σ_Q_TIMEOUT"
    };
  }
}

const swarm = new AgentSwarm();

export async function generateAlphaSheet(sport: string): Promise<AlphaSheetContainer> {
  try {
    const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY || "");
    const model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });

    const prompt = `
      ROLE: V13 God-Engine // Market Aggressor Sheet Generator.
      TASK: Generate a high-alpha "Cheat Sheet" for the current ${sport} slate.
      
      REQUIRED FORMAT: JSON Array of 10 objects.
      Each object must contain:
      - 'rank': number (1-10)
      - 'team_logo': string (A valid MLB/NBA team logo URL fallback or code)
      - 'player_name': string
      - 'metric_label': string (e.g. "SLUG%" for MLB, "PR AVG" for NBA)
      - 'metric_value': string (e.g. ".652" or "32.4")
      - 'season_stat': string (e.g. "24 HR" or "14.2 PTS")
      - 'ai_score': number (A 0.0-10.0 confidence score representing the edge)
      - 'status_color': string (Hex for neon green #22c55e or yellow #eab308)
      - 'espn_id': string (Realistic ESPN ID for headshots)

      LOGIC: Focus on high-variance player props with the largest pricing inefficiencies.
    `;

    const result = await model.generateContent(prompt);
    const textResp = result.response.text().replace(/```json|```/g, "");
    const aiResponse = SafeSwarmParser(textResp) as AlphaSheetItem[];

    return {
      title: sport === 'MLB' ? "DAILY DINGER SHEET" : "PROP LOTTO HEATBOARD",
      subtitle: "GOD-ENGINE ALGORITHMIC EDGE // LIVE DATA SYNTHESIS",
      data: aiResponse,
      timestamp: new Date().toLocaleDateString()
    };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    console.error("ALPHA_SHEET_FAILURE:", message);
    throw error;
  }
}

app.post('/api/alpha-sheets', async (req: express.Request, res: express.Response) => {
    try {
        const { sport } = req.body;
        const data = await generateAlphaSheet(sport || 'NBA');
        res.json(data);
    } catch (e: unknown) {
        const message = e instanceof Error ? e.message : String(e);
        res.status(500).json({ error: message });
    }
});

app.post('/api/analyze-unified', async (req: express.Request, res: express.Response) => {
    try {
        const { matchup, sport } = req.body;
        if (!matchup) return res.status(400).json({ error: "MATCHUP_REQUIRED" });
        const data = await swarm.analyzeUnified(matchup, sport || 'NBA');
        res.json(data);
    } catch (e: unknown) {
        const message = e instanceof Error ? e.message : String(e);
        console.error("SWARM_FAILURE:", message);
        res.status(500).json({ error: message });
    }
});

app.post('/api/quantum-mission', async (req: express.Request, res: express.Response) => {
    try {
        const { goal } = req.body;
        if (!goal) return res.status(400).json({ error: "GOAL_REQUIRED" });
        const data = await swarm.quantumMission(goal);
        res.json(data);
    } catch (e: unknown) {
        const message = e instanceof Error ? e.message : String(e);
        console.error("QUANTUM_MISSION_FAILURE:", message);
        res.status(500).json({ error: message });
    }
});

// Prophet Engine: single highest-conviction pick for the day
app.get('/api/prophet', async (req: express.Request, res: express.Response) => {
    try {
        const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY || "");
        const model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });

        const today = new Date().toLocaleDateString('en-US', {
            weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'
        });

        const prompt = `
ROLE: V13 God-Engine // Prophet Terminal // Single Best Pick Generator.
DATE: ${today}.

TASK: Generate today's single highest-conviction sports betting pick using first-principles quantitative reasoning.

REQUIRED FORMAT: Output ONLY a raw JSON object — no markdown, no explanation — with exactly these keys:
{
  "selection": "string (e.g. 'LeBron James Over 26.5 Points' or 'Celtics -5.5')",
  "odds": "string (American odds e.g. '-110' or '+145')",
  "game_name": "string (e.g. 'Celtics vs Lakers — NBA — Tonight 7:30 PM ET')",
  "value_gap": "string (e.g. '+8.4% EV' or '+11.2% EDGE')",
  "recommended_unit": "string (e.g. '2 UNITS' or '1.5 UNITS')",
  "logic_bullets": ["string", "string", "string"],
  "correlated_insight": "string (a correlated SGP or parlay leg suggestion)"
}

LOGIC: Pick a real NBA or MLB game likely scheduled tonight. Use sharp, quantitative reasoning. Cite specific stats, trends, and matchup inefficiencies. Be precise. No filler.
        `.trim();

        const result = await model.generateContent(prompt);
        const textResp = result.response.text().replace(/```json|```/g, "").trim();
        const parsed = SafeSwarmParser(textResp) as Record<string, unknown>;

        res.json({
            ...parsed,
            hash: "Σ_" + Math.random().toString(36).substring(7).toUpperCase()
        });
    } catch (e: unknown) {
        const message = e instanceof Error ? e.message : String(e);
        console.error("PROPHET_ENGINE_FAILURE:", message);
        res.status(500).json({ error: "PROPHET_ENGINE_FAILURE", message });
    }
});

// Proxy route to fetch images and supply CORS headers so html2canvas doesn't taint
app.get('/api/proxy-image', async (req: express.Request, res: express.Response) => {
    try {
        const { url } = req.query;
        if (!url) return res.status(400).send('URL is required');

        const response = await fetch(decodeURIComponent(url as string));
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

        const arrayBuffer = await response.arrayBuffer();
        const buffer = Buffer.from(arrayBuffer);

        res.set('Access-Control-Allow-Origin', '*');
        res.set('Content-Type', response.headers.get('content-type') || 'image/png');
        res.set('Cache-Control', 'public, max-age=31536000');
        res.send(buffer);
    } catch (error) {
        console.error('Image proxy error:', error);
        res.status(500).send('Error proxying image');
    }
});

app.listen(port, '0.0.0.0', () => {
    console.log(`🚀 God-Engine V14.0 First-Principles Backend Active on port ${port}`);
});
