import React from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

export function SRIDisplay({ sri, deltaSri, avgLatency }) {
  const getSriStatus = () => {
    if (sri > 0.3) return { color: 'text-[#00FF9D]', bg: 'bg-[#00FF9D]/10', label: 'Healthy', pulse: 'animate-pulse-healthy' };
    if (sri > 0.1) return { color: 'text-[#FFCC00]', bg: 'bg-[#FFCC00]/10', label: 'Warning', pulse: 'animate-pulse-warning' };
    return { color: 'text-[#FF3B30]', bg: 'bg-[#FF3B30]/10', label: 'Critical', pulse: 'animate-pulse-error' };
  };

  const status = getSriStatus();

  const getDeltaIcon = () => {
    if (deltaSri > 0.01) return <TrendingUp className="w-4 h-4 text-[#00FF9D]" />;
    if (deltaSri < -0.01) return <TrendingDown className="w-4 h-4 text-[#FF3B30]" />;
    return <Minus className="w-4 h-4 text-[#8A8A8E]" />;
  };

  return (
    <div className="grid grid-cols-3 gap-4">
      {/* SRI Value */}
      <div className={`${status.bg} border border-[#262626] rounded p-4`}>
        <div className="text-xs uppercase tracking-[0.2em] text-[#8A8A8E] mb-2">
          Spectral Resilience Index
        </div>
        <div className="flex items-baseline gap-2">
          <span className={`text-3xl font-bold font-['JetBrains_Mono'] ${status.color}`}>
            {sri.toFixed(3)}
          </span>
          <span className={`text-sm ${status.color} ${status.pulse} inline-block w-2 h-2 rounded-full ${status.color.replace('text-', 'bg-')}`} />
        </div>
        <div className={`text-sm mt-1 ${status.color}`}>{status.label}</div>
      </div>

      {/* Delta SRI */}
      <div className="bg-[#121212] border border-[#262626] rounded p-4">
        <div className="text-xs uppercase tracking-[0.2em] text-[#8A8A8E] mb-2">
          ΔSRI (Rate of Change)
        </div>
        <div className="flex items-center gap-2">
          {getDeltaIcon()}
          <span className={`text-2xl font-bold font-['JetBrains_Mono'] ${
            deltaSri > 0 ? 'text-[#00FF9D]' : deltaSri < 0 ? 'text-[#FF3B30]' : 'text-[#8A8A8E]'
          }`}>
            {deltaSri >= 0 ? '+' : ''}{deltaSri.toFixed(4)}
          </span>
        </div>
        <div className="text-sm text-[#8A8A8E] mt-1">
          {deltaSri > 0 ? 'Improving' : deltaSri < 0 ? 'Degrading' : 'Stable'}
        </div>
      </div>

      {/* Avg Latency */}
      <div className="bg-[#121212] border border-[#262626] rounded p-4">
        <div className="text-xs uppercase tracking-[0.2em] text-[#8A8A8E] mb-2">
          Average Latency
        </div>
        <div className="flex items-baseline gap-1">
          <span className="text-2xl font-bold font-['JetBrains_Mono'] text-[#FFCC00]">
            {avgLatency.toFixed(1)}
          </span>
          <span className="text-[#8A8A8E]">ms</span>
        </div>
        <div className="text-sm text-[#8A8A8E] mt-1">
          {avgLatency < 50 ? 'Optimal' : avgLatency < 100 ? 'Acceptable' : 'High'}
        </div>
      </div>
    </div>
  );
}
