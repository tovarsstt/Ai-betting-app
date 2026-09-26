import { test } from "node:test";
import assert from "node:assert/strict";
import {
  impliedProb, devig, devigMulti, toDecimal, decimalToAmerican, parseAmerican, ev, halfKelly,
  parlayPrice, normalCDF, nflMarginPmf, pmfWinProb, pmfCover, fitMuToWinProb, fitMuToSpread,
  noPushProb, totalOverProb, fitTotalMean, auditPick, rng, probToAmerican,
} from "./betting-math.ts";

const close = (a: number, b: number, tol = 1e-3) => assert.ok(Math.abs(a - b) < tol, `${a} !≈ ${b}`);

test("implied probability and decimal conversion", () => {
  close(impliedProb(-110), 0.5238);
  close(impliedProb(150), 0.4);
  close(toDecimal(-200), 1.5);
  close(toDecimal(150), 2.5);
  assert.equal(decimalToAmerican(2.5), 150);
  assert.equal(decimalToAmerican(1.5), -200);
  assert.equal(probToAmerican(0.5), 100);
});

test("devig 2-way and 3-way", () => {
  const d = devig(impliedProb(-110), impliedProb(-110));
  close(d.p1, 0.5); close(d.vig, 4.76, 0.01);
  // soccer 3-way: +150 / +230 / +200
  const m = devigMulti([impliedProb(150), impliedProb(230), impliedProb(200)]);
  close(m.fair.reduce((a, b) => a + b, 0), 1);
  assert.ok(m.vig > 0);
});

test("parseAmerican handles strings, EVEN, junk", () => {
  assert.equal(parseAmerican("+130"), 130);
  assert.equal(parseAmerican("-115"), -115);
  assert.equal(parseAmerican("EVEN"), 100);
  assert.equal(parseAmerican(-110), -110);
  assert.equal(parseAmerican("est."), null);
  assert.equal(parseAmerican("+50"), null);
  assert.equal(parseAmerican(undefined), null);
});

test("EV and Kelly", () => {
  close(ev(0.5, 100), 0);
  close(ev(0.55, -110), 0.05, 1e-2);
  assert.equal(halfKelly(0.4, -110), 0);
  close(halfKelly(0.55, 100), 0.05);
});

test("parlay price multiplies decimal odds", () => {
  const p = parlayPrice([-110, -110, -110]);
  close(p.decimal, 6.9579, 1e-3);
  assert.equal(p.american, 596);
});

test("normalCDF", () => {
  close(normalCDF(0), 0.5, 1e-7);
  close(normalCDF(1.96), 0.975, 1e-4);
  close(normalCDF(-1), 0.1587, 1e-4);
});

test("NFL margin pmf: sums to 1, key numbers, rare ties, symmetric at mu=0", () => {
  const p = nflMarginPmf(0);
  close([...p.values()].reduce((a, b) => a + b, 0), 1, 1e-9);
  const abs = (k: number) => p.get(k)! + p.get(-k)!;
  assert.ok(abs(3) > 0.12 && abs(3) < 0.18, `|3| mass ${abs(3)}`);
  assert.ok(abs(7) > abs(8) && abs(7) > abs(6));
  assert.ok(p.get(0)! < 0.005);
  close(pmfWinProb(p), 0.5, 1e-9);
});

test("spread cover: -3 pushes a lot, -2.5 vs -3.5 differ by more than a normal curve would", () => {
  const p = nflMarginPmf(3);
  const r = pmfCover(p, -3);
  close(r.win + r.push + r.loss, 1, 1e-9);
  assert.ok(r.push > 0.06);
  const diff = noPushProb(pmfCover(p, -2.5)) - noPushProb(pmfCover(p, -3.5));
  assert.ok(diff > 0.06, `-2.5 vs -3.5 gap ${diff}`);
});

test("fitters invert the model", () => {
  const mu = fitMuToWinProb(0.7);
  close(pmfWinProb(nflMarginPmf(mu)), 0.7, 1e-6);
  const mu2 = fitMuToSpread(-6.5, 0.5);
  close(noPushProb(pmfCover(nflMarginPmf(mu2), -6.5)), 0.5, 1e-6);
  const tm = fitTotalMean(44.5, 0.5);
  close(tm, 44.5, 1e-6);
  const t = totalOverProb(44, 44);
  assert.ok(t.push > 0.03);
});

test("auditPick flags overconfident and negative-EV picks", () => {
  const a = auditPick("-110", 0.74);
  assert.ok(a.flags.includes("OVERCONFIDENT_EDGE"));
  close(a.ev_pct!, 41.3, 0.1);
  assert.ok(auditPick("-110", 0.5).flags.includes("NEGATIVE_EV"));
  assert.deepEqual(auditPick("n/a", 0.5).flags, ["ODDS_UNPARSEABLE"]);
  const ok = auditPick("+120", 0.48);
  assert.deepEqual(ok.flags, []);
});

test("rng is deterministic", () => {
  const a = rng(1), b = rng(1);
  for (let i = 0; i < 5; i++) assert.equal(a(), b());
});
