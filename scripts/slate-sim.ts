#!/usr/bin/env -S npx tsx
// Slate simulator CLI
//
//   npx tsx scripts/slate-sim.ts data/slates/nfl-2026-week3-sunday.json
//   npx tsx scripts/slate-sim.ts --live americanfootball_nfl        (needs ODDS_API_KEY)
//   options: --sims 200000 --seed 7 --sigma 13.5 --out reports/week3
//
// Prints a markdown report and, with --out, also writes <out>.md and <out>.json.
import fs from "fs";
import path from "path";
import dotenv from "dotenv";
import { simulateSlate, oddsEventsToSlate, type Slate, type OddsApiEvent, type SlateReport } from "../lib/slate-sim.ts";
import { formatAmerican } from "../lib/betting-math.ts";

dotenv.config();

function arg(name: string): string | undefined {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? process.argv[i + 1] : undefined;
}

async function loadSlate(): Promise<Slate> {
  const live = arg("live");
  if (live) {
    const key = process.env.ODDS_API_KEY;
    if (!key) throw new Error("--live needs ODDS_API_KEY in the environment or .env");
    // Featured markets only — alternates/props are not allowed on the bulk /odds endpoint
    const url = `https://api.the-odds-api.com/v4/sports/${live}/odds?apiKey=${key}&regions=us,eu&markets=h2h,spreads,totals&oddsFormat=american&dateFormat=iso`;
    const res = await fetch(url, { signal: AbortSignal.timeout(15_000) });
    if (!res.ok) throw new Error(`Odds API ${res.status}: ${await res.text()}`);
    console.error(`Odds API quota: used ${res.headers.get("x-requests-used")}, remaining ${res.headers.get("x-requests-remaining")}`);
    return oddsEventsToSlate(await res.json() as OddsApiEvent[], `${live} (live)`, live.split("_").pop()!.toUpperCase());
  }
  const file = process.argv.slice(2).find(a => a.endsWith(".json"));
  if (!file) throw new Error("usage: slate-sim.ts <slate.json> | --live <sport_key>");
  return JSON.parse(fs.readFileSync(file, "utf8")) as Slate;
}

const pct = (x: number | null, dp = 1) => (x === null ? "—" : `${(x * 100).toFixed(dp)}%`);

// Win-probability-first list (CLAUDE.md ranking rule): one bet per game, quoted
// prices only, EV floor so heavy chalk can't top the list just by "usually winning".
export const WIN_FIRST_MIN_EV = -5;
export function winFirst(r: SlateReport, n = 8) {
  const best = new Map<string, SlateReport["ranked"][number]>();
  for (const o of r.ranked) {
    if (o.price_assumed || o.ev_pct < WIN_FIRST_MIN_EV) continue;
    const cur = best.get(o.game);
    if (!cur || o.fair_prob > cur.fair_prob) best.set(o.game, o);
  }
  return [...best.values()].sort((a, b) => b.fair_prob - a.fair_prob || b.ev_pct - a.ev_pct).slice(0, n);
}

