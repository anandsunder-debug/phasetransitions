import React, { useMemo } from 'react';

export function SpectralResilienceGraph({ nodes, edges, weakEdges }) {
  const nodePositions = useMemo(() => ({
    Frontend: { x: 80, y: 50 },
    API: { x: 200, y: 50 },
    Cache: { x: 100, y: 150 },
    DB: { x: 200, y: 150 },
    Queue: { x: 300, y: 150 },
    Backend: { x: 300, y: 250 },
  }), []);

  const getNodeColor = (saturation) => {
    if (saturation > 0.7) return '#FF3B30';
    if (saturation > 0.4) return '#FFCC00';
    return '#00FF9D';
  };

  const isWeakEdge = (source, target) => {
    return weakEdges?.some(
      e => (e.source === source && e.target === target) || (e.source === target && e.target === source)
    );
  };

  return (
    <div className="w-full h-[300px] bg-[#0A0A0A] rounded border border-[#262626] p-4">
      <svg viewBox="0 0 400 300" className="w-full h-full">
        {/* Edges */}
        {edges?.map((edge, idx) => {
          const sourcePos = nodePositions[edge.source];
          const targetPos = nodePositions[edge.target];
          if (!sourcePos || !targetPos) return null;
          const isWeak = isWeakEdge(edge.source, edge.target);
          
          return (
            <line
              key={idx}
              x1={sourcePos.x}
              y1={sourcePos.y}
              x2={targetPos.x}
              y2={targetPos.y}
              stroke={isWeak ? '#FF3B30' : '#444'}
              strokeWidth={Math.max(1, edge.weight / 10)}
              strokeDasharray={isWeak ? '5,5' : 'none'}
            />
          );
        })}

        {/* Nodes */}
        {nodes?.map((node) => {
          const pos = nodePositions[node.id];
          if (!pos) return null;
          const color = getNodeColor(node.saturation);
          
          return (
            <g key={node.id} transform={`translate(${pos.x}, ${pos.y})`}>
              <circle
                r={25}
                fill={color}
                fillOpacity={0.2}
                stroke={color}
                strokeWidth={2}
                className="transition-all duration-300"
              />
              <text
                textAnchor="middle"
                dy="4"
                fill="#F5F5F5"
                fontSize="12"
                fontFamily="JetBrains Mono"
              >
                {node.id}
              </text>
            </g>
          );
        })}

        {/* Legend */}
        <g transform="translate(10, 270)">
          <circle cx={0} cy={0} r={6} fill="#00FF9D" />
          <text x={15} y={4} fill="#8A8A8E" fontSize="10">Healthy</text>
          
          <circle cx={80} cy={0} r={6} fill="#FFCC00" />
          <text x={95} y={4} fill="#8A8A8E" fontSize="10">Warning</text>
          
          <circle cx={160} cy={0} r={6} fill="#FF3B30" />
          <text x={175} y={4} fill="#8A8A8E" fontSize="10">Critical</text>
          
          <line x1={240} y1={0} x2={260} y2={0} stroke="#FF3B30" strokeWidth={2} strokeDasharray="5,5" />
          <text x={270} y={4} fill="#8A8A8E" fontSize="10">Weak Edge</text>
        </g>
      </svg>
    </div>
  );
}
