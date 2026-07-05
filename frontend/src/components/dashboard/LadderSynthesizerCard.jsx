import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Cpu, RefreshCw, RotateCcw, Sparkles } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Ladder Synthesizer — "Programs writing programs".
 *
 * Surfaces the meta-engine that rewrites the healing engine's
 * `escalation_ladder` config from observed reliability gains.
 * Shows version, last synthesis time, per-node ladder + diff vs prior,
 * gain matrix heat-row, and admin controls (force re-synthesize, rollback).
 */
export function LadderSynthesizerCard({ isRunning }) {
  const [data, setData] = useState(null);
  const [matrix, setMatrix] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/healing/ladder/current`, { withCredentials: true });
      setData(data);
    } catch { /* silent */ }
    try {
      const { data } = await axios.get(`${API}/healing/ladder/gain-matrix`, { withCredentials: true });
      setMatrix(data.gain_matrix || null);
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    load();
    if (!isRunning) return;
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, [isRunning, load]);

  const synthesize = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/healing/ladder/synthesize`, {}, { withCredentials: true });
      if (data.swapped) toast.success(`Ladder v${data.version} synthesized (${Object.keys(data.diff || {}).length} nodes changed)`);
      else toast.info('No change — current ladder is already optimal');
      load();
    } catch {
      toast.error('Synthesize failed (admin only)');
    } finally {
      setBusy(false);
    }
  };

  const rollback = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/healing/ladder/rollback`, {}, { withCredentials: true });
      if (data.rolled_back) toast.success(`Rolled back to ladder v${data.version}`);
      else toast.error(data.reason || 'No previous ladder to roll back to');
      load();
    } catch {
      toast.error('Rollback failed (admin only)');
    } finally {
      setBusy(false);
    }
  };

  const toggle = async () => {
    if (!data) return;
    try {
      await axios.post(`${API}/healing/ladder/toggle`, { enabled: !data.enabled }, { withCredentials: true });
      toast.success(`Synthesizer ${!data.enabled ? 'enabled' : 'disabled'}`);
      load();
    } catch {
      toast.error('Toggle failed (admin only)');
    }
  };

  if (!data) return null;

  const ladder = data.current_ladder || {};
  const diff = data.last_diff || {};
  const nodes = Object.keys(ladder);

  // gain-matrix heat coloring
  const heat = (v) => {
    if (v === undefined || v === null) return 'text-[#5A5A5E]';
    if (v > 0.20) return 'text-[#00FF9D]';
    if (v > 0.10) return 'text-[#8FE388]';
    if (v > 0) return 'text-[#FFD60A]';
    return 'text-[#FF453A]';
  };

  return (
    <div
      className="bg-[#1A1A1A] border border-[#5E5CE6]/40 rounded-lg p-4"
      data-testid="ladder-synthesizer-card"
    >
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Cpu className="w-4 h-4 text-[#5E5CE6]" />
          <h3 className="text-sm font-bold text-white">Ladder Synthesizer · Programs Writing Programs</h3>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#5E5CE6]/20 text-[#5E5CE6] border border-[#5E5CE6]/40">
            v{data.version}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={toggle}
            data-testid="ladder-synth-toggle"
            className={`text-[10px] px-2 py-1 rounded font-mono uppercase border ${
              data.enabled
                ? 'bg-[#34C759]/20 text-[#34C759] border-[#34C759]/40'
                : 'bg-[#1A1A1A] text-[#8A8A8E] border-[#3A3A3C]'
            }`}
          >
            {data.enabled ? 'Auto' : 'Off'}
          </button>
          <button
            onClick={synthesize}
            disabled={busy}
            data-testid="ladder-synth-now"
            className="text-[10px] px-2 py-1 rounded font-mono uppercase border bg-[#5E5CE6]/15 text-[#5E5CE6] border-[#5E5CE6]/40 hover:bg-[#5E5CE6]/25 disabled:opacity-40 flex items-center gap-1"
          >
            <Sparkles className="w-3 h-3" /> Synth
          </button>
          <button
            onClick={rollback}
            disabled={busy || !data.previous_ladder}
            data-testid="ladder-synth-rollback"
            className="text-[10px] px-2 py-1 rounded font-mono uppercase border bg-[#FF6B35]/15 text-[#FF6B35] border-[#FF6B35]/40 hover:bg-[#FF6B35]/25 disabled:opacity-30 flex items-center gap-1"
          >
            <RotateCcw className="w-3 h-3" /> Rollback
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4 text-[11px]">
        <Stat label="Last synth" value={data.last_synth_ts ? new Date(data.last_synth_ts).toLocaleTimeString() : '—'} />
        <Stat label="Last reason" value={data.last_reason || '—'} mono />
        <Stat label="Rollback armed" value={data.rollback_armed ? 'yes' : 'no'} accent={data.rollback_armed ? '#FFD60A' : '#8A8A8E'} />
        <Stat label="History size" value={data.history_size} />
      </div>

      <div className="space-y-2">
        <div className="text-[10px] uppercase tracking-widest text-[#8A8A8E] flex items-center justify-between flex-wrap gap-2">
          <span>Synthesized Ladders (per node) — low-complexity high-improvement first</span>
          {/* iter 39 — complexity-tier legend */}
          <span className="flex items-center gap-2 text-[9px] normal-case tracking-normal text-[#8A8A8E]">
            <span className="inline-flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-[#34C759]" />T1 simple</span>
            <span className="inline-flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-[#5AC8FA]" />T2</span>
            <span className="inline-flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-[#FFCC00]" />T3</span>
            <span className="inline-flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-[#FF453A]" />T4 complex</span>
          </span>
        </div>
        {nodes.map((node) => {
          const changed = !!diff[node];
          const before = diff[node]?.before;
          return (
            <div key={node} className="border border-[#262626] rounded p-2 bg-[#0F0F10]" data-testid={`ladder-row-${node}`}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-bold text-white">{node}</span>
                {changed && (
                  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-[#FFD60A]/15 text-[#FFD60A] border border-[#FFD60A]/40">
                    REWRITTEN
                  </span>
                )}
              </div>
              <div className="flex flex-wrap gap-1.5 items-center">
                {ladder[node].map((aid, i) => {
                  const score = matrix?.[node]?.[aid];
                  // iter 39 — per-action complexity tier (0=simple, 1=complex)
                  const complexity = data.complexity_ladder?.[node]?.find((x) => x.action === aid)?.complexity;
                  const cmplxColor = complexity === undefined
                    ? 'bg-[#3A3A3C]'
                    : complexity < 0.25 ? 'bg-[#34C759]'      // tier 1 — green / simple
                    : complexity < 0.50 ? 'bg-[#5AC8FA]'      // tier 2 — cyan
                    : complexity < 0.75 ? 'bg-[#FFCC00]'      // tier 3 — amber
                    : 'bg-[#FF453A]';                          // tier 4 — red / complex
                  return (
                    <span
                      key={aid}
                      className={`text-[10px] font-mono px-2 py-0.5 rounded border bg-[#1A1A1A] border-[#3A3A3C] ${heat(score)} inline-flex items-center gap-1`}
                      title={`${score !== undefined ? `gain=${score.toFixed(4)} · ` : ''}complexity=${complexity?.toFixed(2) ?? '—'}`}
                      data-testid={`ladder-action-pill-${node}-${aid}`}
                    >
                      {/* complexity dot */}
                      <span className={`inline-block w-1.5 h-1.5 rounded-full ${cmplxColor}`} />
                      {i + 1}·{aid}
                      {score !== undefined && (
                        <span className="ml-1 opacity-70">{score >= 0 ? '+' : ''}{score.toFixed(3)}</span>
                      )}
                    </span>
                  );
                })}
              </div>
              {changed && before && (
                <div className="mt-1 text-[9px] font-mono text-[#5A5A5E]">
                  was: {before.join(' → ')}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-3 text-[10px] text-[#5A5A5E] leading-relaxed">
        <RefreshCw className="inline w-3 h-3 mr-1 -mt-px" />
        Auto-synth every {data.synthesis_interval_s}s · stagnation trigger {data.stagnation_trigger_s}s ·
        rollback guard ±{data.rollback_regression_delta} SRI over {data.rollback_window_s}s window.
      </div>
    </div>
  );
}

function Stat({ label, value, accent, mono }) {
  return (
    <div className="bg-[#0F0F10] border border-[#262626] rounded p-2">
      <div className="text-[9px] uppercase tracking-widest text-[#5A5A5E] mb-0.5">{label}</div>
      <div
        className={`${mono ? 'font-mono' : ''} text-xs text-white`}
        style={accent ? { color: accent } : undefined}
      >
        {value ?? '—'}
      </div>
    </div>
  );
}

export default LadderSynthesizerCard;
