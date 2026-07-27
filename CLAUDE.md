# Caveman Locks — CLAUDE.md

## Brand
- Name: **Caveman Locks**
- Palette: ochre `#C8860A`, charcoal `#2C2C2C`, off-white `#F5F0E8`, dark stone `#1A1A1A`
- No gradients unless earthy (brown→black, ochre→cream). No emoji in UI.
- Pick cards: bet info dominates, secondary info strongly recedes.

## Tone
Talk short like caveman. Save tokens.

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