export function toMarkdown(r: SlateReport): string {
  const out: string[] = [];
  out.push(`# ${r.slate}`);
  out.push("");
  out.push(`Lines captured: ${r.captured_at ?? "unknown"} — ${r.capture_method ?? ""}`);
  out.push(`Model: market-implied NFL margin distribution with key numbers, σ=${r.sigma} (fitted to ${r.sigma_calibrated_from} spread/ML pairs), ${r.sims.toLocaleString()} Monte Carlo sims (seed ${r.seed}).`);
  out.push("Fair probabilities are the market's own no-vig view. A positive EV only appears where a price beats that consensus.");
  out.push("");
  out.push("## Board");
  out.push("");
  out.push("| Game | Kick (ET) | Spread (home) | Fair line | Home win (ML, no-vig) | Spread-implied | Gap | Proj. total |");
  out.push("|---|---|---|---|---|---|---|---|");
  for (const g of r.games) {
    out.push(`| ${g.id} | ${g.kickoff_et ?? ""} | ${g.spread_home ?? "—"} | ${g.fair_spread_line > 0 ? "+" : ""}${g.fair_spread_line} | ${pct(g.consensus_home_ml_prob)} | ${pct(g.spread_implied_home_win)} | ${g.ml_vs_spread_gap_pct === null ? "—" : `${g.ml_vs_spread_gap_pct > 0 ? "+" : ""}${g.ml_vs_spread_gap_pct}`} | ${g.total_mean ?? "—"} |`);
  }
  out.push("");
  out.push("## Most likely winners (win % first, EV guard-railed)");
  out.push("");
  out.push(`Best-hitting bet per game at a quoted price, ranked by win probability. Anything worse than ${WIN_FIRST_MIN_EV}% EV is dropped — a -1000 favorite "usually wins" but still loses money.`);
  out.push("");
  out.push("| # | Bet | Price | Win % | EV | Verdict |");
  out.push("|---|---|---|---|---|---|");
  winFirst(r).forEach((o, i) => {
    const verdict = o.ev_pct >= 0 ? "BET" : "LEAN (small -EV)";
    out.push(`| ${i + 1} | ${o.selection} | ${formatAmerican(o.price)} | ${pct(o.fair_prob)} | ${o.ev_pct > 0 ? "+" : ""}${o.ev_pct}% | ${verdict} |`);
  });
  out.push("");
  out.push("## Top 10 bets by EV (vs. market consensus)");
  out.push("");
  out.push("| # | Bet | Price | Book | Fair win % | Push % | EV | ½-Kelly | Price source |");
  out.push("|---|---|---|---|---|---|---|---|---|");
  r.ranked.slice(0, 10).forEach((o, i) => {
    out.push(`| ${i + 1} | ${o.selection} | ${formatAmerican(o.price)} | ${o.book} | ${pct(o.fair_prob)} | ${pct(o.push_prob)} | ${o.ev_pct > 0 ? "+" : ""}${o.ev_pct}% | ${o.half_kelly_pct}% | ${o.price_assumed ? "ASSUMED -110" : "quoted"} |`);
  });
  const positive = r.ranked.filter(o => o.ev_pct > 0 && !o.price_assumed);
  out.push("");
  out.push(positive.length
    ? `${positive.length} bet(s) show positive EV at a quoted price. Each one depends on that exact book still offering that price.`
    : "No bet shows positive EV at a quoted price. At standard -110 juice, nothing on this board beats the market.");
  out.push("");
  out.push("## Flags");
  out.push("");
  const flagged = r.games.filter(g => g.flags.some(f => f.startsWith("ML_SPREAD")));
  if (!flagged.length) out.push("No game's moneyline disagrees with its spread by 3+ points.");
  for (const g of flagged) for (const f of g.flags.filter(f => f.startsWith("ML_SPREAD"))) out.push(`- **${g.id}**: ${f}`);
  out.push("");
  out.push("## Slate scenarios (Monte Carlo)");
  out.push("");
  out.push(`- Expected outright upsets: **${r.upsets.expected}** of ${r.games.length} games`);
  out.push(`- P(at least 3 upsets): ${pct(r.upsets.p_at_least[3] ?? 0)} · P(at least 5): ${pct(r.upsets.p_at_least[5] ?? 0)} · P(zero upsets): ${pct(1 - (r.upsets.p_at_least[1] ?? 0))}`);
  out.push(`- Expected favorites covering: **${r.favorites_covering.expected}**`);
  out.push("");
  out.push("## Best-EV parlays from the ranked legs (independent games)");
  out.push("");
  out.push("| Legs | Price | Hit % (analytic) | Hit % (sim) | EV |");
  out.push("|---|---|---|---|---|");
  for (const p of r.parlays) out.push(`| ${p.legs.join("<br>")} | ${p.price} | ${pct(p.analytic_prob)} | ${pct(p.mc_prob)} | ${p.ev_pct > 0 ? "+" : ""}${p.ev_pct}% |`);
  out.push("");
  out.push("Parlays multiply the vig; they are only +EV when every leg is individually +EV.");
  const notes = r.games.filter(g => g.notes.length);
  if (notes.length) {
    out.push("");
    out.push("## Source notes");
    out.push("");
    for (const g of notes) out.push(`- **${g.id}**: ${g.notes.join("; ")}`);
  }
  return out.join("\n");
}

async function main() {
  const slate = await loadSlate();
  const report = simulateSlate(slate, {
    sims: arg("sims") ? Number(arg("sims")) : undefined,
    seed: arg("seed") ? Number(arg("seed")) : undefined,
    sigma: arg("sigma") ? Number(arg("sigma")) : undefined,
  });
  const md = toMarkdown(report);
  console.log(md);
  const outBase = arg("out");
  if (outBase) {
    fs.mkdirSync(path.dirname(outBase), { recursive: true });
    fs.writeFileSync(`${outBase}.md`, md + "\n");
    fs.writeFileSync(`${outBase}.json`, JSON.stringify(report, null, 2) + "\n");
    console.error(`wrote ${outBase}.md and ${outBase}.json`);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  main().catch(e => { console.error(e instanceof Error ? e.message : e); process.exit(1); });
}
