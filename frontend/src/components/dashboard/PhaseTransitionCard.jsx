import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { AlertTriangle, Activity, Target } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Operational Phase Transition Card (iter 31)
 *
 * Surfaces per-service operational phase classification, composite σ,
 * eutectic-distance, and the cross-system retry-amplification +
 * healing-saturation flags that gate AggressiveHealingMode and the
 * LadderSynthesizer cost penalty.
 */

const PHASE_META = {
  cold_start:          { color: '#5AC8FA', bg: 'rgba(90,200,250,0.10)',  label: 'COLD START' },
  warm_runtime:        { color: '#8FE388', bg: 'rgba(143,227,136,0.10)', label: 'WARM' },
  stable_throughput:   { color: '#00FF9D', bg: 'rgba(0,255,157,0.10)',   label: 'STABLE' },
  jvm_saturation:      { color: '#FFCC00', bg: 'rgba(255,204,0,0.10)',   label: 'JVM SAT' },
  retry_amplification: { color: '#FF9500', bg: 'rgba(255,149,0,0.15)',   label: 'RETRY AMP' },
  healing_saturation:  { color: '#BF5AF2', bg: 'rgba(191,90,242,0.15)',  label: 'HEAL SAT' },
  cascading_collapse:  { color: '#FF453A', bg: 'rgba(255,69,58,0.18)',   label: 'COLLAPSE' },
  unknown:             { color: '#8A8A8E', bg: 'rgba(138,138,142,0.10)', label: '—' },
};

