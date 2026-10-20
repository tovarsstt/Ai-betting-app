// Shared pure math: logistic helpers, ridge logistic regression, scoring rules.

export const clamp = (x: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, x));
export const logit = (p: number): number => { const q = clamp(p, 1e-6, 1 - 1e-6); return Math.log(q / (1 - q)); };
export const sigmoid = (z: number): number => 1 / (1 + Math.exp(-z));

// Standard normal CDF (Abramowitz-Stegun 7.1.26 via erf)
export function normCdf(z: number): number {
  const t = 1 / (1 + 0.3275911 * Math.abs(z) / Math.SQRT2);
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-(z * z) / 2);
  return z >= 0 ? 0.5 * (1 + y) : 0.5 * (1 - y);
}

// Solve A x = b (Gaussian elimination with partial pivoting). A is n x n.
function solve(A: number[][], b: number[]): number[] {
  const n = b.length;
  const M = A.map((r, i) => [...r, b[i]]);
  for (let c = 0; c < n; c++) {
    let p = c;
    for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    [M[c], M[p]] = [M[p], M[c]];
    const d = M[c][c] || 1e-12;
    for (let r = c + 1; r < n; r++) {
      const f = M[r][c] / d;
      for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k];
    }
  }
  const x = new Array<number>(n).fill(0);
  for (let r = n - 1; r >= 0; r--) {
    let s = M[r][n];
    for (let k = r + 1; k < n; k++) s -= M[r][k] * x[k];
    x[r] = s / (M[r][r] || 1e-12);
  }
  return x;
}

export interface LogisticModel { w: number[]; b: number }

// Ridge logistic regression via IRLS (Newton). Intercept is not penalised.
// `prior` shrinks weights toward a given vector instead of 0 (e.g. toward equal-weight averaging).
export function fitLogistic(X: number[][], y: number[], l2 = 1, prior?: number[], iters = 25): LogisticModel {
  const d = X[0]?.length ?? 0;
  const pr = prior ?? new Array<number>(d).fill(0);
  let beta = [0, ...pr]; // [b, w...]
  for (let it = 0; it < iters; it++) {
    const H = Array.from({ length: d + 1 }, () => new Array<number>(d + 1).fill(0));
    const g = new Array<number>(d + 1).fill(0);
    for (let i = 0; i < X.length; i++) {
      const xi = [1, ...X[i]];
      let z = 0;
      for (let k = 0; k <= d; k++) z += beta[k] * xi[k];
      const p = sigmoid(z);
      const w = Math.max(p * (1 - p), 1e-6);
      for (let k = 0; k <= d; k++) {
        g[k] += (p - y[i]) * xi[k];
        for (let m = 0; m <= d; m++) H[k][m] += w * xi[k] * xi[m];
      }
    }
    for (let k = 1; k <= d; k++) { g[k] += l2 * (beta[k] - pr[k - 1]); H[k][k] += l2; }
    const step = solve(H, g);
    let mx = 0;
    for (let k = 0; k <= d; k++) { beta[k] -= step[k]; mx = Math.max(mx, Math.abs(step[k])); }
    if (mx < 1e-8) break;
  }
  return { b: beta[0], w: beta.slice(1) };
}

export const predictLogistic = (m: LogisticModel, x: number[]): number =>
  sigmoid(m.b + x.reduce((s, v, i) => s + v * m.w[i], 0));

// Proper scoring rules (lower = better)
export const logLoss = (p: number[], y: number[]): number =>
  -p.reduce((s, pi, i) => s + y[i] * Math.log(clamp(pi, 1e-9, 1)) + (1 - y[i]) * Math.log(clamp(1 - pi, 1e-9, 1)), 0) / p.length;
export const brier = (p: number[], y: number[]): number =>
  p.reduce((s, pi, i) => s + (pi - y[i]) ** 2, 0) / p.length;
export const accuracy = (p: number[], y: number[]): number =>
  p.reduce((s, pi, i) => s + ((pi >= 0.5 ? 1 : 0) === y[i] ? 1 : 0), 0) / p.length;
