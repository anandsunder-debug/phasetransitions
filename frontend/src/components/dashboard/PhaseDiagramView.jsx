import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Activity } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Phase Diagram View — iron-carbide-style 2D phase chart for the
 * operational state of every service node.
 *
 * X-axis: M/M_cap (memory saturation), 0 → 1.0   (≈ carbon content)
 * Y-axis: L/L₀   (latency ratio),     0 → 20    (≈ temperature)
 *
 * Filled regions show the geometric phase fields from the classifier;
 * boundary lines are crisp transition isotherms; each service is plotted
 * as a labeled dot with a fading 20-sample trajectory tail; Ψ_s is
 * rendered as a star. Regime-override phases (retry_amplification,
 * healing_saturation) appear as banner overlays on top of the chart
 * since they are temporal, not positional.
 */

// Plot dimensions in viewBox units
const VB_W = 720;
const VB_H = 460;
const PAD_L = 70;
const PAD_R = 30;
const PAD_T = 30;
const PAD_B = 50;
const PW = VB_W - PAD_L - PAD_R;  // plot width
const PH = VB_H - PAD_T - PAD_B;  // plot height

// X axis: M/M_cap from 0 to 1
const X_MIN = 0;
const X_MAX = 1;
// Y axis: L/L₀ from 0 to 20  (log-like via sqrt scaling so low values aren't squeezed)
const Y_MIN = 0;
const Y_MAX = 20;

// scaling helpers
const xScale = (m) => PAD_L + ((m - X_MIN) / (X_MAX - X_MIN)) * PW;
// sqrt scale on Y to spread the low-latency region (more legible)
const yNorm  = (l) => Math.sqrt(Math.max(0, Math.min(Y_MAX, l)) / Y_MAX);
const yScale = (l) => PAD_T + (1 - yNorm(l)) * PH;

// Phase region definitions (matching classifier._classify thresholds)
// Order matters: paint largest/lowest-priority first, then overlay smaller ones.
const PHASE_REGIONS = [
  // cascading_collapse: top-right corner (M>0.95 OR L/L₀>20-ish)
  {
    id: 'cascading_collapse', label: 'CASCADING COLLAPSE',
    color: '#FF453A', opacity: 0.18,
    poly: [[0.95, 0], [1, 0], [1, 20], [0.95, 20]],
  },
  // jvm_saturation: high-M or high-L band
  {
    id: 'jvm_saturation', label: 'JVM SATURATION',
    color: '#FFCC00', opacity: 0.14,
    poly: [[0.80, 0], [0.95, 0], [0.95, 20], [0, 20], [0, 4], [0.80, 4]],
  },
  // stable_throughput: the central operating band
  {
    id: 'stable_throughput', label: 'STABLE THROUGHPUT',
    color: '#00FF9D', opacity: 0.12,
    poly: [[0.40, 0.80], [0.80, 0.80], [0.80, 4], [0, 4], [0, 0.80]],
  },
  // warm_runtime: low-M, low-L bracket
  {
    id: 'warm_runtime', label: 'WARM RUNTIME',
    color: '#8FE388', opacity: 0.14,
    poly: [[0.25, 0.50], [0.40, 0.50], [0.40, 0.80], [0, 0.80], [0, 0.50]],
  },
  // cold_start: smallest corner near (0, 0)
  {
    id: 'cold_start', label: 'COLD START',
    color: '#5AC8FA', opacity: 0.18,
    poly: [[0, 0], [0.25, 0], [0.25, 0.50], [0, 0.50]],
  },
  // remaining stable area to the right (M=0.40..0.80, L=0..0.80)
  {
    id: 'stable_throughput_lower', label: '',
    color: '#00FF9D', opacity: 0.12,
    poly: [[0.40, 0], [0.80, 0], [0.80, 0.80], [0.40, 0.80]],
  },
];

const PHASE_META = {
  cold_start:          { color: '#5AC8FA', label: 'COLD START' },
  warm_runtime:        { color: '#8FE388', label: 'WARM' },
  stable_throughput:   { color: '#00FF9D', label: 'STABLE' },
  jvm_saturation:      { color: '#FFCC00', label: 'JVM SAT' },
  retry_amplification: { color: '#FF9500', label: 'RETRY AMP' },
  healing_saturation:  { color: '#BF5AF2', label: 'HEAL SAT' },
  cascading_collapse:  { color: '#FF453A', label: 'COLLAPSE' },
};

const NODE_COLORS = {
  Frontend: '#FF6B35',
  API:      '#00A3FF',
  Cache:    '#FFD60A',
  DB:       '#34C759',
  Queue:    '#AF52DE',
  Backend:  '#FF2D55',
};

function polyToPoints(poly) {
  return poly.map(([m, l]) => `${xScale(m)},${yScale(l)}`).join(' ');
}