export function PhaseTransitionCard({ isRunning }) {
  const [state, setState] = useState(null);
  const [history, setHistory] = useState([]);

  const load = async () => {
    try {
      const { data } = await axios.get(`${API}/phase/state`, { withCredentials: true });
      setState(data);
    } catch (e) {
      console.error('Failed to load phase state:', e);
    }
    try {
      const { data } = await axios.get(`${API}/phase/history?limit=30`, { withCredentials: true });
      setHistory(data.samples || []);
    } catch (e) {
      console.error('Failed to load phase history:', e);
    }
  };

  useEffect(() => {
    load();
    if (!isRunning) return;
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, [isRunning]);

  if (!state || !state.ready) return null;

  const perNode = state.per_node || {};
  const eutectic = state.flags?.eutectic_target || {};

  // sigma over time — sparkline
  const sparkPoints = history.map((s, i) => ({ i, sigma: s.composite_sigma }));
  const sparkMax = Math.max(0.01, ...sparkPoints.map(p => p.sigma));

  return (
    <div
      className="bg-[#1A1A1A] border border-[#BF5AF2]/40 rounded-lg p-4"
      data-testid="phase-transition-card"
    >
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-[#BF5AF2]" />
          <h3 className="text-sm font-bold text-white">Operational Phase Transition</h3>
          <span
            className="text-[10px] font-mono px-2 py-0.5 rounded border"
            style={{
              color: PHASE_META[state.worst_phase]?.color,
              backgroundColor: PHASE_META[state.worst_phase]?.bg,
              borderColor: `${PHASE_META[state.worst_phase]?.color}66`,
            }}
            data-testid="phase-system-worst"
          >
            {PHASE_META[state.worst_phase]?.label || state.worst_phase}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Stat label="σ (composite stress)" value={state.composite_sigma.toFixed(3)} testid="phase-composite-sigma" />
          <Stat label="Ψ_s dist" value={state.eutectic_distance.toFixed(3)} testid="phase-eutectic-distance" accent="#5AC8FA" />
        </div>
      </div>

      {/* Cross-system flags */}
      <div className="flex flex-wrap gap-2 mb-3">
        {state.retry_amplification && (
          <FlagBanner
            color="#FF9500"
            icon={<AlertTriangle className="w-3 h-3" />}
            text="Retry amplification — Aggressive healing braked (would worsen σ)"
            testid="phase-flag-retry-amp"
          />
        )}
        {state.healing_saturation && (
          <FlagBanner
            color="#BF5AF2"
            icon={<AlertTriangle className="w-3 h-3" />}
            text={`Healing saturation — synthesizer cost-penalty ×${state.synth_cost_penalty_boost.toFixed(1)} (favoring cheap actions)`}
            testid="phase-flag-heal-sat"
          />
        )}
        {state.aggressive_braked && !state.retry_amplification && (
          <FlagBanner
            color="#FF9500"
            icon={<AlertTriangle className="w-3 h-3" />}
            text="Aggressive healing braked"
            testid="phase-flag-aggressive-braked"
          />
        )}
        {!state.retry_amplification && !state.healing_saturation && !state.aggressive_braked && (
          <FlagBanner
            color="#00FF9D"
            icon={<Target className="w-3 h-3" />}
            text={`Operating ${state.eutectic_distance < 0.2 ? 'near' : 'away from'} eutectic point Ψ_s`}
            testid="phase-flag-healthy"
          />
        )}
      </div>

      {/* Per-node phase chips */}
      <div className="space-y-1.5 mb-3">
        <div className="text-[10px] uppercase tracking-widest text-[#8A8A8E]">Per-Service Phase</div>
        {Object.entries(perNode).map(([node, p]) => {
          const meta = PHASE_META[p.phase] || PHASE_META.unknown;
          // (L/L_0, M/M_cap) → mini 2D position visual
          const lFrac = Math.min(1, p.l_ratio / 20);  // clamp L/L_0 viz at 20
          const mFrac = Math.min(1, p.m_ratio);
          return (
            <div
              key={node}
              className="flex items-center gap-2 bg-[#0F0F10] border border-[#262626] rounded p-2"
              data-testid={`phase-node-${node}`}
            >
              <span className="text-xs text-white w-20 font-bold">{node}</span>
              <span
                className="text-[10px] font-mono px-2 py-0.5 rounded border w-24 text-center"
                style={{ color: meta.color, backgroundColor: meta.bg, borderColor: `${meta.color}66` }}
              >
                {meta.label}
              </span>
              <span className="text-[10px] font-mono text-[#8A8A8E] w-20">σ={p.sigma.toFixed(3)}</span>
              <span className="text-[10px] font-mono text-[#8A8A8E] w-24">L/L₀={p.l_ratio.toFixed(2)}</span>
              <span className="text-[10px] font-mono text-[#8A8A8E] w-24">M/M_cap={p.m_ratio.toFixed(2)}</span>
              {/* 2D mini phase-space dot */}
              <div className="relative w-12 h-6 bg-[#181818] rounded border border-[#262626] ml-auto">
                <div
                  className="absolute w-1.5 h-1.5 rounded-full"
                  style={{
                    left: `${lFrac * 100}%`, bottom: `${mFrac * 100}%`,
                    transform: 'translate(-50%, 50%)',
                    backgroundColor: meta.color,
                    boxShadow: `0 0 4px ${meta.color}`,
                  }}
                />
                {/* Ψ_s reference marker */}
                <div
                  className="absolute w-1 h-1 bg-[#5AC8FA] opacity-50"
                  style={{
                    left: `${(eutectic.L_ratio || 0.5) * 50}%`,
                    bottom: `${(eutectic.M_ratio || 0.55) * 100}%`,
                    transform: 'translate(-50%, 50%)',
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* σ sparkline */}
      {sparkPoints.length > 1 && (
        <div className="mt-2">
          <div className="text-[10px] uppercase tracking-widest text-[#8A8A8E] mb-1">σ trajectory (last {sparkPoints.length})</div>
          <svg viewBox={`0 0 ${sparkPoints.length} 30`} className="w-full h-8" preserveAspectRatio="none" data-testid="phase-sigma-sparkline">
            <polyline
              fill="none"
              stroke="#BF5AF2"
              strokeWidth="0.8"
              points={sparkPoints.map((p) => `${p.i},${30 - (p.sigma / sparkMax) * 28}`).join(' ')}
            />
          </svg>
        </div>
      )}

      <div className="mt-3 text-[10px] text-[#5A5A5E] leading-relaxed font-mono">
        σ = αL + βQ + γM + δE
        &nbsp;·&nbsp; α={state.flags?.weights?.alpha_L} &nbsp;
        β={state.flags?.weights?.beta_Q} &nbsp;
        γ={state.flags?.weights?.gamma_M} &nbsp;
        δ={state.flags?.weights?.delta_E}
        &nbsp;·&nbsp; M_cap threshold = {state.flags?.m_cap_threshold}
      </div>
    </div>
  );
}

function FlagBanner({ color, icon, text, testid }) {
  return (
    <div
      className="text-[10px] font-mono px-2 py-1 rounded border flex items-center gap-1.5"
      style={{ color, borderColor: `${color}66`, backgroundColor: `${color}1A` }}
      data-testid={testid}
    >
      {icon}
      {text}
    </div>
  );
}

function Stat({ label, value, testid, accent }) {
  return (
    <div className="bg-[#0F0F10] border border-[#262626] rounded p-2" data-testid={testid}>
      <div className="text-[9px] uppercase tracking-widest text-[#5A5A5E] mb-0.5">{label}</div>
      <div className="text-xs font-mono text-white" style={accent ? { color: accent } : undefined}>{value}</div>
    </div>
  );
}

export default PhaseTransitionCard;
