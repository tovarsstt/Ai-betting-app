# Repo Integration Report — 15 candidates → Caveman Locks

**Date:** 2026-07-20
**App:** Caveman Locks — React 19 + Vite front, ~240 KB Express `server.ts`, ~95 Python model scripts, per-sport betting skills, TikTok content lane.
**Method:** every repo's real README/skill read before judging. No repo was "added" on faith. The rule was Karpathy-simple: *does this make the betting app better, and can it actually work here?* If not, it is documented, not jammed in.

## Verdict table

| # | Repo | What it really is | Verdict | Where it lands |
|---|------|-------------------|---------|----------------|
| 1 | Nutlope/**hallmark** | Anti-AI-slop UI *design skill* (SKILL.md + refs) | ✅ **Integrated** | `skills/design/hallmark/` |
| 2 | jamiepine/**voicebox** | Local TTS voice studio (Tauri app) | ✅ **Integrated (as feature)** | `scripts/pick_narration.py` |
| 3 | DeusData/**codebase-memory-mcp** | C MCP: code knowledge-graph, <1 ms queries | 🔧 **Dev tool (recommended)** | setup below |
| 4 | tirth8205/**code-review-graph** | Tree-sitter review graph, ~82× token cut, MCP | 🔧 **Dev tool (recommended)** | setup below |
| 5 | usestrix/**strix** | Autonomous AI pentest CLI (Docker) | 🔧 **Security tool (recommended)** | setup below |
| 6 | diegosouzapw/**OmniRoute** | LLM gateway: 271 providers, token compression | 🔧 **Cost gateway (optional)** | see note — overlaps 9Router |
| 7 | ibelick/**ui-skills** | `npx` router over UI design patterns | 🔧 **Design tool (optional)** | `npx ui-skills start` |
| 8 | kangarooking/**cangjie-skill** | Pipeline: books/videos → new AI skills | 📚 **Optional meta-tool** | see note |
| 9 | Shubhamsaboo/**awesome-llm-apps** | *Curated collection*, not an app | 📚 **Reference only** | bookmark |
| 10 | wonderwhy-er/**DesktopCommanderMCP** | MCP for file/terminal/process control | ⚠️ **Skip** | redundant + broad access |
| 11 | every-app/**open-seo** | Ahrefs/Semrush alternative (SEO) | ⚠️ **Deferred** | only if a public marketing site ships |
| 12 | JCodesMore/**ai-website-cloner-template** | Clone any site → Next.js | ❌ **No fit** | app clones nothing |
| 13 | MadsLorentzen/**ai-job-search** | Automates job applications + CVs | ❌ **No fit** | unrelated domain |
| 14 | HKUDS/**DeepTutor** | Agentic learning/tutoring workspace | ❌ **No fit** | separate heavy app |
| 15 | tokio-rs/**topcoat** | Rust fullstack framework | ❌ **No fit** | adopting = full rewrite |

Legend: ✅ done · 🔧 wire when you want it (real value, needs install/keys) · 📚 reference · ⚠️ conditional · ❌ won't help this app.

---

## What was actually added (working now)

### 1. Hallmark → the frontend design skill
Copied the real skill (MIT) verbatim into `skills/design/hallmark/` (SKILL.md + all
`references/`). Added `PROJECT_NOTES.md` so it obeys the fixed brand (ochre/charcoal,
no blue, no emoji) instead of its 20 generic themes. Use it when building/redesigning
`src/pages/*` — it enforces structural variety and runs 57 slop-test gates before UI ships.

### 2. Voicebox → pick-recap narration (`scripts/pick_narration.py`)
The betting app doesn't need a desktop voice studio; it needs *picks turned into
spoken word* for the TikTok/recap lane. Built exactly that:
- pick JSON (`{match, selection, decimal, prob, why}`) or a `bank_builder` ticket list →
  short **caveman voiceover** script.
- renders audio locally via macOS `say` today (tested, 428 KB AIFF out), with a
  one-flag swap to a production voice: `--engine "piper -m cave.onnx -f {out}"` or any
  Voicebox/Chatterbox/Kokoro command reading text on stdin.
- **never invents a number** — a leg with no `prob` drops that line instead of faking it
  (same discipline as every other script here).

```bash
echo '{"match":"Spain v Argentina","selection":"Over 2.5","decimal":1.95,"prob":0.61}' \
  | python3 scripts/pick_narration.py --audio recap.aiff --json
```
Feed it `bank_builder` / `/api/bank-builder` output to narrate a whole slate.

---

## Recommended tools — real value, need a deliberate install (not auto-added)

These are **not** app features; they make building/shipping the app cheaper and safer.
Not committed blindly because each needs an install or API key I can't verify headlessly.

### code-review-graph (#4) — pairs with `/code-review`
```bash
pipx install code-review-graph        # or: pip install code-review-graph
code-review-graph build               # index the repo
code-review-graph install claude-code # register the MCP
```
Cuts review token cost ~82× by feeding only blast-radius files. Best ROI given the
240 KB `server.ts` + 95 scripts.

### codebase-memory-mcp (#3) — overlaps the existing CodeGraph skill
Same idea, C-fast. Pick **one** graph tool (this *or* #4 *or* the current `.codegraph/`),
not all three — running duplicates is wasted indexing. Build from source per its README.

### strix (#5) — pre-deploy security scan (like the ECC AgentShield step)
```bash
pipx install strix-agent
export STRIX_LLM=anthropic/claude-... ; export LLM_API_KEY=...
strix --target ./                     # scans the codebase; Docker sandbox
```
Worth it: the app runs a server and touches Stake/odds APIs. Run it before deploys.
Heavy (Docker + LLM spend) — a checkpoint, not a loop.

### OmniRoute (#6) — LLM cost gateway
Does the same job as the **9Router** skill already listed in CLAUDE.md. Don't run both —
pick one, point `ANTHROPIC_BASE_URL` / the SDK `baseURL` at it, keep it off high-volume
loops (see the Fable-5 cost note). Documented, not wired, to avoid a silent double-proxy.

### ui-skills (#7) — complements Hallmark
`npx ui-skills start` — zero install, routes the agent to a UI pattern set. Use alongside
Hallmark; Hallmark owns the brand gates, ui-skills is a pattern lookup.

### cangjie-skill (#8) — skill factory
Turns betting books/podcasts/videos into new `skills/betting/*` files via its RIA-TV++
pipeline. Useful *if* you want to grow the skill library from external content; otherwise skip.

---

## Not added — and why (honest)

- **awesome-llm-apps (#9)** — a *list* of 100+ example apps, nothing to install. Kept as a
  pattern reference (its RAG/agent examples) — bookmark, don't clone.
- **DesktopCommanderMCP (#10)** — duplicates Claude Code's own file/terminal tools and grants
  broad system access for no betting-specific gain. Skipped on the "no speculative surface" rule.
- **open-seo (#11)** — only pays off if a public, indexable marketing site ships. Current app
  is the single-page Game Breakdown product. Revisit if that changes.
- **ai-website-cloner-template (#12)**, **ai-job-search (#13)**, **DeepTutor (#14)**,
  **topcoat (#15)** — wrong domain or a wholesale stack change. Adding them would bloat the
  repo and break the "every changed line traces to the goal" test. Left out on purpose.

---

## One-line summary
Added the two that make the betting app better and actually run here (Hallmark UI skill,
pick narration). Flagged five that are worth a deliberate install (review-graph, memory-mcp,
strix, OmniRoute/9Router, ui-skills). Left the rest out — jamming a job-search bot or a Rust
framework into a sports-betting app is the opposite of good engineering.