export function PhaseDiagramView({ isRunning }) {
  const [state, setState] = useState(null);
  const [history, setHistory] = useState([]);

  const load = async () => {
    try {
      const { data } = await axios.get(`${API}/phase/state`, { withCredentials: true });
      setState(data);
    } catch (e) {
      console.error('PhaseDiagramView: load state', e);
    }
    try {
      const { data } = await axios.get(`${API}/phase/history?limit=20`, { withCredentials: true });
      setHistory(data.samples || []);
    } catch (e) {
      console.error('PhaseDiagramView: load history', e);
    }
  };

  useEffect(() => {
    load();
    if (!isRunning) return;
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, [isRunning]);

  // Build per-node trajectory lists from history
  const trajectories = useMemo(() => {
    const out = {};
    for (const sample of history) {
      for (const [node, p] of Object.entries(sample.per_node || {})) {
        if (!out[node]) out[node] = [];
        out[node].push({ m: p.m_ratio, l: p.l_ratio });
      }
    }
    return out;
  }, [history]);

  if (!state || !state.ready) return null;

  const perNode = state.per_node || {};
  const eutectic_l_over_l0 = state.flags?.eutectic_l_over_l0 ?? 1.5;
  const eutectic_m = state.flags?.eutectic_target?.M_ratio ?? 0.55;
  const eutX = xScale(eutectic_m);
  const eutY = yScale(eutectic_l_over_l0);

  // axis ticks
  const xTicks = [0, 0.2, 0.4, 0.55, 0.8, 1.0];
  const yTicks = [0, 0.5, 1, 2, 4, 8, 16];

  return (
    <div
      className="bg-[#1A1A1A] border border-[#BF5AF2]/40 rounded-lg p-4"
      data-testid="phase-diagram-card"
    >
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-[#BF5AF2]" />
          <h3 className="text-sm font-bold text-white">Operational Phase Diagram</h3>
          <span className="text-[10px] font-mono text-[#5A5A5E] uppercase tracking-widest">
            iron-carbide style · live
          </span>
        </div>
        <div className="text-[10px] font-mono text-[#8A8A8E]">
          Y = L/L₀ (latency ratio, √-scaled) · X = M/M_cap (memory saturation)
        </div>
      </div>

      {/* Regime overlay banners */}
      <div className="flex flex-wrap gap-2 mb-3">
        {state.retry_amplification && (
          <Banner color="#FF9500" text="Retry amplification phase — geometric position alone does not describe the regime" testid="diag-retry-amp" />
        )}
        {state.healing_saturation && (
          <Banner color="#BF5AF2" text="Healing saturation phase — synth cost-penalty boosted, cheap actions favored" testid="diag-heal-sat" />
        )}
      </div>

      <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="w-full h-auto" data-testid="phase-diagram-svg">
        {/* === phase regions === */}
        {PHASE_REGIONS.map((r) => (
          <polygon
            key={`region-${r.id}-${r.poly[0][0]}-${r.poly[0][1]}`}
            points={polyToPoints(r.poly)}
            fill={r.color}
            fillOpacity={r.opacity}
            stroke={r.color}
            strokeOpacity={0.45}
            strokeWidth={0.6}
          />
        ))}

        {/* === axes === */}
        {/* X axis line */}
        <line x1={PAD_L} y1={PAD_T + PH} x2={PAD_L + PW} y2={PAD_T + PH} stroke="#5A5A5E" strokeWidth={1} />
        {/* Y axis line */}
        <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={PAD_T + PH} stroke="#5A5A5E" strokeWidth={1} />

        {/* X ticks + labels */}
        {xTicks.map((t) => (
          <g key={`xt-${t}`}>
            <line x1={xScale(t)} y1={PAD_T + PH} x2={xScale(t)} y2={PAD_T + PH + 4} stroke="#5A5A5E" />
            <text x={xScale(t)} y={PAD_T + PH + 18} fontSize="10" fill="#8A8A8E" textAnchor="middle" fontFamily="monospace">
              {t.toFixed(2)}
            </text>
          </g>
        ))}
        {/* M_cap reference dashed at 0.80 */}
        <line
          x1={xScale(0.80)} y1={PAD_T}
          x2={xScale(0.80)} y2={PAD_T + PH}
          stroke="#FFCC00" strokeOpacity={0.35} strokeDasharray="4 3" strokeWidth={0.8}
        />
        <text x={xScale(0.80) + 4} y={PAD_T + 12} fontSize="9" fill="#FFCC00" fontFamily="monospace">
          M_cap = 0.80
        </text>

        {/* Y ticks + labels */}
        {yTicks.map((t) => (
          <g key={`yt-${t}`}>
            <line x1={PAD_L - 4} y1={yScale(t)} x2={PAD_L} y2={yScale(t)} stroke="#5A5A5E" />
            <text x={PAD_L - 8} y={yScale(t) + 3} fontSize="10" fill="#8A8A8E" textAnchor="end" fontFamily="monospace">
              {t}
            </text>
          </g>
        ))}

        {/* === phase labels in their region centroids === */}
        {[
          { id: 'cold_start',          text: 'COLD START',      x: 0.12, y: 0.25 },
          { id: 'warm_runtime',        text: 'WARM RUNTIME',    x: 0.20, y: 0.65 },
          { id: 'stable_throughput',   text: 'STABLE THROUGHPUT', x: 0.50, y: 2.0 },
          { id: 'jvm_saturation',      text: 'JVM SATURATION',  x: 0.85, y: 8.0 },
          { id: 'cascading_collapse',  text: 'CASCADING COLLAPSE', x: 0.975, y: 15, rotate: -88 },
        ].map((l) => (
          <text
            key={`label-${l.id}`}
            x={xScale(l.x)} y={yScale(l.y)}
            fontSize="11" fill="#fff" fillOpacity={0.7}
            textAnchor="middle" fontFamily="monospace" fontWeight="bold"
            transform={l.rotate ? `rotate(${l.rotate}, ${xScale(l.x)}, ${yScale(l.y)})` : undefined}
          >
            {l.text}
          </text>
        ))}

        {/* === Ψ_s eutectic point === */}
        <g data-testid="phase-eutectic-marker">
          <circle cx={eutX} cy={eutY} r={8} fill="none" stroke="#5AC8FA" strokeOpacity={0.4} strokeWidth={1} />
          <circle cx={eutX} cy={eutY} r={3} fill="#5AC8FA" />
          <text x={eutX + 10} y={eutY + 4} fontSize="11" fill="#5AC8FA" fontFamily="monospace">
            Ψ_s ({eutectic_m.toFixed(2)}, {eutectic_l_over_l0.toFixed(2)})
          </text>
        </g>

        {/* === trajectories === */}
        {Object.entries(trajectories).map(([node, pts]) => {
          if (!pts || pts.length < 2) return null;
          const color = NODE_COLORS[node] || '#fff';
          const d = pts
            .map((p, i) => `${i === 0 ? 'M' : 'L'} ${xScale(p.m)} ${yScale(p.l)}`)
            .join(' ');
          return (
            <path
              key={`traj-${node}`}
              d={d}
              fill="none"
              stroke={color}
              strokeOpacity={0.35}
              strokeWidth={1.2}
              strokeDasharray="2 2"
            />
          );
        })}

        {/* === per-service current point === */}
        {Object.entries(perNode).map(([node, p]) => {
          const color = NODE_COLORS[node] || '#fff';
          const cx = xScale(p.m_ratio);
          const cy = yScale(p.l_ratio);
          const meta = PHASE_META[p.phase] || PHASE_META.stable_throughput;
          return (
            <g key={`pt-${node}`} data-testid={`phase-diagram-node-${node}`}>
              {/* outer ring tinted by current phase */}
              <circle cx={cx} cy={cy} r={10} fill="none" stroke={meta.color} strokeOpacity={0.5} strokeWidth={1.4} />
              {/* inner dot in service color */}
              <circle cx={cx} cy={cy} r={5} fill={color} stroke="#000" strokeWidth={1} />
              <text
                x={cx + 12} y={cy - 8}
                fontSize="10.5" fill={color} fontFamily="monospace" fontWeight="bold"
              >
                {node}
              </text>
              <text
                x={cx + 12} y={cy + 5}
                fontSize="9" fill={meta.color} fontFamily="monospace"
              >
                {meta.label} · σ={p.sigma.toFixed(2)}
              </text>
            </g>
          );
        })}

        {/* === axis titles === */}
        <text x={PAD_L + PW / 2} y={VB_H - 10} fontSize="11" fill="#cfcfcf" textAnchor="middle" fontFamily="monospace">
          M / M_cap  (memory saturation, normalised)
        </text>
        <text
          x={20} y={PAD_T + PH / 2}
          fontSize="11" fill="#cfcfcf" textAnchor="middle" fontFamily="monospace"
          transform={`rotate(-90, 20, ${PAD_T + PH / 2})`}
        >
          L / L₀  (latency ratio, √-scaled)
        </text>
      </svg>

      {/* node legend */}
      <div className="flex flex-wrap gap-3 mt-2">
        {Object.entries(NODE_COLORS).map(([node, color]) => (
          <div key={node} className="flex items-center gap-1.5 text-[10px] font-mono text-[#cfcfcf]">
            <span
              className="inline-block w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: color, border: '1px solid #000' }}
            />
            {node}
          </div>
        ))}
        <div className="flex items-center gap-1.5 text-[10px] font-mono text-[#5AC8FA]">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-[#5AC8FA]" />
          Ψ_s (stable operating point)
        </div>
      </div>
    </div>
  );
}

function Banner({ color, text, testid }) {
  return (
    <div
      className="text-[10px] font-mono px-2 py-1 rounded border"
      style={{ color, borderColor: `${color}66`, backgroundColor: `${color}1A` }}
      data-testid={testid}
    >
      {text}
    </div>
  );
}

export default PhaseDiagramView;
