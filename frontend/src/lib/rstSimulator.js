/**
 * rstSimulator.js — Client-side Runtime Stiffness Tensor simulator.
 *
 * Used to render RST visualizations in "offline" / demo mode when the
 * obs_server is not available, or to preview a scenario before committing
 * it to the backend.
 *
 * The math mirrors backend/obs/engines/rst_engine.py exactly so the
 * frontend always renders the same output that the backend would produce.
 */

// Service graph topology (mirrors rst_engine.py)
export const ALL_NODES = ['Frontend', 'API', 'Cache', 'Backend', 'DB', 'Queue'];

export const GRAPH_EDGES = [
  ['Frontend', 'API'],
  ['API',      'Cache'],
  ['API',      'Backend'],
  ['Backend',  'DB'],
  ['Backend',  'Queue'],
  ['Cache',    'DB'],
];

// Pre-computed structural degree
const NODE_DEGREE = Object.fromEntries(ALL_NODES.map(n => [n, 0]));
for (const [a, b] of GRAPH_EDGES) {
  NODE_DEGREE[a]++;
  NODE_DEGREE[b]++;
}
const MAX_DEGREE = Math.max(...Object.values(NODE_DEGREE));

// Tensor component weights (match rst_engine.py defaults)
const W = { A: 0.20, H: 0.15, S: 0.20, D: 0.15, F: 0.15, R: 0.15 };

const LATENCY_BASELINE_MS = 50.0;
const LATENCY_CEILING_MS  = 1500.0;

/**
 * Compute a single-node tensor from raw metrics.
 *
 * @param {string} node
 * @param {{ latency?: number, error?: number, saturation?: number, traffic?: number }} metrics
 * @param {{ eutectic_d2?: number }} phaseData
 * @param {object} scenarioOverrides  — per-component scale factors { K_A, K_H, ... }
 * @returns {{ K_A, K_H, K_S, K_D, K_F, K_R, K_eff, sigma, epsilon }}
 */
export function computeNodeTensor(node, metrics = {}, phaseData = {}, scenarioOverrides = {}) {
  const latency    = metrics.latency    ?? LATENCY_BASELINE_MS;
  const errorRate  = metrics.error      ?? 0;
  const saturation = metrics.saturation ?? 0;

  const latencyRatio = latency / LATENCY_BASELINE_MS;

  let K_A = Math.max(0.01, 1.0 - errorRate);
  let K_S = Math.max(0.01, 1.0 - saturation);
  let K_D = 0.5 + 0.5 * (NODE_DEGREE[node] / MAX_DEGREE);
  let K_H = 0.5; // default when no gain matrix
  let K_F = Math.max(0.01, 1.0 / (1.0 + Math.log(Math.max(latencyRatio, 1.0))));

  let K_R;
  if (phaseData.eutectic_d2 != null) {
    K_R = Math.exp(-phaseData.eutectic_d2);
  } else {
    const stressProxy =
      0.30 * Math.min(1.0, Math.max(0.0, (latencyRatio - 1.0) / (LATENCY_CEILING_MS / LATENCY_BASELINE_MS - 1.0))) +
      0.35 * Math.min(1.0, errorRate) +
      0.35 * Math.min(1.0, saturation);
    K_R = Math.max(0.01, Math.exp(-3.0 * Math.max(0.0, stressProxy)));
  }

  // Apply scenario overrides
  K_A *= scenarioOverrides.K_A ?? 1.0;
  K_H *= scenarioOverrides.K_H ?? 1.0;
  K_S *= scenarioOverrides.K_S ?? 1.0;
  K_D *= scenarioOverrides.K_D ?? 1.0;
  K_F *= scenarioOverrides.K_F ?? 1.0;
  K_R *= scenarioOverrides.K_R ?? 1.0;

  // Clamp
  const clamp = v => Math.min(1.0, Math.max(0.01, v));
  K_A = clamp(K_A); K_H = clamp(K_H); K_S = clamp(K_S);
  K_D = clamp(K_D); K_F = clamp(K_F); K_R = clamp(K_R);

  const K_eff = Math.max(
    0.001,
    Math.pow(K_A, W.A) *
    Math.pow(K_H, W.H) *
    Math.pow(K_S, W.S) *
    Math.pow(K_D, W.D) *
    Math.pow(K_F, W.F) *
    Math.pow(K_R, W.R)
  );

  const sigma = (
    0.30 * Math.min(1.0, Math.max(0.0, (latencyRatio - 1.0) / (LATENCY_CEILING_MS / LATENCY_BASELINE_MS - 1.0))) +
    0.35 * Math.min(1.0, errorRate) +
    0.35 * Math.min(1.0, saturation)
  );

  const epsilon = Math.min(5.0, Math.max(0.0, sigma / K_eff));

  return {
    K_A:     +K_A.toFixed(4),
    K_H:     +K_H.toFixed(4),
    K_S:     +K_S.toFixed(4),
    K_D:     +K_D.toFixed(4),
    K_F:     +K_F.toFixed(4),
    K_R:     +K_R.toFixed(4),
    K_eff:   +K_eff.toFixed(4),
    sigma:   +sigma.toFixed(4),
    epsilon: +epsilon.toFixed(4),
  };
}

