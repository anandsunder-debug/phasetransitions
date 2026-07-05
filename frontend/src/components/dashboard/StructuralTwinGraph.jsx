import React, { useMemo } from 'react';

const ALL_NODES = ['Frontend', 'API', 'Cache', 'Backend', 'DB', 'Queue'];
const GRAPH_EDGES = [
  ['Frontend', 'API'],
  ['API',      'Cache'],
  ['API',      'Backend'],
  ['Backend',  'DB'],
  ['Backend',  'Queue'],
  ['Cache',    'DB'],
];

// Fixed node positions in a radial layout (SVG 300×300 viewport)
const NODE_POSITIONS = {
  Frontend: { x: 150, y: 30  },
  API:      { x: 260, y: 110 },
  Cache:    { x: 260, y: 220 },
  Backend:  { x: 150, y: 270 },
  DB:       { x: 40,  y: 220 },
  Queue:    { x: 40,  y: 110 },
};

const NODE_COLORS = {
  Frontend: '#00FF9D',
  API:      '#00A3FF',
  Cache:    '#FFCC00',
  Backend:  '#A855F7',
  DB:       '#FF8C00',
  Queue:    '#FF3B30',
};

function edgeColor(k_eff_a, k_eff_b) {
  const avg = (k_eff_a + k_eff_b) / 2;
  if (avg >= 0.65) return '#00FF9D';
  if (avg >= 0.45) return '#FFCC00';
  return '#FF3B30';
}

function nodeRadius(k_eff) {
  // 12–24 px, proportional to stiffness
  return 12 + 12 * k_eff;
}

/**
 * StructuralTwinGraph — service graph with stiffness encoded visually.
 * Node size and color intensity ∝ K_eff.
 * Edge thickness ∝ harmonic mean K_eff of endpoints.
 *
 * Props:
 *   nodes — { [node]: { K_eff, sigma, epsilon, phase } }
 */
export function StructuralTwinGraph({ nodes = {} }) {
  const hasData = Object.keys(nodes).length > 0;

  const edgeData = useMemo(() => {
    if (!hasData) return [];
    return GRAPH_EDGES.map(([a, b]) => {
      const ka = nodes[a]?.K_eff ?? 0.5;
      const kb = nodes[b]?.K_eff ?? 0.5;
      const wAB = (2 * ka * kb) / (ka + kb + 1e-9);
      return { a, b, weight: wAB, color: edgeColor(ka, kb) };
    });
  }, [nodes, hasData]);

  return (
    <div
      className="bg-[#1A1A1A] border border-[#00A3FF]/30 rounded-lg p-4"
      data-testid="structural-twin-graph"
    >
      <div className="flex items-center gap-2 mb-3">
        <span className="text-[#00A3FF] text-base font-bold">⬡</span>
        <h3 className="text-sm font-bold text-white">Structural Twin Graph</h3>
        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#00A3FF]/10 text-[#00A3FF] border border-[#00A3FF]/30">
          K_eff encoded · stiffness-weighted Laplacian
        </span>
      </div>

      {!hasData ? (
        <p className="text-[#8A8A8E] text-xs">Waiting for RST data…</p>
      ) : (
        <div className="flex gap-6 flex-wrap items-start">
          {/* SVG graph */}
          <svg
            viewBox="0 0 300 300"
            className="w-full max-w-[300px] h-[300px]"
            style={{ minWidth: 200 }}
          >
            {/* Edges */}
            {edgeData.map(({ a, b, weight, color }) => {
              const pa = NODE_POSITIONS[a];
              const pb = NODE_POSITIONS[b];
              const strokeW = Math.max(1, weight * 6);
              return (
                <g key={`${a}-${b}`}>
                  <line
                    x1={pa.x} y1={pa.y}
                    x2={pb.x} y2={pb.y}
                    stroke={color}
                    strokeWidth={strokeW}
                    strokeOpacity={0.5}
                  />
                  {/* Edge weight label */}
                  <text
                    x={(pa.x + pb.x) / 2}
                    y={(pa.y + pb.y) / 2 - 4}
                    textAnchor="middle"
                    fontSize="8"
                    fill={color}
                    opacity={0.7}
                  >
                    {weight.toFixed(2)}
                  </text>
                </g>
              );
            })}

            {/* Nodes */}
            {ALL_NODES.map(nd => {
              const pos  = NODE_POSITIONS[nd];
              const data = nodes[nd] ?? {};
              const r    = nodeRadius(data.K_eff ?? 0.5);
              const col  = NODE_COLORS[nd] ?? '#8A8A8E';
              const stressed = (data.epsilon ?? 0) > 0.8;
              return (
                <g key={nd}>
                  {/* Stress ring */}
                  {stressed && (
                    <circle
                      cx={pos.x} cy={pos.y}
                      r={r + 5}
                      fill="none"
                      stroke="#FF3B30"
                      strokeWidth={2}
                      strokeDasharray="4 3"
                      opacity={0.7}
                    />
                  )}
                  <circle
                    cx={pos.x} cy={pos.y} r={r}
                    fill={col + '33'}
                    stroke={col}
                    strokeWidth={2}
                  />
                  <text
                    x={pos.x} y={pos.y - 2}
                    textAnchor="middle"
                    fontSize="9"
                    fill={col}
                    fontWeight="bold"
                  >
                    {nd}
                  </text>
                  <text
                    x={pos.x} y={pos.y + 9}
                    textAnchor="middle"
                    fontSize="8"
                    fill={col}
                    opacity={0.8}
                  >
                    {(data.K_eff ?? 0).toFixed(2)}
                  </text>
                </g>
              );
            })}
          </svg>

          {/* Legend table */}
          <div className="flex-1 min-w-[140px]">
            <p className="text-[10px] text-[#8A8A8E] mb-2">Node K_eff · σ · ε</p>
            <div className="space-y-1.5">
              {ALL_NODES.map(nd => {
                const d = nodes[nd] ?? {};
                const col = NODE_COLORS[nd] ?? '#8A8A8E';
                return (
                  <div key={nd} className="flex items-center gap-2 text-[10px]">
                    <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: col }} />
                    <span className="font-medium w-14" style={{ color: col }}>{nd}</span>
                    <span className="font-mono text-[#8A8A8E]">
                      K {(d.K_eff ?? 0).toFixed(2)}
                      {' '}σ {(d.sigma ?? 0).toFixed(2)}
                      {' '}ε {(d.epsilon ?? 0).toFixed(2)}
                    </span>
                  </div>
                );
              })}
            </div>

            <div className="mt-4 space-y-1">
              <p className="text-[10px] text-[#8A8A8E] mb-1">Edge weight = harmonic mean K_eff</p>
              {[
                { color: '#00FF9D', label: 'Stiff edge (≥ 0.65)' },
                { color: '#FFCC00', label: 'Moderate (0.45–0.64)' },
                { color: '#FF3B30', label: 'Compliant (< 0.45)' },
              ].map(({ color, label }) => (
                <div key={label} className="flex items-center gap-1.5">
                  <div className="w-4 h-0.5" style={{ backgroundColor: color }} />
                  <span className="text-[9px] text-[#8A8A8E]">{label}</span>
                </div>
              ))}
              <div className="flex items-center gap-1.5 mt-1">
                <div className="w-4 h-0.5 border-t-2 border-dashed border-[#FF3B30]" />
                <span className="text-[9px] text-[#8A8A8E]">High strain ring (ε&gt;0.8)</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
