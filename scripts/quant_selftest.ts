// Self-verification: invariants + known values. Exit code != 0 on any failure.
import { predictSoccer, scoreGrid } from '../quant/soccer.ts';
import { devigProportional, evPerUnit, americanToDecimal, kellyFraction } from '../quant/odds.ts';
import { fitLogistic, predictLogistic, normCdf } from '../quant/math.ts';
import { formatPick } from '../quant/report.ts';
let fails = 0;
const ok = (n: string, c: boolean, d = '') => { console.log(`${c ? 'PASS' : 'FAIL'}  ${n} ${d}`); if (!c) fails++; };
const near = (a: number, b: number, t = 1e-6) => Math.abs(a - b) < t;

const g = scoreGrid(1.5, 1.2);
ok('1X2 sums to 1', near(g.pH + g.pD + g.pA, 1), `${(g.pH + g.pD + g.pA).toFixed(9)}`);
ok('equal teams, no home adv => pH==pA', (() => { const s = scoreGrid(1.3, 1.3); return near(s.pH, s.pA, 1e-9); })());
const sym = predictSoccer({ home: { name: 'A', gf: 10, ga: 10, gp: 8 }, away: { name: 'B', gf: 10, ga: 10, gp: 8 }, neutral: true });
ok('identical teams neutral => pH==pA', near(sym.pHome, sym.pAway, 1e-9), `${sym.pHome.toFixed(4)}`);
const strong = predictSoccer({ home: { name: 'S', gf: 20, ga: 4, gp: 8 }, away: { name: 'W', gf: 6, ga: 16, gp: 8 } });
ok('strong home favoured', strong.pHome > 0.6, `pH=${strong.pHome.toFixed(3)} lam=${strong.lambdas.home.toFixed(2)}/${strong.lambdas.away.toFixed(2)}`);
const mk = predictSoccer({ home: { name: 'S', gf: 20, ga: 4, gp: 8 }, away: { name: 'W', gf: 6, ga: 16, gp: 8 } }, { pHome: 0.5, pDraw: 0.27, pAway: 0.23 });
ok('market blend sums to 1', near(mk.pHome + mk.pDraw + mk.pAway, 1));
ok('blend lies between model and market', mk.pHome < strong.pHome && mk.pHome > 0.5);
const dv = devigProportional([1.9, 1.9]);
ok('devig 1.9/1.9 => 50/50, 5.26% hold', near(dv.probs[0], 0.5) && near(dv.overroundPct, 5.2631579, 1e-4), `${dv.overroundPct.toFixed(4)}%`);
ok('EV at fair odds = 0', near(evPerUnit(0.5, 2), 0));
ok('EV p=.55 @ -110', near(evPerUnit(0.55, americanToDecimal(-110)), 0.55 * (100 / 110) - 0.45, 1e-9), evPerUnit(0.55, americanToDecimal(-110)).toFixed(4));
ok('Kelly 0 when -EV', kellyFraction(0.4, 2) === 0);
ok('Kelly capped at 5%', kellyFraction(0.9, 3) === 0.05);
ok('normCdf(1.96)~0.975', near(normCdf(1.96), 0.975, 1e-3));
// logistic recovers a known relationship
let s = 7; const r = () => (s = (s * 1664525 + 1013904223) % 4294967296) / 4294967296;
const X: number[][] = [], y: number[] = [];
for (let i = 0; i < 4000; i++) { const x = r() * 4 - 2; X.push([x]); y.push(r() < 1 / (1 + Math.exp(-(0.5 + 1.5 * x))) ? 1 : 0); }
const m = fitLogistic(X, y, 0.01);
ok('logistic recovers b=.5,w=1.5', Math.abs(m.b - 0.5) < 0.15 && Math.abs(m.w[0] - 1.5) < 0.2, `b=${m.b.toFixed(2)} w=${m.w[0].toFixed(2)}`);
ok('predictLogistic in (0,1)', (() => { const p = predictLogistic(m, [0]); return p > 0 && p < 1; })());
console.log('\n' + formatPick({ label: 'Strong home ML', pWin: mk.pHome, marketOdds: 1.67, marketFair: 0.5 }));
console.log(fails ? `\n${fails} FAILED` : '\nALL PASSED');
process.exit(fails ? 1 : 0);
