import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Route, Zap, CheckCircle2, AlertCircle } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Path-to-Stable Card (iter 45).
 *
 * Computes and displays the fastest greedy-planned sequence of healing
 * actions that takes each stressed node from its current phase-space
 * coordinates back to Ψ_s (the stable operating point). Uses one-sided
 * distance (Ψ_s as a CEILING): nodes operating BELOW Ψ_s on every axis
 * show d²=0 ("stable, no healing needed"). Nodes ABOVE Ψ_s get a step-
 * by-step plan with predicted Δd² per action and total cost.
 *
 * GET /api/healing/path-to-stable returns the per-node plans + summary.
 */
export function PathToStableCard({ isRunning }) {
  const [data, setData] = useState(null);

  const load = useCallback(async () => {
    try {
      const { data: d } = await axios.get(`${API}/healing/path-to-stable?max_steps=5`, { withCredentials: true });
      setData(d);
    } catch (e) { /* silent */ }
  }, []);

  useEffect(() => {
    load();
    if (!isRunning) return;
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, [isRunning, load]);

  if (!data) return null;
  if (!data.applicable) {
    return (
      <div className="bg-[#121212] border border-[#262626] rounded-lg p-4" data-testid="path-to-stable-card">
        <p className="text-xs text-[#8A8A8E] italic">Path-to-stable planner: {data.reason}</p>
      </div>
    );
  }
  const summary = data.summary || {};
  const plans = data.plans || {};
  const stressedNodes = Object.entries(plans).filter(([, p]) => p.applicable && (p.steps || []).length > 0);
  const stableNodes   = Object.entries(plans).filter(([, p]) => p.applicable && (p.steps || []).length === 0);

  return (
    <div
      className="bg-[#121212] border border-[#00FF9D]/30 rounded-lg p-4"
      data-testid="path-to-stable-card"
    >
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h3 className="text-xs uppercase tracking-[0.2em] text-[#8A8A8E] flex items-center gap-2">
          <Route className="w-3 h-3 text-[#00FF9D]" />
          Fastest Path to Ψ_s
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#00FF9D]/15 text-[#00FF9D] border border-[#00FF9D]/40 normal-case tracking-normal">
            iter 45 · Greedy IPC Planner
          </span>
        </h3>
        <div className="text-[10px] font-mono text-[#5A5A5E]">
          {summary.total_actions_across_nodes ?? 0} action(s) · ${(summary.total_cost ?? 0).toFixed(2)} total
        </div>
      </div>

      {stressedNodes.length === 0 ? (
        <div className="bg-[#0F0F10] border border-[#00FF9D]/20 rounded p-3 text-center">
          <CheckCircle2 className="w-5 h-5 text-[#00FF9D] mx-auto mb-1" />
          <div className="text-[11px] text-[#00FF9D] font-mono">
            All nodes at or below Ψ_s — no healing path needed
          </div>
          <div className="text-[10px] text-[#5A5A5E] mt-0.5">
            ({stableNodes.length} stable nodes · d² = 0 on every axis)
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {stressedNodes.map(([node, plan]) => (
            <NodePlan key={node} node={node} plan={plan} />
          ))}
          {stableNodes.length > 0 && (
            <div className="text-[10px] text-[#5A5A5E] italic pt-2 border-t border-[#262626]">
              ✓ {stableNodes.map(([n]) => n).join(', ')} already at/below Ψ_s — no plan needed
            </div>
          )}
        </div>
      )}

      <div className="mt-3 text-[10px] text-[#5A5A5E] leading-relaxed">
        Greedy forward-simulation through the healing ladder, picking the highest
        improvement-per-cost (IPC = −Δd² / cost) at each step. Ψ_s is treated as a
        CEILING: nodes below it need no healing. d² uses one-sided L2 distance.
      </div>
    </div>
  );
}

function NodePlan({ node, plan }) {
  return (
    <div className="bg-[#1F1F1F] rounded-lg p-3 border border-[#262626]" data-testid={`path-plan-${node}`}>
      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-white">{node}</span>
          {plan.reached_target ? (
            <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-[#00FF9D]/15 text-[#00FF9D] border border-[#00FF9D]/40">
              REACHES Ψ_s
            </span>
          ) : (
            <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-[#FFCC00]/15 text-[#FFCC00] border border-[#FFCC00]/40">
              <AlertCircle className="w-2.5 h-2.5 inline mr-0.5" />
              PARTIAL
            </span>
          )}
        </div>
        <div className="text-[10px] font-mono text-[#5A5A5E]">
          d²: <span className="text-[#FF453A]">{plan.start_d2.toFixed(4)}</span>
          {' '}→{' '}
          <span className="text-[#00FF9D]">{plan.final_d2.toFixed(4)}</span>
          {' · '}
          {plan.total_actions} steps · ${plan.total_cost.toFixed(2)}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-1">
        {plan.steps.map((s, i) => (
          <React.Fragment key={s.step}>
            <span
              className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-1 rounded bg-[#0F0F10] border border-[#262626]"
              title={`Δd²=${s.delta_d2.toFixed(5)} | IPC=${s.improvement_per_cost} | cost=$${s.cost}`}
              data-testid={`path-step-${node}-${s.step}`}
            >
              <span className="text-[#5A5A5E]">{s.step}.</span>
              <Zap className="w-2.5 h-2.5 text-[#FFCC00]" />
              <span className="text-white">{s.action}</span>
              <span className="text-[#00FF9D]">{s.delta_d2.toFixed(4)}</span>
              <span className="text-[#5A5A5E]">${s.cost.toFixed(2)}</span>
            </span>
            {i < plan.steps.length - 1 && (
              <span className="text-[#5A5A5E] text-[10px]">→</span>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

export default PathToStableCard;
