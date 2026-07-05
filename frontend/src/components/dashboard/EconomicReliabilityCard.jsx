import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { DollarSign, TrendingUp, ShieldCheck, Activity } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Economic Reliability Card (iter 35) — Phase 3 of the Unified Model.
 *
 * Visualizes the economic side of resilience:
 *   R_econ           = W / C_T              (Eq. 57)
 *   R_econ_resilience = W · R_S / C_T       (Eq. 58)
 *
 * with cost decomposition C_T = C_I + C_O + C_H + C_F (Eq. 51).
 *
 * Pulls from /api/economic-reliability/state and /api/economic-reliability/trend
 * (both proxied through the e-commerce gateway to obs_server on :8002).
 */
export function EconomicReliabilityCard({ isRunning }) {
  const [state, setState] = useState(null);
  const [trend, setTrend] = useState([]);

  const load = async () => {
    try {
      const [{ data: s }, { data: t }] = await Promise.all([
        axios.get(`${API}/economic-reliability/state`, { withCredentials: true }),
        axios.get(`${API}/economic-reliability/trend?limit=60`, { withCredentials: true }),
      ]);
      setState(s);
      setTrend(t.samples || []);
    } catch (e) {
      console.error('Failed to load economic reliability state:', e);
    }
  };

  useEffect(() => {
    load();
    if (!isRunning) return;
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, [isRunning]);

  if (!state) return null;

  const latest = state.latest;
  const ready = state.ready;

  return (
    <div
      className="bg-[#1A1A1A] border border-[#FFCC00]/40 rounded-lg p-4"
      data-testid="economic-reliability-card"
    >
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <DollarSign className="w-4 h-4 text-[#FFCC00]" />
          <h3 className="text-sm font-bold text-white">Economic Reliability</h3>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#FFCC00]/15 text-[#FFCC00] border border-[#FFCC00]/40">
            Phase 3 · Unified Model
          </span>
        </div>
        <span className="text-[10px] font-mono text-[#8A8A8E]">
          {ready ? `${state.history_size} samples` : 'warming up…'}
        </span>
      </div>

      {!ready || !latest ? (
        <div className="text-[11px] text-[#8A8A8E] italic py-3 text-center bg-[#0F0F10] border border-[#262626] rounded">
          Tracker initialising — first tick lands ~20s after server start
        </div>
      ) : (
        <>
          {/* Headline metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
            <Headline
              icon={<TrendingUp className="w-3 h-3" />}
              label="R_econ (W/C_T)"
              value={latest.R_econ.toFixed(3)}
              accent="#FFCC00"
              testid="econ-r-econ"
            />
            <Headline
              icon={<ShieldCheck className="w-3 h-3" />}
              label="R = W·R_S/C_T"
              value={latest.R_econ_resilience.toFixed(2)}
              accent="#00FF9D"
              testid="econ-r-econ-resilience"
            />
            <Headline
              icon={<DollarSign className="w-3 h-3" />}
              label="W (USD/min)"
              value={`$${latest.w_per_min.toFixed(2)}`}
              accent="#5AC8FA"
              testid="econ-w-per-min"
            />
            <Headline
              icon={<Activity className="w-3 h-3" />}
              label="Heal-saved /min"
              value={`$${state.counterfactual_revenue_saved_per_min.toFixed(2)}`}
              accent="#34C759"
              testid="econ-heal-saved"
            />
          </div>

          {/* Cost decomposition bar */}
          <div className="mb-3">
            <div className="text-[10px] uppercase tracking-widest text-[#8A8A8E] mb-1">
              Cost decomposition C_T = ${latest.cost_decomposition.C_T.toFixed(2)}/min
            </div>
            <CostBar parts={latest.cost_decomposition} />
            <div className="flex items-center justify-between mt-1.5 text-[10px] font-mono text-[#8A8A8E] flex-wrap gap-2">
              <LegendDot color="#5AC8FA" label={`C_I infra $${latest.cost_decomposition.C_I.toFixed(2)}`} />
              <LegendDot color="#FFCC00" label={`C_O obs $${latest.cost_decomposition.C_O.toFixed(2)}`} />
              <LegendDot color="#34C759" label={`C_H heal $${latest.cost_decomposition.C_H.toFixed(2)}`} />
              <LegendDot color="#FF453A" label={`C_F failure $${latest.cost_decomposition.C_F.toFixed(2)}`} />
            </div>
          </div>

          {/* Tiny inline trendlines */}
          {trend.length > 1 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-3">
              <SparkPanel
                label="R_econ trend"
                values={trend.map((s) => s.R_econ)}
                color="#FFCC00"
                testid="econ-trend-r-econ"
              />
              <SparkPanel
                label="W trend ($/min)"
                values={trend.map((s) => s.W)}
                color="#5AC8FA"
                testid="econ-trend-w"
              />
            </div>
          )}

          {/* Resilience ratio R_S + funnel */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px]">
            <Stat label="R_S = ΣH/Σσ" value={latest.resilience_ratio_R_S.toFixed(3)} mono />
            <Stat label="Conversion" value={`${(latest.funnel_conversion_overall * 100).toFixed(2)}%`} mono />
            <Stat label="Orders" value={latest.funnel_orders} mono />
            <Stat label="Revenue 5m" value={`$${latest.revenue_5min.toFixed(2)}`} mono accent="#34C759" />
          </div>

          <div className="mt-3 text-[10px] text-[#5A5A5E] leading-relaxed">
            R_econ = W/C_T (Eq. 57) · R = W·R_S/C_T (Eq. 58) · cost split C_I+C_O+C_H+C_F
            · counterfactual heal-saved revenue integrated over the last minute
          </div>
        </>
      )}
    </div>
  );
}

