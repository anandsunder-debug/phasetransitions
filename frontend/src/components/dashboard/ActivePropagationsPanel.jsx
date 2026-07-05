import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Radar, Wand2, Play, Activity, Zap } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Live panel showing auto-detected failure propagations + the optimized
 * healing sequence the system would (or did) run along the propagation path.
 */
export function ActivePropagationsPanel({ isRunning }) {
  const [data, setData] = useState(null);
  const [executing, setExecuting] = useState(false);

  const load = async () => {
    try {
      const { data } = await axios.get(`${API}/healing/active-propagations`, { withCredentials: true });
      setData(data);
    } catch (e) { /* silent */ }
  };

  useEffect(() => {
    load();
    if (!isRunning) return;
    const iv = setInterval(load, 4000);
    return () => clearInterval(iv);
  }, [isRunning]);

  const toggleEnable = async (key, value) => {
    try {
      const { data } = await axios.post(`${API}/healing/auto-propagation/config`, { [key]: value }, { withCredentials: true });
      setData(data);
      toast.success(`${key} ${value ? 'enabled' : 'disabled'}`);
    } catch (e) {
      toast.error('Config update failed');
    }
  };

  const executeSequence = async (sequence) => {
    if (!sequence || sequence.length === 0) return;
    setExecuting(true);
    try {
      const { data } = await axios.post(`${API}/healing/execute-sequence`, { sequence, delay_ms: 800 }, { withCredentials: true });
      const cooldownSkipped = (data.results || []).filter(r => r.reason === 'cooldown');
      if (data.executed_count === 0 && cooldownSkipped.length > 0) {
        const cdLine = cooldownSkipped.map(r => `${r.step?.action_id} ${r.cooldown_remaining_seconds?.toFixed(0)}s`).join(', ');
        toast.warning(`Skipped ${cooldownSkipped.length} (cooling down: ${cdLine})`, { duration: 4000 });
      } else {
        const skippedNote = cooldownSkipped.length > 0 ? ` • ${cooldownSkipped.length} on cooldown` : '';
        toast.success(`Executed ${data.executed_count}/${sequence.length}${skippedNote} • Δ SRI ${data.cumulative_sri_delta >= 0 ? '+' : ''}${data.cumulative_sri_delta}`);
      }
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Execute failed');
    } finally {
      setExecuting(false);
    }
  };

  if (!data) {
    return (
      <div className="bg-[#121212] border border-[#262626] rounded-lg p-6" data-testid="active-propagations-panel">
        <p className="text-xs text-[#8A8A8E]">Loading auto-propagation detector…</p>
      </div>
    );
  }

  const active = data.active || [];

  return (
    <div className="bg-[#121212] border border-[#262626] rounded-lg p-6" data-testid="active-propagations-panel">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <h3 className="text-xs uppercase tracking-[0.2em] text-[#8A8A8E] flex items-center gap-2">
            <Radar className="w-3 h-3 text-[#FF9500]" />
            Auto-Detected Failure Propagations
          </h3>
          <p className="text-[10px] text-[#8A8A8E] mt-1">
            Continuous scan of stressed services + predictive cascade simulation. {data.detection_count} total detections.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-[10px] text-[#8A8A8E] flex items-center gap-1 cursor-pointer">
            <input
              type="checkbox"
              checked={data.enabled}
              onChange={(e) => toggleEnable('enabled', e.target.checked)}
              className="accent-[#00FF9D]"
              data-testid="auto-prop-enabled-toggle"
            />
            Detection
          </label>
          <label className="text-[10px] text-[#8A8A8E] flex items-center gap-1 cursor-pointer">
            <input
              type="checkbox"
              checked={data.autonomous_heal}
              onChange={(e) => toggleEnable('autonomous_heal', e.target.checked)}
              className="accent-[#00FF9D]"
              data-testid="auto-prop-heal-toggle"
            />
            Autonomous Heal
          </label>
        </div>
      </div>

      {active.length === 0 ? (
        <div className="p-6 bg-[#1F1F1F] rounded text-center" data-testid="active-propagations-empty">
          <p className="text-sm text-[#00FF9D]">All services within stress thresholds — no active propagations.</p>
          <p className="text-[10px] text-[#8A8A8E] mt-1">Threshold: pressure ≥ {data.stress_pressure_threshold}</p>
        </div>
      ) : (
        <div className="space-y-3" data-testid="active-propagations-list">
          {active.map((p) => (
            <div key={p.source} className="bg-[#1F1F1F] border border-[#FF9500]/30 rounded-lg p-3" data-testid={`active-prop-${p.source}`}>
              <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <Activity className="w-3 h-3 text-[#FF9500]" />
                  <span className="text-sm font-bold text-[#FFFFFF]">{p.source}</span>
                  <span className="text-[10px] text-[#FFCC00] font-mono" title={`Raw von-Mises pressure ${p.pressure.toFixed(3)} (threshold ${data.stress_pressure_threshold})`}>
                    {(p.pressure / Math.max(data.stress_pressure_threshold, 1e-6)).toFixed(0)}× threshold
                  </span>
                  {p.yield_exceeded && <span className="text-[10px] px-2 py-0.5 rounded bg-[#FF3B30]/20 text-[#FF3B30]">YIELD</span>}
                  {p.healing_executed && p.healing_executed.length > 0 && (
                    <span className="text-[10px] px-2 py-0.5 rounded bg-[#00FF9D]/20 text-[#00FF9D]">AUTO-HEALED ×{p.healing_executed.length}</span>
                  )}
                </div>
                {p.plan && p.plan.sequence && p.plan.sequence.length > 0 && (
                  <button
                    onClick={() => executeSequence(p.plan.sequence)}
                    disabled={executing}
                    className="text-[10px] px-2 py-1 rounded border bg-[#5AC8FA]/10 border-[#5AC8FA]/40 text-[#5AC8FA] hover:bg-[#5AC8FA]/20 flex items-center gap-1 disabled:opacity-50"
                    data-testid={`execute-plan-${p.source}`}
                  >
                    <Play className="w-3 h-3" /> Run Plan
                  </button>
                )}
              </div>

              {/* Predicted downstream impact */}
              <div className="text-[10px] text-[#8A8A8E] mb-2">
                Predicted impact on {p.downstream?.length || 0} downstream nodes:
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-1 mb-2">
                {(p.downstream || []).slice(0, 4).map((d) => (
                  <div key={d.node} className="text-[10px] font-mono px-2 py-1 bg-[#0F0F0F] rounded">
                    <div className="flex justify-between">
                      <span className="text-[#FFFFFF]">{d.node}</span>
                      <span className="text-[#FFCC00]">peak {d.peak_fault.toFixed(2)}</span>
                    </div>
                    <div className="text-[#8A8A8E]">arrives @ {d.first_arrival_t?.toFixed(1) || '∞'}s</div>
                  </div>
                ))}
              </div>

              {/* Optimized healing plan */}
              {p.plan && p.plan.sequence && p.plan.sequence.length > 0 && (
                <div className="mt-2" data-testid={`plan-${p.source}`}>
                  <div className="flex items-center gap-1 text-[10px] text-[#8A8A8E] uppercase tracking-wider mb-1">
                    <Wand2 className="w-3 h-3 text-[#5AC8FA]" />
                    Optimized healing plan • expected gain {p.plan.expected_total_sri_gain}
                  </div>
                  <div className="flex flex-wrap gap-1 text-[10px] font-mono">
                    {p.plan.sequence.map((step, i) => (
                      <div key={`${step.action_id}-${step.target_node}-${i}`} className={`px-2 py-1 rounded flex items-center gap-1 ${
                        step.readiness > 0.5 ? 'bg-[#00FF9D]/10 text-[#00FF9D]' : 'bg-[#FFCC00]/10 text-[#FFCC00]'
                      }`}>
                        <span className="text-[#8A8A8E]">{i + 1}.</span>
                        <span className="font-bold">{step.action_id}</span>
                        <span className="text-[#8A8A8E]">@{step.target_node}</span>
                        <span className="text-[#8A8A8E]">d={step.depth}</span>
                        {step.cooldown_remaining > 0 && <span className="text-[#FFCC00]">cd {step.cooldown_remaining.toFixed(0)}s</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Executed healing actions */}
              {p.healing_executed && p.healing_executed.length > 0 && (
                <div className="mt-2 text-[10px] font-mono">
                  <div className="text-[#8A8A8E] mb-1 flex items-center gap-1">
                    <Zap className="w-3 h-3 text-[#00A3FF]" /> Auto-executed:
                  </div>
                  {p.healing_executed.map((h, i) => (
                    <div key={`${h.action_id}-${h.target_node}-${i}`} className="px-2 py-0.5 rounded bg-[#00A3FF]/10 text-[#00A3FF]">
                      {h.action_id} @ {h.target_node}
                      {h.sri_delta !== undefined && h.sri_delta !== null && (
                        <span className={`ml-2 ${h.sri_delta >= 0 ? 'text-[#00FF9D]' : 'text-[#FF3B30]'}`}>
                          ΔSRI {h.sri_delta >= 0 ? '+' : ''}{h.sri_delta.toFixed(4)}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
