import React from 'react';

export function MetricsPanel({ nodes }) {
  if (!nodes || nodes.length === 0) {
    return (
      <div className="text-[#8A8A8E] text-center py-4">
        No metrics data available
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm font-['JetBrains_Mono']">
        <thead>
          <tr className="border-b border-[#262626]">
            <th className="text-left py-2 px-3 text-[#8A8A8E] font-medium">Node</th>
            <th className="text-right py-2 px-3 text-[#8A8A8E] font-medium">Traffic</th>
            <th className="text-right py-2 px-3 text-[#8A8A8E] font-medium">Latency</th>
            <th className="text-right py-2 px-3 text-[#8A8A8E] font-medium">Error</th>
            <th className="text-right py-2 px-3 text-[#8A8A8E] font-medium">Saturation</th>
          </tr>
        </thead>
        <tbody>
          {nodes.map((node) => (
            <tr key={node.id} className="border-b border-[#262626]/50 hover:bg-[#1F1F1F]">
              <td className="py-2 px-3 text-[#F5F5F5] font-medium">{node.id}</td>
              <td className="py-2 px-3 text-right text-[#00FF9D]">{node.traffic.toFixed(0)}</td>
              <td className="py-2 px-3 text-right text-[#FFCC00]">{node.latency.toFixed(1)}ms</td>
              <td className="py-2 px-3 text-right">
                <span className={node.error > 0.1 ? 'text-[#FF3B30]' : 'text-[#8A8A8E]'}>
                  {(node.error * 100).toFixed(1)}%
                </span>
              </td>
              <td className="py-2 px-3 text-right">
                <div className="flex items-center justify-end gap-2">
                  <div className="w-16 h-2 bg-[#262626] rounded-full overflow-hidden">
                    <div 
                      className={`h-full rounded-full transition-all ${
                        node.saturation > 0.7 ? 'bg-[#FF3B30]' : 
                        node.saturation > 0.4 ? 'bg-[#FFCC00]' : 'bg-[#00FF9D]'
                      }`}
                      style={{ width: `${node.saturation * 100}%` }}
                    />
                  </div>
                  <span className="text-[#8A8A8E] w-10 text-right">{(node.saturation * 100).toFixed(0)}%</span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
