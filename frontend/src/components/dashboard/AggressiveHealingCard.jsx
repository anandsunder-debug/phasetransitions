import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Zap, TrendingDown, ShieldCheck } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Aggressive / Reliability-aware Healing — surfaces the proactive heal loop
 * that fires *before* SRI dips when resilience debt is accumulating.
 */
export function AggressiveHealingCard({ isRunning }) {
  const [data, setData] = useState(null);
  const [permFixes, setPermFixes] = useState(null);
  const [ranking, setRanking] = useState(null);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/healing/aggressive/status`, { withCredentials: true });
      setData(data);
    } catch (e) {
      console.error('Failed to load aggressive healing status:', e);
    }
    try {
      const { data: pf } = await axios.get(`${API}/healing/permanent-fixes`, { withCredentials: true });
      setPermFixes(pf);
    } catch (e) {
      console.error('Failed to load permanent fixes:', e);
    }
    // iter 40 — preview the cheap-first ranking on every tick
    try {
      const { data: rk } = await axios.get(`${API}/healing/aggressive/preview-ranking`, { withCredentials: true });
      setRanking(rk);
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    load();
    if (!isRunning) return;
    const iv = setInterval(load, 4000);
    return () => clearInterval(iv);
  }, [isRunning, load]);

  const toggle = async (enabled) => {
    try {
      await axios.post(`${API}/healing/aggressive/toggle`, { enabled }, { withCredentials: true });
      toast.success(`Aggressive mode ${enabled ? 'enabled' : 'disabled'}`);
      load();
    } catch (e) {
      console.error('Aggressive toggle failed:', e);
      toast.error('Toggle failed (admin only)');
    }
  };

  // Flatten the {node: {signal: multiplier}} registry into a stable, memoised array
  // so React doesn't re-build the list on every parent tick.
  const permFixEntries = useMemo(() => {
    const reg = permFixes?.registry || {};
    return Object.entries(reg).flatMap(([node, sigs]) =>
      Object.entries(sigs).map(([sig, mult]) => ({ node, sig, mult })),
    );
  }, [permFixes?.registry]);

  if (!data) return null;
  const recent = data.recent_actions || [];

  return (
    <div className="bg-[#1A1A1A] border border-[#FF6B35]/40 rounded-lg p-4" data-testid="aggressive-healing-card">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-[#FF6B35]" />
          <h3 className="text-sm font-bold text-white">Aggressive Reliability Heal</h3>
        </div>
        <button
          onClick={() => toggle(!data.enabled)}
          data-testid="aggressive-toggle"
          className={`text-[10px] px-2 py-1 rounded font-mono uppercase border ${
            data.enabled
              ? 'bg-[#34C759]/20 text-[#34C759] border-[#34C759]/40'
              : 'bg-[#1A1A1A] text-[#8A8A8E] border-[#3A3A3C]'
          }`}
        >
          {data.enabled ? 'ON' : 'OFF'}
        </button>
      </div>

      <div className="grid grid-cols-4 gap-2 mb-3">
        <div className="bg-[#0F0F0F] rounded p-2">
          <div className="text-[9px] text-[#8A8A8E] uppercase">Proactive Fires</div>
          <div className="text-base font-bold text-[#5AC8FA] font-mono">{data.proactive_fire_count}</div>
        </div>
        <div className="bg-[#0F0F0F] rounded p-2">
          <div className="text-[9px] text-[#8A8A8E] uppercase flex items-center gap-1">
            <TrendingDown className="w-2.5 h-2.5" /> Reliability Δ (60s)
          </div>
          <div className={`text-base font-bold font-mono ${data.reliability_gain_60s >= 0 ? 'text-[#34C759]' : 'text-[#FF453A]'}`}>
            {data.reliability_gain_60s >= 0 ? '+' : ''}{(data.reliability_gain_60s * 100).toFixed(2)}%
          </div>
        </div>
        <div className="bg-[#0F0F0F] rounded p-2" data-testid="counterfactual-tile">
          <div className="text-[9px] text-[#8A8A8E] uppercase">Reliability Saved</div>
          <div className="text-base font-bold text-[#34C759] font-mono">
            +{((data.counterfactual?.reliability_saved || 0) * 100).toFixed(2)}%
          </div>
          <div className="text-[8px] text-[#8A8A8E] mt-0.5 font-mono">
            vs counterfactual {(((data.counterfactual?.counterfactual_reliability) || 0) * 100).toFixed(1)}%
          </div>
          <div className="text-[8px] text-[#34C759] mt-0.5 font-mono" data-testid="aggressive-roi">
            ≈ ${((data.counterfactual?.reliability_saved || 0) * (data.proactive_fire_count || 0) * 0.5).toFixed(2)} saved
          </div>
        </div>
        <div className="bg-[#0F0F0F] rounded p-2">
          <div className="text-[9px] text-[#8A8A8E] uppercase">Debt Threshold</div>
          <div className="text-base font-bold text-[#AF52DE] font-mono">{data.debt_rate_threshold}</div>
        </div>
      </div>

      {data.phi_reduction_per_action && Object.keys(data.phi_reduction_per_action).length > 0 && (
        <div className="mb-3">
          <div className="text-[10px] text-[#8A8A8E] mb-1 uppercase tracking-wider">Φ-Reduction per Action (debt-rate Δ)</div>
          <div className="grid grid-cols-2 gap-1">
            {Object.entries(data.phi_reduction_per_action).map(([aid, val]) => (
              <div key={aid} className="text-[10px] font-mono bg-[#0F0F0F] rounded px-2 py-1 flex justify-between">
                <span className="text-[#FF6B35]">{aid}</span>
                <span className={val >= 0 ? 'text-[#34C759]' : 'text-[#FF453A]'}>
                  {val >= 0 ? '↓' : '↑'} {Math.abs(val).toFixed(4)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="text-[10px] text-[#8A8A8E] mb-1 uppercase tracking-wider">Recent Proactive Heals</div>
      <div className="space-y-1 max-h-32 overflow-y-auto">
        {recent.length === 0 ? (
          <div className="text-[10px] text-[#8A8A8E] italic">Waiting for debt rate &gt; threshold or predicted SRI dip…</div>
        ) : (
          recent.slice().reverse().map((a, i) => (
            <div key={i} className="text-[10px] font-mono bg-[#0F0F0F] rounded px-2 py-1 flex items-center justify-between">
              <span className="text-white truncate" title={a.reason}>
                <span className="text-[#FF6B35]">{a.action_id}</span> @ <span className="text-[#5AC8FA]">{a.target}</span>
              </span>
              <span className="text-[#8A8A8E] flex-shrink-0">
                score {a.score?.toFixed?.(4)} · Δsri {(a.sri_delta || 0).toFixed(4)}
              </span>
            </div>
          ))
        )}
      </div>

      {permFixes && (
        <div className="mt-4 pt-3 border-t border-[#3A3A3C]/40" data-testid="permanent-fixes-section">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-[#5AC8FA]" />
              <span className="text-[11px] font-bold text-white uppercase tracking-wider">Permanent Funnel Fixes</span>
            </div>
            <span className="text-[10px] text-[#8A8A8E] font-mono">
              {permFixes.fix_count} installed · suppression Σ {permFixes.total_debt_suppression_estimate?.toFixed?.(2)}
            </span>
          </div>
          {permFixEntries.length === 0 ? (
            <div className="text-[10px] text-[#8A8A8E] italic">No conversion-funnel stagnation detected — no permanent fixes installed.</div>
          ) : (
            <div className="grid grid-cols-2 gap-1">
              {permFixEntries.map(({ node, sig, mult }) => (
                <div key={`${node}-${sig}`} className="text-[10px] font-mono bg-[#0F0F0F] rounded px-2 py-1 flex justify-between" data-testid={`perm-fix-${node}-${sig}`}>
                  <span className="text-white">
                    <span className="text-[#5AC8FA]">{node}</span>.<span className="text-[#FF6B35]">{sig}</span>
                  </span>
                  <span className="text-[#34C759]">×{(1 - mult).toFixed(2)} stiffness</span>
                </div>
              ))}
            </div>
          )}
          {(permFixes.recent_fixes || []).length > 0 && (
            <div className="mt-1 text-[9px] text-[#8A8A8E] italic">
              Latest: {permFixes.recent_fixes[permFixes.recent_fixes.length - 1].rationale}
            </div>
          )}
        </div>
      )}

      {/* iter 40 — Cheap-first escalation preview. Shows the live rank order
          that the engine would walk on its next fire: cheapest, highest-
          improvement-per-cost first. ★ marks plateaued actions (recent
          |ΔSRI| below noise floor → bias relaxed → costlier actions
          become competitive). */}
      {ranking?.ranked?.length > 0 && (
        <div
          className="mt-3 pt-3 border-t border-[#262626]"
          data-testid="cheap-first-escalation-preview"
        >
          <div className="flex items-center justify-between mb-1.5 flex-wrap gap-2">
            <span className="text-[10px] uppercase tracking-widest text-[#8A8A8E]">
              Cheap-First Escalation Order — Unified Objective: minimize d(x, Ψ_s)²
            </span>
            <span className="text-[9px] font-mono text-[#8A8A8E]">
              bias=+{ranking.low_cost_bias.toFixed(2)} · plateau&lt;{ranking.plateau_threshold}
            </span>
          </div>
          <div className="space-y-1">
            {ranking.ranked.slice(0, 8).map((r, i) => {
              const cost = r.cost ?? 0;
              const costPct = Math.min(100, cost * 100);
              const tierColor = cost <= 0.20 ? '#34C759'
                : cost <= 0.40 ? '#5AC8FA'
                : cost <= 0.55 ? '#FFCC00'
                : '#FF453A';
              // iter 41 — eutectic-pull Δd² (negative = pulls toward Ψ_s)
              const eutDelta = r.eut_delta_d2 ?? 0;
              const eutTarget = r.eut_target || '';
              const eutColor = eutDelta < -0.001 ? '#34C759' : eutDelta > 0.001 ? '#FF453A' : '#5A5A5E';
              return (
                <div
                  key={r.action}
                  className="flex items-center gap-2 text-[10px] font-mono"
                  data-testid={`cheap-first-rank-${i + 1}`}
                >
                  <span className="text-[#5A5A5E] w-4 text-right">{i + 1}.</span>
                  <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: tierColor }} />
                  <span className="flex-1 truncate text-white">{r.action}</span>
                  {r.plateaued && (
                    <span
                      className="text-[8px] px-1 py-px rounded bg-[#FFCC00]/15 text-[#FFCC00] border border-[#FFCC00]/40"
                      title="Recent |ΔSRI| below noise floor — bias relaxed, costlier actions now competitive"
                    >
                      ★ PLATEAU
                    </span>
                  )}
                  <span
                    className="w-20 text-right"
                    style={{ color: eutColor }}
                    title={`Simulated change in d(x, Ψ_s)² on ${eutTarget || 'target'} — negative pulls toward Ψ_s`}
                  >
                    Δd²={eutDelta >= 0 ? '+' : ''}{eutDelta.toFixed(4)}
                  </span>
                  <div className="w-12 h-1 bg-[#0F0F10] rounded overflow-hidden">
                    <div className="h-full" style={{ width: `${costPct}%`, background: tierColor }} />
                  </div>
                  <span className="w-10 text-right text-[#8A8A8E]" title="cost">${cost.toFixed(2)}</span>
                  <span className="w-14 text-right" style={{ color: r.score >= 0 ? '#34C759' : '#FF453A' }} title="score">
                    {r.score >= 0 ? '+' : ''}{r.score.toFixed(3)}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="mt-1.5 text-[9px] text-[#5A5A5E] leading-relaxed">
            Engine walks this list top→down, skipping cooldown + exhausted actions.
            Primary objective: minimize d(x, Ψ_s)² (Δd² &lt; 0 pulls toward Ψ_s).
            Cost ramp T1 simple → T4 complex.
          </div>
        </div>
      )}
    </div>
  );
}

export default AggressiveHealingCard;
