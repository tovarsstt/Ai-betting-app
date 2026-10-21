# Caveman Locks — CLAUDE.md

## Brand
- Name: **Caveman Locks**
- Palette: ochre `#C8860A`, charcoal `#2C2C2C`, off-white `#F5F0E8`, dark stone `#1A1A1A`
- No gradients unless earthy (brown→black, ochre→cream). No emoji in UI.
- Pick cards: bet info dominates, secondary info strongly recedes.

## Tone
Talk short like caveman. Save tokens.

## P(win) Rule — FULL TOOLKIT, ALWAYS (all sessions, whole engine)
P(win) is NEVER one formula. Every pick's P(win) comes from running EVERY applicable tool in the repo,
and the report shows each tool's number plus the spread between them. Never skip a tool because it is
inconvenient; if one cannot run, say which and why (never drop it silently, never invent its output).
- Soccer: Poisson / Dixon-Coles (poisson_model, soccer_markets), Monte Carlo (simulate_match), Skellam
  (exact goal difference), binomial / Bernoulli / Beta-Dirichlet W-D-L rates + log5, data-fit Poisson
  regression (poisson_regression), eigenvector ratings (eigen_ratings), Elo, sport_math 3-way anchored
  Dixon-Coles, market devig (multiplicative / power / Shin), chaos_engine (draw risk), failure_modes.
- NBA / basketball: stacked Elo + form + context (nba_stack), normal-margin model (sport_math), Monte Carlo
  of the margin, log5 on Beta-Binomial records, ridge team ratings (team_ratings), market devig.
- Other sports: use that sport's own registry (engine_all / sport_math / engine_v2) — same principle.
- Order of every report: P(win) first -> odds / payout -> EV last. Rank by P(win): likely winners before
  longshots. WIN PROBABILITY DECIDES (user rule, repeated): EV is shown last as information and is NEVER a filter
  for what gets recommended. Practical floors only so a pick pays something: leg odds >= 1.25, ticket odds >= 2.0.
  Show warnings (low-sample club, big model-vs-market gap, wide tool spread, stale ratings) next to the pick
  instead of hiding it.
- Honesty: no tool is claimed to beat the market without out-of-sample validation vs closing lines.
  The market (devigged) is one input and the strongest prior; the code registry is `scripts/pwin_ensemble.py`.

## Section Order Rule (all reports, all sessions)
UCL (Champions League) ALWAYS comes first, then NBA, then any other league. This applies to the report, the
per-tool detail, the SKIPPED list and any summary. Inside each section: P(win) first -> odds/payout -> EV last,
ranked by P(win). Code: `SECTION_ORDER` in `scripts/value_picks.py`. Effort and review time also go to UCL first.

## Total-Anchor Rule (all sports, all sessions)
When the market gives a game total (soccer goals, NBA/NFL points, MLB runs), the MARKET sets the expected total and the
model only sets the split between the teams. Every goal/score-rate tool is rescaled to the market total before any
probability (1X2, totals, BTTS, props) is derived (`scripts/total_anchor.py`, `pwin_ensemble.market_total_from_ou`).
Evidence: soccer Elo model under-predicted Champions League totals by 0.54 goals/match (-1.0 in mismatches, measured
walk-forward with `scripts/validate_ucl.py`); NFL benchmark (`data/benchmarks/nfl_backtest.json`) gives ratings a
weight of 0.0 for totals and a 48.9% hit rate when the model disagreed by 3+ points (n=659). Without a market total the
report must say "total NOT anchored". Never present a model total that disagrees with the market as an edge.

## Ranking Priority
Rank picks by win-probability first, edge (+EV) second. Favor likely winners over longshots.

## API Rules
Never call Odds API / BallDontLie during debug/test. Only on real app usage.

---

## Karpathy Coding Principles

### 1. Think Before Coding
- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, surface them — don't pick silently.
- If something is unclear, stop and ask before implementing.

### 2. Simplicity First
- Minimum code that solves the problem. Nothing speculative.
- No abstractions for single-use code. No "flexibility" that wasn't requested.
- If you write 200 lines and it could be 50, rewrite it.

### 3. Surgical Changes
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style. Every changed line must trace to the user's request.

### 4. Goal-Driven Execution
- Transform tasks into verifiable goals with explicit success criteria.
- For multi-step tasks, state a brief plan with verify steps.

---

## Taste — UI Design Rules (CAVEMAN CTE)
- Color: ochre accent max, used with purpose. No blue buttons.
- Typography: heavy display for headlines, clean sans-serif for body.
- Textures: rough/grainy backgrounds OK — cave painting brand.
- No default Tailwind `rounded-xl shadow-sm bg-white p-6` without intent.
- Each Tailwind class chosen deliberately, not by habit.

---

## Skills Active This Project
| Skill | Purpose |
|-------|---------|
| CodeGraph | Codebase nav — run `codegraph init --index` once |
| Headroom | Context compression — `pip install "headroom-ai[all]"` |
| Kronos | Line movement signals — `pip install torch transformers` |
| Ruflo Neural Trader | Multi-agent pick pipeline |
| ECC AgentShield | Security scan before deploy |
| 9Router | LLM proxy + RTK compression for cost savings |
| Hermes | Telegram bot for automated picks delivery |
