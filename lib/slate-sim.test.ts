import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "fs";
import { simulateSlate, analyzeGame, calibrateSigma, oddsEventsToSlate, type Slate } from "./slate-sim.ts";

const slate: Slate = {
  slate: "test", sport: "NFL",
  games: [
    { id: "A@B", away: "A", home: "B", spread: { home: -3 }, total: { points: 44.5 }, moneylines: [{ book: "x", home: -160, away: 135 }] },
    { id: "C@D", away: "C", home: "D", spread: { home: 7 }, total: { points: 41.5 }, moneylines: [{ book: "x", home: 280, away: -350 }, { book: "y", home: 300, away: -380 }] },
    { id: "E@F", away: "E", home: "F", spread: { home: -1 }, moneylines: [{ book: "x", home: -120, away: 100 }] },
    { id: "G@H", away: "G", home: "H", spread: { home: -10 }, total: { points: 47 }, moneylines: [{ book: "x", home: -500, away: 380 }] },
  ],
};

test("analyzeGame: probabilities are coherent and best price is chosen", () => {
  const g = analyzeGame(slate.games[1], 13);
  const ml = g.options.filter(o => o.market === "ML");
  close(ml[0].fair_prob + ml[1].fair_prob, 1);
  const away = ml.find(o => o.side === "away")!;
  assert.equal(away.price, -350); // -350 pays more than -380
  const home = ml.find(o => o.side === "home")!;
  assert.equal(home.price, 300);
  assert.ok(g.fair_spread_line > 0, "home is the dog, so fair line is positive");
});

test("standard -110 spreads and totals are negative EV against their own consensus", () => {
  const g = analyzeGame(slate.games[0], 13);
  for (const o of g.options.filter(o => o.market !== "ML")) assert.ok(o.ev_pct < 0.5, `${o.selection} ${o.ev_pct}`);
});

test("simulateSlate: Monte Carlo agrees with analytic parlay probabilities", () => {
  const r = simulateSlate(slate, { sims: 60_000, seed: 3 });
  assert.equal(r.games.length, 4);
  for (const p of r.parlays) assert.ok(Math.abs(p.mc_prob - p.analytic_prob) < 0.02, JSON.stringify(p));
  assert.ok(r.upsets.expected > 0 && r.upsets.expected < 4);
  // deterministic with a fixed seed
  const r2 = simulateSlate(slate, { sims: 60_000, seed: 3 });
  assert.deepEqual(r2.parlays, r.parlays);
});

test("calibrateSigma picks a sensible NFL sigma on the checked-in Week 3 slate", () => {
  const week3 = JSON.parse(fs.readFileSync(new URL("../data/slates/nfl-2026-week3-sunday.json", import.meta.url), "utf8")) as Slate;
  const { sigma, n } = calibrateSigma(week3);
  assert.equal(n, week3.games.length);
  assert.ok(sigma >= 10 && sigma <= 15, `sigma ${sigma}`);
});

test("oddsEventsToSlate maps The Odds API payload", () => {
  const s = oddsEventsToSlate([{
    id: "1", commence_time: "2026-09-27T17:00:00Z", home_team: "Buffalo Bills", away_team: "Los Angeles Chargers",
    bookmakers: [
      { key: "draftkings", title: "DraftKings", markets: [
        { key: "h2h", outcomes: [{ name: "Buffalo Bills", price: -340 }, { name: "Los Angeles Chargers", price: 270 }] },
        { key: "spreads", outcomes: [{ name: "Buffalo Bills", price: -110, point: -7 }, { name: "Los Angeles Chargers", price: -110, point: 7 }] },
        { key: "totals", outcomes: [{ name: "Over", price: -110, point: 50.5 }, { name: "Under", price: -110, point: 50.5 }] },
      ] },
    ],
  }], "live", "NFL");
  assert.equal(s.games[0].spread?.home, -7);
  assert.equal(s.games[0].total?.points, 50.5);
  assert.deepEqual(s.games[0].moneylines, [{ book: "DraftKings", home: -340, away: 270 }]);
});

function close(a: number, b: number, tol = 1e-3) { assert.ok(Math.abs(a - b) < tol, `${a} !≈ ${b}`); }