/**
 * Compute spectral properties (λ2, λmax, rst_sri) from per-node K_eff values.
 *
 * @param {{ [node]: { K_eff: number } }} nodesData
 * @returns {{ lambda2: number, lambda_max: number, rst_sri: number }}
 */
export function computeSpectral(nodesData) {
  const n = ALL_NODES.length;
  const idx = Object.fromEntries(ALL_NODES.map((nd, i) => [nd, i]));
  const W_mat = Array.from({ length: n }, () => new Array(n).fill(0));

  for (const [a, b] of GRAPH_EDGES) {
    const ia = idx[a], ib = idx[b];
    const ka = nodesData[a]?.K_eff ?? 0.5;
    const kb = nodesData[b]?.K_eff ?? 0.5;
    const w = (2 * ka * kb) / (ka + kb + 1e-9);
    W_mat[ia][ib] = w;
    W_mat[ib][ia] = w;
  }

  // Laplacian L = D - W
  const L = Array.from({ length: n }, (_, i) =>
    Array.from({ length: n }, (_, j) => {
      const deg = W_mat[i].reduce((s, v) => s + v, 0);
      return i === j ? deg : -W_mat[i][j];
    })
  );

  // Power iteration for λmax, then deflation for λ2
  // (analytical for 6x6 symmetric is fine with this approach)
  try {
    const eigvals = jacobiEigenvalues(L, n);
    eigvals.sort((a, b) => a - b);
    const lambda2    = eigvals[1] ?? 0;
    const lambda_max = eigvals[n - 1] ?? 0;
    const rst_sri    = lambda2 / (lambda_max + 1e-9);
    return {
      lambda2:    +lambda2.toFixed(4),
      lambda_max: +lambda_max.toFixed(4),
      rst_sri:    +Math.min(1, Math.max(0, rst_sri)).toFixed(4),
    };
  } catch {
    return { lambda2: 0, lambda_max: 0, rst_sri: 0 };
  }
}

/**
 * Simple Jacobi eigenvalue solver for small symmetric matrices.
 * Returns array of eigenvalues.
 */
function jacobiEigenvalues(A, n, maxIter = 200) {
  // Deep-copy A into a mutable 2-D array
  const a = A.map(row => [...row]);
  for (let iter = 0; iter < maxIter; iter++) {
    // Find largest off-diagonal element
    let p = 0, q = 1, max = Math.abs(a[0][1]);
    for (let i = 0; i < n - 1; i++) {
      for (let j = i + 1; j < n; j++) {
        if (Math.abs(a[i][j]) > max) { max = Math.abs(a[i][j]); p = i; q = j; }
      }
    }
    if (max < 1e-10) break;
    const theta = (a[q][q] - a[p][p]) / (2 * a[p][q]);
    const t = Math.sign(theta) / (Math.abs(theta) + Math.sqrt(1 + theta * theta));
    const c = 1 / Math.sqrt(1 + t * t);
    const s = t * c;
    // Rotate
    const app = a[p][p], aqq = a[q][q], apq = a[p][q];
    a[p][p] = app - t * apq;
    a[q][q] = aqq + t * apq;
    a[p][q] = 0;
    a[q][p] = 0;
    for (let r = 0; r < n; r++) {
      if (r === p || r === q) continue;
      const arp = a[r][p], arq = a[r][q];
      a[r][p] = c * arp - s * arq;
      a[p][r] = a[r][p];
      a[r][q] = s * arp + c * arq;
      a[q][r] = a[r][q];
    }
  }
  return ALL_NODES.map((_, i) => a[i][i]);
}

/**
 * Built-in stress scenarios for the RST simulator tab.
 */
export const SCENARIOS = [
  {
    id:   'normal',
    name: 'Normal operation',
    description: 'All nodes at baseline stiffness',
    overrides: {},
  },
  {
    id:   'db_failure',
    name: 'DB partial failure',
    description: 'DB availability drops, fault propagates to Backend and Cache',
    overrides: {
      DB:      { K_A: 0.15, K_F: 0.20 },
      Backend: { K_F: 0.55 },
      Cache:   { K_F: 0.70 },
    },
  },
  {
    id:   'cache_miss_storm',
    name: 'Cache miss storm',
    description: 'Cache saturation collapses; DB and Backend absorb the load',
    overrides: {
      Cache:   { K_S: 0.05, K_A: 0.40 },
      DB:      { K_S: 0.45 },
      Backend: { K_S: 0.50 },
    },
  },
  {
    id:   'healing_saturation',
    name: 'Healing saturation',
    description: 'Healing actions are themselves creating load — K_H drops system-wide',
    overrides: Object.fromEntries(ALL_NODES.map(n => [n, { K_H: 0.10 }])),
  },
  {
    id:   'api_latency_spike',
    name: 'API latency spike',
    description: 'API experiencing severe latency; upstream Frontend and downstream are stressed',
    overrides: {
      API:      { K_F: 0.10, K_A: 0.50 },
      Frontend: { K_F: 0.60 },
      Backend:  { K_F: 0.65 },
    },
  },
];
