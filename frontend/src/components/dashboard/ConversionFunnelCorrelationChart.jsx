import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Legend } from 'recharts';
import { TrendingUp, TrendingDown, Activity } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Live SRI ↔ Conversion correlation chart. Demonstrates the central thesis
 * of the SRI papers: as infrastructure resilience improves, conversion
 * follows. Annotates each healing action so users can see the cause-effect
 * directly on the chart.
 */
export function ConversionFunnelCorrelationChart({ isRunning }) {
  const [data, setData] = useState(null);
  const [windowSec, setWindowSec] = useState(300); // 5 min default

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const { data } = await axios.get(`${API}/metrics/correlation`, {
          params: { window_seconds: windowSec },
          withCredentials: true,
        });
        if (!cancelled) setData(data);
      } catch (e) { /* silent */ }
    };
    load();
    if (!isRunning) return;
    const iv = setInterval(load, 4000);
    return () => { cancelled = true; clearInterval(iv); };
  }, [isRunning, windowSec]);

  const chartData = useMemo(() => {
    if (!data?.series) return [];
    return data.series.map(s => ({
      t: s.t,                          // negative seconds (relative to now)
      tLabel: `${s.t.toFixed(0)}s`,
      sri: s.sri,
      conversion: s.conversion * 100,  // % for readability
    }));
  }, [data]);

  const r = data?.pearson_r;
  const rColor = r === null || r === undefined ? '#8A8A8E' :
                 r > 0.5 ? '#00FF9D' :
                 r > 0.2 ? '#FFCC00' : '#FF3B30';

  return (
    <div className="bg-[#121212] border border-[#262626] rounded-lg p-6" data-testid="conv-correlation-chart">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-xs uppercase tracking-[0.2em] text-[#8A8A8E] flex items-center gap-2">
            <Activity className="w-3 h-3 text-[#5AC8FA]" />
            SRI ↔ Conversion Funnel — Live Correlation
          </h3>
          <p className="text-[10px] text-[#8A8A8E] mt-1">
            Watch resilience improvements translate into business outcomes.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-[#8A8A8E]">Window:</span>
          {[
            { v: 300, label: '5m' },
            { v: 1800, label: '30m' },
          ].map(opt => (
            <button
              key={opt.v}
              onClick={() => setWindowSec(opt.v)}
              className={`text-[10px] px-2 py-1 rounded border ${
                windowSec === opt.v
                  ? 'bg-[#5AC8FA]/20 border-[#5AC8FA] text-[#5AC8FA]'
                  : 'bg-[#1F1F1F] border-[#262626] text-[#8A8A8E] hover:bg-[#2A2A2A]'
              }`}
              data-testid={`conv-window-${opt.v}`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="p-3 bg-[#1F1F1F] rounded-lg">
          <p className="text-[10px] text-[#8A8A8E] uppercase tracking-wider mb-1">Pearson r</p>
          <p className="text-xl font-bold font-['JetBrains_Mono']" style={{ color: rColor }} data-testid="conv-pearson-r">
            {r === null || r === undefined ? '—' : r.toFixed(3)}
          </p>
          <p className="text-[10px] text-[#8A8A8E]">SRI ↔ conversion</p>
        </div>
        <div className="p-3 bg-[#1F1F1F] rounded-lg">
          <p className="text-[10px] text-[#8A8A8E] uppercase tracking-wider mb-1">SRI range</p>
          <p className="text-xl font-bold font-['JetBrains_Mono'] text-[#00FF9D]">
            {data?.current?.sri_min?.toFixed(2) || '—'} → {data?.current?.sri_max?.toFixed(2) || '—'}
          </p>
          <p className="text-[10px] text-[#8A8A8E]">window min/max</p>
        </div>
        <div className="p-3 bg-[#1F1F1F] rounded-lg">
          <p className="text-[10px] text-[#8A8A8E] uppercase tracking-wider mb-1">Conversion</p>
          <p className="text-xl font-bold font-['JetBrains_Mono'] text-[#FFCC00]">
            {data?.current?.conversion_min ? (data.current.conversion_min * 100).toFixed(2) : '—'}% → {data?.current?.conversion_max ? (data.current.conversion_max * 100).toFixed(2) : '—'}%
          </p>
          <p className="text-[10px] text-[#8A8A8E]">window range</p>
        </div>
      </div>

      <div style={{ width: '100%', height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
            <XAxis dataKey="tLabel" stroke="#8A8A8E" fontSize={10} />
            <YAxis yAxisId="left" stroke="#00FF9D" fontSize={10} domain={[0, 1]} />
            <YAxis yAxisId="right" orientation="right" stroke="#FFCC00" fontSize={10} />
            <Tooltip
              contentStyle={{ backgroundColor: '#0F0F0F', border: '1px solid #262626', fontSize: 11 }}
              labelStyle={{ color: '#FFFFFF' }}
            />
            <Legend wrapperStyle={{ fontSize: 10 }} />
            <Line yAxisId="left" type="monotone" dataKey="sri" name="SRI" stroke="#00FF9D" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line yAxisId="right" type="monotone" dataKey="conversion" name="Conversion %" stroke="#FFCC00" strokeWidth={2} dot={false} isAnimationActive={false} />
            {/* Healing-action annotations */}
            {data?.annotations?.filter(a => typeof a?.t_relative === 'number').slice(-6).map((a, i) => (
              <ReferenceLine
                key={i}
                yAxisId="left"
                x={`${a.t_relative.toFixed(0)}s`}
                stroke="#00A3FF"
                strokeDasharray="3 3"
                label={{ value: '⚡', position: 'top', fill: '#00A3FF', fontSize: 12 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {data?.annotations && data.annotations.length > 0 && (
        <div className="mt-3 max-h-24 overflow-y-auto" data-testid="conv-annotations-list">
          <p className="text-[10px] text-[#8A8A8E] uppercase tracking-wider mb-1">Recent healing actions in window</p>
          <div className="space-y-1">
            {data.annotations.slice(-5).reverse().map((a, i) => {
              const positive = (a.sri_delta || 0) > 0;
              const tRel = typeof a.t_relative === 'number' ? a.t_relative : 0;
              const delta = typeof a.sri_delta === 'number' ? a.sri_delta : 0;
              return (
                <div key={i} className="flex items-center gap-2 text-[10px] font-mono">
                  <span className="text-[#00A3FF]">⚡ {tRel.toFixed(0)}s</span>
                  <span className="text-[#FFFFFF]">{a.action_id}</span>
                  <span className="text-[#8A8A8E]">@ {a.target_node || '-'}</span>
                  <span className={positive ? 'text-[#00FF9D]' : 'text-[#FF3B30]'}>
                    {positive ? <TrendingUp className="w-3 h-3 inline" /> : <TrendingDown className="w-3 h-3 inline" />}
                    SRI {delta >= 0 ? '+' : ''}{delta.toFixed(4)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <p className="text-[10px] text-[#8A8A8E] mt-3 italic" data-testid="conv-interpretation">
        {data?.interpretation || 'Loading correlation analysis…'}
      </p>
    </div>
  );
}