function Headline({ icon, label, value, accent, testid }) {
  return (
    <div
      className="bg-[#0F0F10] border border-[#262626] rounded p-2"
      data-testid={testid}
    >
      <div className="flex items-center gap-1 text-[9px] uppercase tracking-widest text-[#8A8A8E] mb-0.5">
        <span style={{ color: accent }}>{icon}</span>
        <span>{label}</span>
      </div>
      <div className="font-mono text-base font-bold" style={{ color: accent }}>
        {value}
      </div>
    </div>
  );
}

function CostBar({ parts }) {
  const total = (parts.C_I + parts.C_O + parts.C_H + parts.C_F) || 1e-6;
  const segs = [
    { color: '#5AC8FA', pct: (parts.C_I / total) * 100, key: 'C_I' },
    { color: '#FFCC00', pct: (parts.C_O / total) * 100, key: 'C_O' },
    { color: '#34C759', pct: (parts.C_H / total) * 100, key: 'C_H' },
    { color: '#FF453A', pct: (parts.C_F / total) * 100, key: 'C_F' },
  ];
  return (
    <div className="flex h-3 rounded overflow-hidden bg-[#0F0F10] border border-[#262626]">
      {segs.map((s) => (
        <div
          key={s.key}
          className="h-full"
          style={{ width: `${s.pct}%`, background: s.color }}
          title={`${s.key}: ${s.pct.toFixed(1)}%`}
        />
      ))}
    </div>
  );
}

function SparkPanel({ label, values, color, testid }) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const w = 240;
  const h = 40;
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - ((v - min) / range) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <div
      className="bg-[#0F0F10] border border-[#262626] rounded p-2"
      data-testid={testid}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-[9px] uppercase tracking-widest text-[#8A8A8E]">{label}</span>
        <span className="text-[10px] font-mono" style={{ color }}>
          {values[values.length - 1]?.toFixed(2)}
        </span>
      </div>
      <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" />
      </svg>
    </div>
  );
}

function LegendDot({ color, label }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="w-2 h-2 rounded-sm" style={{ background: color }} />
      {label}
    </span>
  );
}

function Stat({ label, value, mono, accent }) {
  return (
    <div className="bg-[#0F0F10] border border-[#262626] rounded p-2">
      <div className="text-[9px] uppercase tracking-widest text-[#5A5A5E] mb-0.5">{label}</div>
      <div className={`${mono ? 'font-mono' : ''} text-xs text-white`} style={accent ? { color: accent } : undefined}>
        {value ?? '—'}
      </div>
    </div>
  );
}

export default EconomicReliabilityCard;
