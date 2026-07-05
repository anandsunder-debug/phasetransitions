import React, { useMemo } from 'react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend,
} from 'recharts';

const NODE_COLORS = {
  Frontend: '#00FF9D',
  API:      '#00A3FF',
  Cache:    '#FFCC00',
  Backend:  '#A855F7',
  DB:       '#FF8C00',
  Queue:    '#FF3B30',
};

/**
 * StressStrainPanel — per-service σ (stress) and ε (strain) curves.
 *
 * Props:
 *   nodes    — current snapshot: { [node]: { sigma, epsilon, K_eff } }
 *   history  — array of snapshots (each has { ts, nodes: { [node]: {sigma, epsilon} } })
 *   limit    — max history points to display (default 40)
 */
export function StressStrainPanel({ nodes = {}, history = [], limit = 40 }) {
  const nodeNames = Object.keys(nodes);

  // Build time-series arrays from history
  const sigmaData = useMemo(() => {
    const recent = history.slice(-limit);
    return recent.map((snap, i) => {
      const row = { t: i };
      for (const nd of nodeNames) {
        row[nd] = snap.nodes?.[nd]?.sigma ?? null;
      }
      return row;
    });
  }, [history, nodeNames, limit]);

  const epsilonData = useMemo(() => {
    const recent = history.slice(-limit);
    return recent.map((snap, i) => {
      const row = { t: i };
      for (const nd of nodeNames) {
        row[nd] = snap.nodes?.[nd]?.epsilon ?? null;
      }
      return row;
    });
  }, [history, nodeNames, limit]);

  const currentRows = nodeNames.map(nd => ({
    node: nd,
    sigma:   nodes[nd]?.sigma   ?? 0,
    epsilon: nodes[nd]?.epsilon ?? 0,
    k_eff:   nodes[nd]?.K_eff  ?? 0,
    color:   NODE_COLORS[nd] ?? '#8A8A8E',
  })).sort((a, b) => b.epsilon - a.epsilon);

  return (
    <div
      className="bg-[#1A1A1A] border border-[#A855F7]/30 rounded-lg p-4 space-y-5"
      data-testid="stress-strain-panel"
    >
      <div className="flex items-center gap-2">
        <span className="text-[#A855F7] text-base font-bold">⟂</span>
        <h3 className="text-sm font-bold text-white">Stress σ &amp; Strain ε</h3>
        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#A855F7]/10 text-[#A855F7] border border-[#A855F7]/30">
          Hooke analogy · ε = σ / K_eff
        </span>
      </div>

      {/* Current snapshot table */}
      <div>
        <p className="text-[10px] text-[#8A8A8E] mb-2">Current snapshot (ranked by ε)</p>
        <div className="space-y-1">
          {currentRows.map(({ node, sigma, epsilon, k_eff, color }) => (
            <div key={node} className="flex items-center gap-2 text-xs">
              <span className="w-16 font-medium" style={{ color }}>{node}</span>
              {/* Sigma bar */}
              <div className="flex-1 flex items-center gap-1">
                <span className="text-[#8A8A8E] w-5 text-right font-mono text-[10px]">σ</span>
                <div className="flex-1 bg-[#2A2A2A] rounded-full h-2 overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.min(100, sigma * 100).toFixed(1)}%`,
                      backgroundColor: color,
                      opacity: 0.8,
                    }}
                  />
                </div>
                <span className="font-mono text-[10px] w-10 text-right" style={{ color }}>
                  {sigma.toFixed(3)}
                </span>
              </div>
              {/* Epsilon bar */}
              <div className="flex-1 flex items-center gap-1">
                <span className="text-[#8A8A8E] w-4 text-right font-mono text-[10px]">ε</span>
                <div className="flex-1 bg-[#2A2A2A] rounded-full h-2 overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.min(100, (epsilon / 5) * 100).toFixed(1)}%`,
                      backgroundColor: epsilon > 1.5 ? '#FF3B30' : epsilon > 0.8 ? '#FFCC00' : color,
                      opacity: 0.8,
                    }}
                  />
                </div>
                <span
                  className="font-mono text-[10px] w-10 text-right"
                  style={{ color: epsilon > 1.5 ? '#FF3B30' : epsilon > 0.8 ? '#FFCC00' : color }}
                >
                  {epsilon.toFixed(3)}
                </span>
              </div>
              <span className="text-[#8A8A8E] text-[10px] font-mono w-16 text-right">
                K_eff {k_eff.toFixed(3)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Sigma trend */}
      {sigmaData.length > 1 && (
        <div>
          <p className="text-[10px] text-[#8A8A8E] mb-2">σ trajectory (operational stress)</p>
          <ResponsiveContainer width="100%" height={110}>
            <LineChart data={sigmaData} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
              <CartesianGrid stroke="#222" strokeDasharray="3 3" />
              <XAxis dataKey="t" hide />
              <YAxis domain={[0, 1]} tick={{ fontSize: 9, fill: '#8A8A8E' }} />
              <Tooltip
                contentStyle={{ background: '#1A1A1A', border: '1px solid #333', fontSize: 10 }}
                formatter={(v, name) => [v?.toFixed(3), name]}
              />
              {nodeNames.map(nd => (
                <Line
                  key={nd}
                  type="monotone"
                  dataKey={nd}
                  stroke={NODE_COLORS[nd] ?? '#8A8A8E'}
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Epsilon trend */}
      {epsilonData.length > 1 && (
        <div>
          <p className="text-[10px] text-[#8A8A8E] mb-2">ε trajectory (structural strain)</p>
          <ResponsiveContainer width="100%" height={110}>
            <LineChart data={epsilonData} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
              <CartesianGrid stroke="#222" strokeDasharray="3 3" />
              <XAxis dataKey="t" hide />
              <YAxis domain={[0, 'auto']} tick={{ fontSize: 9, fill: '#8A8A8E' }} />
              <Tooltip
                contentStyle={{ background: '#1A1A1A', border: '1px solid #333', fontSize: 10 }}
                formatter={(v, name) => [v?.toFixed(3), name]}
              />
              {nodeNames.map(nd => (
                <Line
                  key={nd}
                  type="monotone"
                  dataKey={nd}
                  stroke={NODE_COLORS[nd] ?? '#8A8A8E'}
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
