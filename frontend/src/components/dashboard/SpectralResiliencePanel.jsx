import React, { useMemo } from 'react';
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis,
  CartesianGrid, Tooltip,
} from 'recharts';

function spectralColor(rst_sri) {
  if (rst_sri >= 0.6) return '#00FF9D';
  if (rst_sri >= 0.35) return '#FFCC00';
  return '#FF3B30';
}

/**
 * SpectralResiliencePanel — shows λ2, λmax, and RST-SRI from the
 * stiffness-weighted graph Laplacian.
 *
 * Props:
 *   spectral — { lambda2, lambda_max, rst_sri }
 *   history  — array of snapshots (each has { ts, spectral: { lambda2, lambda_max, rst_sri } })
 *   limit    — max history points (default 60)
 */
export function SpectralResiliencePanel({ spectral = {}, history = [], limit = 60 }) {
  const ready = spectral.rst_sri != null;
  const color = spectralColor(spectral.rst_sri ?? 0);

  const sriHistory = useMemo(() => {
    return history.slice(-limit).map((snap, i) => ({
      t:       i,
      rst_sri: snap.spectral?.rst_sri   ?? null,
      lambda2: snap.spectral?.lambda2    ?? null,
    }));
  }, [history, limit]);

  return (
    <div
      className="bg-[#1A1A1A] border border-[#FFCC00]/30 rounded-lg p-4"
      data-testid="spectral-resilience-panel"
    >
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <span className="text-[#FFCC00] text-base font-bold">λ</span>
          <h3 className="text-sm font-bold text-white">Spectral Resilience</h3>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#FFCC00]/10 text-[#FFCC00] border border-[#FFCC00]/30">
            Stiffness Laplacian · algebraic connectivity
          </span>
        </div>
      </div>

      {!ready ? (
        <p className="text-[#8A8A8E] text-xs">Waiting for RST spectral data…</p>
      ) : (
        <>
          {/* Three big numbers */}
          <div className="grid grid-cols-3 gap-3 mb-4">
            {[
              {
                label: 'λ₂ — Algebraic connectivity',
                value: (spectral.lambda2 ?? 0).toFixed(4),
                sub:   'Fiedler value — 0 means disconnected',
                color: '#00A3FF',
              },
              {
                label: 'λmax — Spectral radius',
                value: (spectral.lambda_max ?? 0).toFixed(4),
                sub:   'Max Laplacian eigenvalue',
                color: '#A855F7',
              },
              {
                label: 'RST-SRI',
                value: (spectral.rst_sri ?? 0).toFixed(4),
                sub:   'λ₂ / λmax — structural connectivity index',
                color,
              },
            ].map(({ label, value, sub, color: c }) => (
              <div
                key={label}
                className="rounded-lg p-3 text-center"
                style={{ background: c + '11', border: `1px solid ${c}33` }}
              >
                <p className="text-[9px] text-[#8A8A8E] mb-1">{label}</p>
                <p className="text-2xl font-mono font-bold" style={{ color: c }}>{value}</p>
                <p className="text-[9px] text-[#8A8A8E] mt-1">{sub}</p>
              </div>
            ))}
          </div>

          {/* RST-SRI gauge bar */}
          <div className="mb-4">
            <div className="flex justify-between text-[10px] text-[#8A8A8E] mb-1">
              <span>RST-SRI connectivity</span>
              <span style={{ color }}>{((spectral.rst_sri ?? 0) * 100).toFixed(1)}%</span>
            </div>
            <div className="w-full bg-[#2A2A2A] rounded-full h-3 overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${Math.min(100, (spectral.rst_sri ?? 0) * 100)}%`,
                  backgroundColor: color,
                }}
              />
            </div>
            <div className="flex justify-between text-[9px] text-[#8A8A8E] mt-0.5">
              <span>Disconnected (0)</span>
              <span>Fully stiff (1)</span>
            </div>
          </div>

          {/* Trend chart */}
          {sriHistory.length > 1 && (
            <div>
              <p className="text-[10px] text-[#8A8A8E] mb-2">RST-SRI &amp; λ₂ trend</p>
              <ResponsiveContainer width="100%" height={100}>
                <AreaChart data={sriHistory} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
                  <CartesianGrid stroke="#222" strokeDasharray="3 3" />
                  <XAxis dataKey="t" hide />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 9, fill: '#8A8A8E' }} />
                  <Tooltip
                    contentStyle={{ background: '#1A1A1A', border: '1px solid #333', fontSize: 10 }}
                    formatter={(v, name) => [v?.toFixed(4), name]}
                  />
                  <Area
                    type="monotone" dataKey="rst_sri" name="RST-SRI"
                    stroke={color} fill={color + '22'} strokeWidth={2}
                    dot={false} isAnimationActive={false}
                  />
                  <Area
                    type="monotone" dataKey="lambda2" name="λ₂"
                    stroke="#00A3FF" fill="#00A3FF22" strokeWidth={1.5}
                    dot={false} isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Interpretation */}
          <div className="mt-3 p-2 rounded bg-[#111] border border-[#333] text-[10px] text-[#8A8A8E]">
            <span className="font-bold text-white">Interpretation: </span>
            {(spectral.rst_sri ?? 0) >= 0.6
              ? 'High structural connectivity — the service mesh absorbs fault propagation well.'
              : (spectral.rst_sri ?? 0) >= 0.35
              ? 'Moderate connectivity — some services are poorly coupled; targeted healing advised.'
              : 'Low connectivity — the stiffness graph is near-disconnected; cascading failure risk is elevated.'}
          </div>
        </>
      )}
    </div>
  );
}
