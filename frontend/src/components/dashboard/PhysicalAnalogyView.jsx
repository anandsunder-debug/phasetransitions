import React from 'react';

const ALL_NODES = ['Frontend', 'API', 'Cache', 'Backend', 'DB', 'Queue'];
const GRAPH_EDGES = [
  ['Frontend', 'API'],
  ['API',      'Cache'],
  ['API',      'Backend'],
  ['Backend',  'DB'],
  ['Backend',  'Queue'],
  ['Cache',    'DB'],
];

const NODE_COLORS = {
  Frontend: '#00FF9D',
  API:      '#00A3FF',
  Cache:    '#FFCC00',
  Backend:  '#A855F7',
  DB:       '#FF8C00',
  Queue:    '#FF3B30',
};

// Fixed spring layout positions (SVG 400×200)
const NODE_X = {
  Frontend: 30,
  API:      110,
  Cache:    200,
  Backend:  200,
  DB:       290,
  Queue:    290,
};
const NODE_Y = {
  Frontend: 100,
  API:      100,
  Cache:    60,
  Backend:  140,
  DB:       60,
  Queue:    140,
};

function springColor(k_eff) {
  if (k_eff >= 0.65) return '#00FF9D';
  if (k_eff >= 0.40) return '#FFCC00';
  return '#FF3B30';
}

function damperColor(epsilon) {
  if (epsilon < 0.4) return '#00A3FF';
  if (epsilon < 0.9) return '#FFCC00';
  return '#FF3B30';
}

/**
 * Draw a spring between two points using an SVG path.
 * Spring is drawn as a zigzag along the line a→b.
 */
function SpringPath({ x1, y1, x2, y2, k_eff, strokeWidth = 2 }) {
  const coils = 6;
  const color = springColor(k_eff);
  const dx = x2 - x1, dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len < 1) return null;
  // Unit vectors along and perpendicular to the spring axis
  const ux = dx / len, uy = dy / len;
  const px = -uy, py = ux;
  // Amplitude scales inversely with stiffness (stiffer = tighter coils)
  const amplitude = 6 * (1.0 - k_eff * 0.6);
  const segLen = len / (coils * 2 + 1);

  const points = [];
  for (let i = 0; i <= coils * 2; i++) {
    const t = segLen * (i + 0.5);
    const ax = x1 + ux * t;
    const ay = y1 + uy * t;
    const side = i % 2 === 0 ? 1 : -1;
    points.push(`${ax + px * amplitude * side},${ay + py * amplitude * side}`);
  }

  const d = `M${x1},${y1} L${points[0]} ` +
    points.slice(1).map(p => `L${p}`).join(' ') +
    ` L${x2},${y2}`;

  return (
    <path
      d={d}
      fill="none"
      stroke={color}
      strokeWidth={strokeWidth}
      strokeOpacity={0.8}
    />
  );
}

/**
 * Draw a dashpot (damper) symbol alongside the spring.
 * Drawn as a small box with a vertical line through it.
 */
function DamperSymbol({ x1, y1, x2, y2, epsilon }) {
  const color = damperColor(epsilon);
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
  const dx = x2 - x1, dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  const ux = dx / len, uy = dy / len;
  const px = -uy * 5, py = ux * 5;

  const bx = mx + px, by = my + py;
  const w = 8, h = 12;
  // Rotate box to align with edge direction
  const angle = Math.atan2(dy, dx) * 180 / Math.PI;

  return (
    <g transform={`translate(${bx},${by}) rotate(${angle + 90})`}>
      <rect
        x={-w / 2} y={-h / 2}
        width={w} height={h}
        fill={color + '33'} stroke={color} strokeWidth={1}
        rx={1}
      />
      {/* Fill level indicates strain */}
      <rect
        x={-w / 2 + 1} y={-h / 2 + 1 + (h - 2) * (1 - Math.min(1, epsilon / 2))}
        width={w - 2} height={(h - 2) * Math.min(1, epsilon / 2)}
        fill={color}
        opacity={0.6}
        rx={0.5}
      />
    </g>
  );
}

