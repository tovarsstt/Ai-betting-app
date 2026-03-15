# app-ai-bets

A high-performance AI betting engine and prediction UI that translates predictive logic models and sharp market signals into actionable intelligence.

## Why this exists
I’m a student of both psychology and code, building comprehensive tools that merge sports analytics, machine learning, and market sentiment. This repository represents the "V12 God-Engine"—transitioning from a Python/SQLite monolithic architecture into a modern TypeScript, Express, and PostgreSQL-powered stack, layered with an aesthetic React interface.

## Current Status
**Experimental / Active Development.** The prediction pipelines, sharp money EV math, and UI layouts are functional. We are actively refining the TypeScript schemas and autonomous background data ingestion loops.

## Features
- **V12 God-Engine Dashboard:** A dark-mode, carbon-fibre styled interface to visualize predictions, line movements, and EV signals.
- **Python-to-TypeScript Port:** Core python predictive logic (`psych_factors`, `circadian_friction`, `ev_market_filter`) natively executing within Node.js.
- **Postgres DB:** Utilizing Drizzle ORM and `pglite` for highly scalable local database management.
- **Autonomous Polling:** Background processes run autonomously to ingest live API events and recalculate match edges via Cron.
- **React Query Hooks:** Dynamic and responsive frontend API integrations.

## Tech Stack
- **Frontend:** React, Vite, Shadcn UI, Tailwind CSS, Wouter, TanStack Query
- **Backend:** Node.js, Express, Zod (Validation), Drizzle ORM
- **Database:** PostgreSQL (via `@electric-sql/pglite`)

## How to Run It

### 1. Prerequisites
Make sure you have Node.js and `npm` installed.

### 2. Setup Dependencies
From the root directory, install all packages:
```bash
npm install
```

### 3. Environment Config
Create a `.env` file in the root directory and add any keys necessary to run the project. *(Note: DO NOT upload your `.env` file online. It is protected by `.gitignore` by default.)*
```
# Example .env format
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/app_ai_bets
# Other API Tokens go here
```

### 4. Database Initialization
This project uses a local Postgres database embedded into the `.data/` folder via PGlite. To generate the tables, run:
```bash
npx tsx src/db/migrate.ts
```

### 5. Start the Engine
Boot both the background data processes and the Vite frontend simultaneously:
```bash
npm run dev
```

The V12 UI will be available in your browser at: `http://localhost:5173`

## Repository Structure
- `/src/`: React frontend UI, Node.js API routes, TS predictive logic services, and DB schemas.
- `/scripts/`: Python analytics scripts and background web scrapers.
- `/data/`: Stored analysis, JSONs, or CSV extracts.
- `server.js`: The Express API and Webhook entry point.

## License
MIT License - See the [LICENSE](LICENSE) file for more details.
