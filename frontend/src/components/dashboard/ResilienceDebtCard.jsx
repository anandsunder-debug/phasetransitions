import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Wallet, TrendingDown, TrendingUp, Sigma } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Resilience Debt Card — Phase 1 of the Unified Model.
 *
 *   E(t) = ∫₀ᵗ Φ(τ) dτ          cumulative resilience debt (energy)
 *   Cost(t) = ∫₀ᵗ 1/SRI(τ) dτ × c   operational-cost proxy (Eq. 38 of Unified-View)
 *
 * Twin live charts:
 *   • Φ(t) — instantaneous debt-rate
 *   • E(t) — D(t) INTEGRAL CURVE with shaded area-under-curve so the
 *            integration relationship is visually obvious
 */
export function ResilienceDebtCard({ isRunning }) {
  const [data, setData] = useState(null);
  const [history, setHistory] = useState([]);

  const load = useCallback(async () => {
    try {
      const [{ data: s }, { data: h }] = await Promise.all([
        axios.get(`${API}/healing/resilience-debt`, { withCredentials: true }),
        axios.get(`${API}/healing/resilience-debt/history?limit=240`, { withCredentials: true }),
      ]);
      setData(s);
      setHistory(h.samples || []);
    } catch (e) { /* silent */ }
  }, []);

  useEffect(() => {
    load();
    if (!isRunning) return;
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, [isRunning, load]);

  if (!data) {
    return (
      <div className="bg-[#121212] border border-[#262626] rounded-lg p-6" data-testid="resilience-debt-card">
        <p className="text-xs text-[#8A8A8E]">Loading resilience debt…</p>
      </div>
    );
  }

  const isRising = data.current_phi > 0.001;
  const ready = (data.samples || 0) > 0;

  return (
    <div className="bg-[#121212] border border-[#FF9F0A]/30 rounded-lg p-6" data-testid="resilience-debt-card">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h3 className="text-xs uppercase tracking-[0.2em] text-[#8A8A8E] flex items-center gap-2">
          <Wallet className="w-3 h-3 text-[#FFCC00]" />
          Resilience Debt — E(t) = ∫Φ dt
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#FF9F0A]/15 text-[#FF9F0A] border border-[#FF9F0A]/40 normal-case tracking-normal">
            Phase 1 · Unified Model
          </span>
        </h3>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-[#5A5A5E]">{ready ? `${data.samples} samples` : 'warming up…'}</span>
          {isRising
            ? <TrendingUp className="w-4 h-4 text-[#FF3B30]" />
            : <TrendingDown className="w-4 h-4 text-[#00FF9D]" />
          }
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-3">
        <div className="p-3 bg-[#1F1F1F] rounded-lg">
          <p className="text-[10px] text-[#8A8A8E] uppercase tracking-wider mb-1">Cum. Cost</p>
          <p className="text-xl font-bold font-['JetBrains_Mono'] text-[#FFCC00]" data-testid="resilience-debt-cost">
            ${data.cost_total_usd.toFixed(2)}
          </p>
          <p className="text-[10px] text-[#8A8A8E]">since boot</p>
        </div>
        <div className="p-3 bg-[#1F1F1F] rounded-lg">
          <p className="text-[10px] text-[#8A8A8E] uppercase tracking-wider mb-1">Energy ∫Φdt</p>
          <p className="text-xl font-bold font-['JetBrains_Mono'] text-[#5AC8FA]" data-testid="resilience-debt-energy">
            {data.energy_integral_phi.toFixed(4)}
          </p>
          <p className="text-[10px] text-[#8A8A8E]">imbalance·s</p>
        </div>
        <div className="p-3 bg-[#1F1F1F] rounded-lg">
          <p className="text-[10px] text-[#8A8A8E] uppercase tracking-wider mb-1">Burn rate</p>
          <p className="text-xl font-bold font-['JetBrains_Mono'] text-[#FF9500]" data-testid="resilience-debt-burn">
            ${data.instantaneous_cost_per_sec.toFixed(3)}/s
          </p>
          <p className="text-[10px] text-[#8A8A8E]">∝ 1/SRI</p>
        </div>
      </div>

      {history.length > 1 && (
        <>
          <ChartPanel
            label="Φ(t) — instantaneous debt rate"
            samples={history}
            key1="phi"
            color="#FF9F0A"
          />
          <div className="h-2" />
          <ChartPanel
            label="E(t) = ∫₀ᵗ Φ(τ)dτ — D(t) INTEGRAL CURVE"
            samples={history}
            key1="E"
            color="#FF453A"
            bold
            shadeArea
          />
        </>
      )}

      <p className="text-[10px] text-[#8A8A8E] mt-3 italic">
        Slope of E(t) IS Φ(t). A flat E(t) ⇒ system is healing as fast as it accumulates stress.
        Cost ∝ 1/SRI per Eq. 38 of the Unified-View paper.
      </p>
    </div>
  );
}

function ChartPanel({ label, samples, key1, color, bold, shadeArea }) {
  const w = 800, h = 60, pad = 4;
  const vals = samples.map((s) => s[key1] ?? 0);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const range = max - min || 1;
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * w;
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const areaPts = shadeArea ? `0,${h} ${pts} ${w},${h}` : null;
  return (
    <div className="bg-[#0F0F10] border border-[#262626] rounded p-2" data-testid={`debt-chart-${key1}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[9px] uppercase tracking-widest text-[#8A8A8E]">{label}</span>
        <span className="text-[10px] font-mono" style={{ color }}>
          {vals[vals.length - 1].toFixed(4)}
        </span>
      </div>
      <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        {areaPts && <polygon points={areaPts} fill={color} fillOpacity="0.15" />}
        <polyline points={pts} fill="none" stroke={color} strokeWidth={bold ? 2 : 1.5} />
      </svg>
      <div className="flex items-center justify-between mt-0.5 text-[9px] font-mono text-[#5A5A5E]">
        <span>min {min.toFixed(4)}</span>
        <span>max {max.toFixed(4)}</span>
      </div>
    </div>
  );
}

export default ResilienceDebtCard;