/**
 * PhysicalAnalogyView — renders the service mesh as a spring-damper system.
 *
 * Each service = a rigid block.
 * Each service–service edge = a spring (stiffness K_eff) in parallel with a
 *   dashpot (damping proportional to ε).
 *
 * Props:
 *   nodes — { [node]: { K_eff, epsilon, sigma } }
 */
export function PhysicalAnalogyView({ nodes = {} }) {
  const hasData = Object.keys(nodes).length > 0;

  return (
    <div
      className="bg-[#1A1A1A] border border-[#FF8C00]/30 rounded-lg p-4"
      data-testid="physical-analogy-view"
    >
      <div className="flex items-center gap-2 mb-3">
        <span className="text-[#FF8C00] text-base font-bold">⚙</span>
        <h3 className="text-sm font-bold text-white">Physical Analogy — Spring &amp; Damper System</h3>
        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#FF8C00]/10 text-[#FF8C00] border border-[#FF8C00]/30">
          K_eff → spring stiffness · ε → damper fill
        </span>
      </div>

      {!hasData ? (
        <p className="text-[#8A8A8E] text-xs">Waiting for RST data…</p>
      ) : (
        <>
          <svg
            viewBox="0 0 400 200"
            className="w-full"
            style={{ maxHeight: 220 }}
          >
            {/* Springs + dampers on edges */}
            {GRAPH_EDGES.map(([a, b]) => {
              const da = nodes[a] ?? {}, db = nodes[b] ?? {};
              const k_eff  = ((da.K_eff ?? 0.5) + (db.K_eff ?? 0.5)) / 2;
              const epsilon = ((da.epsilon ?? 0) + (db.epsilon ?? 0)) / 2;
              return (
                <g key={`${a}-${b}`}>
                  <SpringPath
                    x1={NODE_X[a]} y1={NODE_Y[a]}
                    x2={NODE_X[b]} y2={NODE_Y[b]}
                    k_eff={k_eff}
                    strokeWidth={1.5 + k_eff * 2}
                  />
                  <DamperSymbol
                    x1={NODE_X[a]} y1={NODE_Y[a]}
                    x2={NODE_X[b]} y2={NODE_Y[b]}
                    epsilon={epsilon}
                  />
                </g>
              );
            })}

            {/* Node blocks */}
            {ALL_NODES.map(nd => {
              const d = nodes[nd] ?? {};
              const col = NODE_COLORS[nd] ?? '#8A8A8E';
              const stressed = (d.epsilon ?? 0) > 0.8;
              return (
                <g key={nd}>
                  {/* Block */}
                  <rect
                    x={NODE_X[nd] - 18} y={NODE_Y[nd] - 14}
                    width={36} height={28}
                    fill={col + '22'}
                    stroke={stressed ? '#FF3B30' : col}
                    strokeWidth={stressed ? 2.5 : 1.5}
                    rx={4}
                  />
                  {/* Label */}
                  <text
                    x={NODE_X[nd]} y={NODE_Y[nd] - 2}
                    textAnchor="middle"
                    fontSize="8" fontWeight="bold"
                    fill={col}
                  >
                    {nd}
                  </text>
                  <text
                    x={NODE_X[nd]} y={NODE_Y[nd] + 8}
                    textAnchor="middle"
                    fontSize="7"
                    fill={col}
                    opacity={0.8}
                  >
                    K={( d.K_eff ?? 0).toFixed(2)}
                  </text>
                </g>
              );
            })}
          </svg>

          {/* Legend */}
          <div className="flex gap-4 mt-3 flex-wrap text-[10px] text-[#8A8A8E]">
            <div className="flex items-center gap-1.5">
              <div className="w-6 h-0.5" style={{ backgroundColor: '#00FF9D' }} />
              <span>Stiff spring (K_eff ≥ 0.65)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-6 h-0.5" style={{ backgroundColor: '#FF3B30' }} />
              <span>Compliant spring (K_eff &lt; 0.40)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-4 border border-[#00A3FF] rounded-sm bg-[#00A3FF]/20" />
              <span>Damper (fill ∝ strain ε)</span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
