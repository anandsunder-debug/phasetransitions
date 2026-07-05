import React, { useMemo } from 'react';

const COMPONENTS = ['K_A', 'K_H', 'K_S', 'K_D', 'K_F', 'K_R'];
const COMPONENT_LABELS = {
  K_A: 'Availability',
  K_H: 'Healing',
  K_S: 'Saturation',
  K_D: 'Dependency',
  K_F: 'Fault resist.',
  K_R: 'Resilience',
};

function stiffnessColor(v) {
  // Green (high stiffness) → Yellow → Red (low stiffness)
  if (v >= 0.75) return '#00FF9D';
  if (v >= 0.55) return '#7BFF9D';
  if (v >= 0.40) return '#FFCC00';
  if (v >= 0.25) return '#FF8C00';
  return '#FF3B30';
}

/**
 * RSTCompositionPanel — heatmap of 6 stiffness tensor components per service.
 *
 * Props:
 *   nodes  — { [nodeName]: { K_A, K_H, K_S, K_D, K_F, K_R, K_eff, sigma, epsilon } }
 *   nodes order follows ALL_NODES
 */
export function RSTCompositionPanel({ nodes = {} }) {
  const nodeNames = Object.keys(nodes);

  if (!nodeNames.length) {
    return (
      <div className="bg-[#1A1A1A] border border-[#333] rounded-lg p-4">
        <p className="text-[#8A8A8E] text-xs">Waiting for RST data…</p>
      </div>
    );
  }

  return (
    <div
      className="bg-[#1A1A1A] border border-[#00FF9D]/30 rounded-lg p-4"
      data-testid="rst-composition-panel"
    >
      <div className="flex items-center gap-2 mb-4">
        <span className="text-[#00FF9D] text-base font-bold">🧱</span>
        <h3 className="text-sm font-bold text-white">Stiffness Tensor Composition K</h3>
        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#00FF9D]/10 text-[#00FF9D] border border-[#00FF9D]/30">
          6-component · per node
        </span>
      </div>

      {/* Column headers: component names */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr>
              <th className="text-left text-[#8A8A8E] pr-3 pb-2 font-normal w-20">Node</th>
              {COMPONENTS.map(c => (
                <th key={c} className="text-center text-[#8A8A8E] pb-2 font-normal px-1 min-w-[54px]">
                  <span className="font-mono text-[10px]">{c}</span>
                  <br />
                  <span className="text-[9px] normal-case">{COMPONENT_LABELS[c]}</span>
                </th>
              ))}
              <th className="text-center text-[#8A8A8E] pb-2 font-mono text-[10px] font-normal px-1 min-w-[54px]">
                K_eff
              </th>
            </tr>
          </thead>
          <tbody>
            {nodeNames.map(node => {
              const d = nodes[node];
              return (
                <tr key={node} className="border-t border-[#222]">
                  <td className="py-1.5 pr-3 text-white font-medium text-[11px]">{node}</td>
                  {COMPONENTS.map(c => {
                    const val = d[c] ?? 0;
                    const color = stiffnessColor(val);
                    return (
                      <td key={c} className="py-1.5 px-1 text-center">
                        <div
                          className="inline-flex items-center justify-center rounded text-[10px] font-mono font-bold w-12 h-6"
                          style={{
                            backgroundColor: color + '22',
                            border: `1px solid ${color}55`,
                            color,
                          }}
                        >
                          {val.toFixed(2)}
                        </div>
                      </td>
                    );
                  })}
                  {/* K_eff */}
                  <td className="py-1.5 px-1 text-center">
                    <div
                      className="inline-flex items-center justify-center rounded text-[10px] font-mono font-bold w-12 h-6"
                      style={{
                        backgroundColor: stiffnessColor(d.K_eff ?? 0) + '33',
                        border: `1px solid ${stiffnessColor(d.K_eff ?? 0)}77`,
                        color: stiffnessColor(d.K_eff ?? 0),
                      }}
                    >
                      {(d.K_eff ?? 0).toFixed(3)}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="flex gap-4 mt-3 flex-wrap">
        {[
          { color: '#00FF9D', label: '≥ 0.75  Stiff' },
          { color: '#FFCC00', label: '0.40–0.74  Moderate' },
          { color: '#FF3B30', label: '< 0.40  Compliant' },
        ].map(({ color, label }) => (
          <div key={label} className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: color }} />
            <span className="text-[10px] text-[#8A8A8E]">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
