# V15.0 // THE GOD-ENGINE TERMINAL

A state-of-the-art **Swarm Intelligence** platform designed for institutional-grade market extraction and high-conviction predictive modeling. The system has been "System Purified," eliminating all legacy technical debt to operate on pure first-principles reasoning.

## 🦾 Core Philosophy: "Model x Machine"

The God-Engine V15.0 operates via a multi-agent swarm architecture inspired by Andrej Karpathy's "Skills" framework. It maintains a strict visual and logical contrast between the sophisticated human-facing "Model" and the clinical, technical "Machine."

## 🧠 Swarm Archetypes (Karpathy Edition)

The engine orchestrates three world-class expert personas to achieve absolute predictive confluence:

1.  **KARPATHY_QUANT**: Senior Quantitative Researcher. Focused on **Σ_Deviation** and global liquidity analysis.
2.  **KARPATHY_RESEARCHER**: Strategic Predictive Analyst. Uses MiroFish-style narrative simulation to filter out retail noise.
3.  **KARPATHY_EXECUTIVE**: Tier-1 Hedge Fund Portfolio Manager. Synthesizes swarm data into binary execution commands.

## 🛠️ Tech Stack: Zero-Dark-Thirty Standard

- **Brain**: Google Gemini 2.5 Flash // AgentSwarm Pipeline.
- **Backend**: Pure TypeScript // Express // Institutional Type-Hardening.
- **Frontend**: React // Vite // Framer Motion // Tailwind (High-Contrast Minimalism).
- **Execution**: Recursive Logic // Sigma-Mutation Hashes // html2canvas social proofing.

## 🚀 Terminal Execution

### 1. Prerequisites
- Node.js (v20+)
- Gemini API Key in `.env`

### 2. Ignition
Install the refined dependencies and start the dual-engine terminal:

```bash
# Total Hardening Setup
npm install

# Start the Backend Machine (Port 3001)
# Terminal A:
npx tsx server.ts

# Start the Model Interface (Port 5173)
# Terminal B:
npm run dev
```

The terminal will be available at: **[http://localhost:5173](http://localhost:5173)**

## 🧮 Slate Simulator & Math Checks

`lib/betting-math.ts` holds the pure betting math (devig, EV, Kelly, parlay pricing, an NFL key-number margin model). `lib/slate-sim.ts` runs it over a whole slate. Both are unit-tested (`npm test`).

```bash
# Simulate a saved slate (lines snapshot in JSON)
npm run slate -- data/slates/nfl-2026-week3-sunday.json --out reports/nfl-2026-week3-sunday

# Pull current lines from The Odds API instead (needs ODDS_API_KEY)
npm run slate -- --live americanfootball_nfl --sims 200000
```

The simulator builds each game's margin distribution from the market's own prices. It does not forecast anything on its own. It reports:
- no-vig fair lines
- where a book's moneyline and spread disagree
- EV and ½-Kelly at every quoted price
- slate-wide Monte Carlo scenarios (upsets, favorites covering)
- the best-EV parlays, with Monte Carlo-checked hit rates

The API also checks the LLM's numbers server-side. It recomputes parlay odds from the leg odds, and it attaches break-even, EV, ½-Kelly and an `OVERCONFIDENT_EDGE` flag to every pick. `ANTHROPIC_MODEL` overrides the default model.

## 📊 Sigma-Proof Audit (V15.0)

Every analysis generates a **Σ_Hash** and is verifiable via the **POST-TRADE_ANALYSIS** portal. Use the **AUDIT** (The Machine) theme in the visualizer for professional social proof.

---
**STATUS: SYSTEM_PURIFIED. 🚀🦾Σ**
