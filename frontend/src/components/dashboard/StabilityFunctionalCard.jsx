import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Activity, TrendingDown, TrendingUp, Minus } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Stability Functional Ψ (iter 42) — Phase 2 of the Unified Model.
 *
 *   Ψ(t) = α·⟨d_n²⟩ + β·D_accum + γ·variance(d_n)
 *   dΨ/dt < 0  ⇒ stabilising      → Ψ_s
 *   dΨ/dt ≈ 0  ⇒ steady
 *   dΨ/dt > 0  ⇒ destabilising    ← Ψ_s
 *
 * Read-only: Ψ measures stability; it doesn't act. The iter 41 unified
 * eutectic-distance objective is what drives the system *toward* low Ψ.
 */
export function StabilityFunctionalCard({ isRunning }) {
  const [state, setState] = useState(null);
  const [trend, setTrend] = useState([]);

  const load = useCallback(async () => {
    try {
      const [{ data: s }, { data: t }] = await Promise.all([
        axios.get(`${API}/stability/state`, { withCredentials: true }),
        axios.get(`${API}/stability/trend?limit=60`, { withCredentials: true }),
      ]);
      setState(s);
      setTrend(t.samples || []);
    } catch (e) { /* silent */ }
  }, []);

  useEffect(() => {
    load();
    if (!isRunning) return;
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, [isRunning, load]);

  if (!state) return null;
  const ready = state.ready;
  const latest = state.latest;

  return (
    <div
      className="bg-[#1A1A1A] border border-[#7B61FF]/40 rounded-lg p-4"
      data-testid="stability-functional-card"
    >
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-[#7B61FF]" />
          <h3 className="text-sm font-bold text-white">Stability Functional Ψ</h3>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#7B61FF]/15 text-[#7B61FF] border border-[#7B61FF]/40">
            Phase 2 · Unified Model
          </span>
        </div>
        <span className="text-[10px] font-mono text-[#8A8A8E]">
          {ready ? `${state.history_size} samples` : 'warming up…'}
        </span>
      </div>

      {!ready || !latest ? (
        <div className="text-[11px] text-[#8A8A8E] italic py-3 text-center bg-[#0F0F10] border border-[#262626] rounded">
          Lyapunov functional initialising — first tick lands ~15s after phase classifier ready
        </div>
      ) : (
        <>
          {/* Headline */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
            <Tile
              label="Ψ (current)"
              value={latest.psi.toFixed(4)}
              accent="#7B61FF"
              testid="psi-value"
            />
            <Tile
              label="dΨ/dt"
              value={`${latest.psi_dot >= 0 ? '+' : ''}${latest.psi_dot.toExponential(2)}`}
              accent={latest.psi_dot < -state.thresholds.stabilising_below
                ? '#34C759'
                : latest.psi_dot > state.thresholds.destabilising_above
                ? '#FF453A'
                : '#FFCC00'}
              testid="psi-dot-value"
            />
            <Tile
              label="Ψ min (5m)"
              value={state.psi_min_5m.toFixed(4)}
              accent="#34C759"
            />
            <Tile
              label="Ψ max (5m)"
              value={state.psi_max_5m.toFixed(4)}
              accent="#FF9F0A"
            />
          </div>

          {/* Classification banner */}
          <ClassificationBanner classification={latest.classification} psi_dot={latest.psi_dot} />

          {/* Decomposition */}
          <div className="mt-3 mb-3">
            <div className="text-[10px] uppercase tracking-widest text-[#8A8A8E] mb-1">
              Ψ decomposition
            </div>
            <div className="grid grid-cols-3 gap-2 text-[11px]">
              <Component
                label={`α·⟨d²⟩`}
                value={(state.weights.alpha_quadratic_dev * latest.d2_mean).toFixed(4)}
                weight={state.weights.alpha_quadratic_dev}
                color="#7B61FF"
              />
              <Component
                label={`β·D_accum`}
                value={(state.weights.beta_debt * latest.debt).toFixed(4)}
                weight={state.weights.beta_debt}
                color="#5AC8FA"
              />
              <Component
                label={`γ·Var(d)`}
                value={(state.weights.gamma_dispersion * latest.d2_var).toFixed(4)}
                weight={state.weights.gamma_dispersion}
                color="#FFCC00"
              />
            </div>
          </div>

          {/* Ψ trend sparkline */}
          {trend.length > 1 && (
            <div className="mb-3">
              <div className="text-[10px] uppercase tracking-widest text-[#8A8A8E] mb-1">
                Ψ trajectory (last {trend.length} samples)
              </div>
              <Sparkline samples={trend} />
            </div>
          )}

          {/* Per-node d_n */}
          <div className="grid grid-cols-3 md:grid-cols-6 gap-1 text-[10px]">
            {Object.entries(latest.per_node).map(([node, d]) => (
              <div
                key={node}
                className="bg-[#0F0F10] border border-[#262626] rounded px-2 py-1"
                title={`d_n(${node}) = ${d}`}
              >
                <div className="text-[8px] uppercase tracking-widest text-[#5A5A5E]">{node}</div>
                <div className="font-mono" style={{ color: d > 0.40 ? '#FF453A' : d > 0.20 ? '#FFCC00' : '#34C759' }}>
                  d={d.toFixed(3)}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-3 text-[10px] text-[#5A5A5E] leading-relaxed">
            Ψ = α·⟨d_n²⟩ + β·D_accum + γ·Var(d_n) · Lyapunov-style scalar over the phase-space
            (L̂, Q, M, E) · dΨ/dt &lt; 0 ⇒ system is pulling toward Ψ_s
          </div>
        </>
      )}
    </div>
  );
}

function Tile({ label, value, accent, testid }) {
  return (
    <div className="bg-[#0F0F10] border border-[#262626] rounded p-2" data-testid={testid}>
      <div className="text-[9px] uppercase tracking-widest text-[#8A8A8E] mb-0.5">{label}</div>
      <div className="font-mono text-base font-bold" style={{ color: accent }}>{value}</div>
    </div>
  );
}

function Component({ label, value, weight, color }) {
  return (
    <div className="bg-[#0F0F10] border border-[#262626] rounded p-2">
      <div className="flex items-center justify-between text-[9px] mb-0.5">
        <span className="uppercase tracking-widest text-[#8A8A8E]">{label}</span>
        <span className="font-mono text-[#5A5A5E]">w={weight}</span>
      </div>
      <div className="font-mono text-xs" style={{ color }}>{value}</div>
    </div>
  );
}

function ClassificationBanner({ classification, psi_dot }) {
  const cls = classification === 'stabilising'
    ? { color: '#34C759', icon: TrendingDown, label: 'STABILISING — system pulling toward Ψ_s' }
    : classification === 'destabilising'
    ? { color: '#FF453A', icon: TrendingUp,   label: 'DESTABILISING — system drifting from Ψ_s' }
    : { color: '#FFCC00', icon: Minus,        label: 'STEADY — Ψ neither rising nor falling' };
  const Icon = cls.icon;
  return (
    <div
      className="flex items-center gap-2 px-3 py-1.5 rounded border"
      style={{ borderColor: `${cls.color}80`, background: `${cls.color}15` }}
      data-testid={`psi-classification-${classification}`}
    >
      <Icon className="w-4 h-4" style={{ color: cls.color }} />
      <span className="text-[11px] font-mono" style={{ color: cls.color }}>
        {cls.label}
      </span>
      <span className="ml-auto text-[10px] font-mono text-[#8A8A8E]">
        dΨ/dt = {psi_dot.toExponential(2)}
      </span>
    </div>
  );
}

function Sparkline({ samples }) {
  const w = 600, h = 50;
  const vals = samples.map((s) => s.psi);
  const min = Math.min(...vals), max = Math.max(...vals);
  const range = max - min || 1;
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * w;
    const y = h - ((v - min) / range) * (h - 4) - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  // Color last segment by classification
  const lastCls = samples[samples.length - 1]?.cls || 'steady';
  const stroke = lastCls === 'stabilising' ? '#34C759'
    : lastCls === 'destabilising' ? '#FF453A'
    : '#7B61FF';
  return (
    <div className="bg-[#0F0F10] border border-[#262626] rounded p-1.5">
      <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        <polyline points={pts} fill="none" stroke={stroke} strokeWidth="1.5" />
      </svg>
      <div className="flex items-center justify-between mt-0.5 text-[9px] font-mono text-[#5A5A5E]">
        <span>min {min.toFixed(4)}</span>
        <span>now {vals[vals.length - 1].toFixed(4)}</span>
        <span>max {max.toFixed(4)}</span>
      </div>
    </div>
  );
}

export default StabilityFunctionalCard;
