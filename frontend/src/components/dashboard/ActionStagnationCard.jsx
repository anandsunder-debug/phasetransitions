import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { AlertOctagon, RotateCcw, X } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Action Stagnation Card (iter 34).
 *
 * Surfaces the inner-loop ActionStagnationGuard: (node, action) pairs
 * currently removed from the live ladder because the last N attempts
 * produced |ΔSRI| < ε. Shows cooldown countdowns + admin manual
 * restore. The synthesizer + auto-heal cycle both consult this card's
 * underlying registry — once a pair appears here, the engine has
 * already stopped picking it.
 */
export function ActionStagnationCard({ isRunning }) {
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const { data } = await axios.get(`${API}/healing/stagnation/state`, { withCredentials: true });
      setState(data);
    } catch (e) {
      console.error('Failed to load stagnation state:', e);
    }
  };

  useEffect(() => {
    load();
    if (!isRunning) return;
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, [isRunning]);

  const restore = async (node, action) => {
    setBusy(true);
    try {
      const { data } = await axios.post(
        `${API}/healing/stagnation/restore`,
        { node, action },
        { withCredentials: true },
      );
      if (data.restored) toast.success(`${node}@${action} restored`);
      else toast.error('Not in stagnation list');
      load();
    } catch {
      toast.error('Restore failed (admin only)');
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/healing/stagnation/reset`, {}, { withCredentials: true });
      toast.success(`Cleared ${data.cleared} stagnant pair(s)`);
      load();
    } catch {
      toast.error('Reset failed (admin only)');
    } finally {
      setBusy(false);
    }
  };

  if (!state) return null;
  const removed = state.removed || [];
  const events = state.events || [];

  return (
    <div
      className="bg-[#1A1A1A] border border-[#FF453A]/40 rounded-lg p-4"
      data-testid="action-stagnation-card"
    >
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <AlertOctagon className="w-4 h-4 text-[#FF453A]" />
          <h3 className="text-sm font-bold text-white">Action Stagnation Guard</h3>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#FF453A]/15 text-[#FF453A] border border-[#FF453A]/40">
            {removed.length} removed
          </span>
        </div>
        <button
          onClick={reset}
          disabled={busy || removed.length === 0}
          data-testid="stagnation-reset"
          className="text-[10px] px-2 py-1 rounded font-mono uppercase border bg-[#FF453A]/15 text-[#FF453A] border-[#FF453A]/40 hover:bg-[#FF453A]/25 disabled:opacity-40 flex items-center gap-1"
        >
          <X className="w-3 h-3" /> Reset all
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3 text-[11px]">
        <Stat label="Removed" value={removed.length} accent="#FF453A" />
        <Stat label="Tracked pairs" value={state.attempts_tracked} />
        <Stat label="Window" value={`${state.window} attempts`} mono />
        <Stat label="Cooldown" value={`${Math.round(state.cooldown_s)}s`} mono />
      </div>

      {/* Currently removed */}
      {removed.length === 0 ? (
        <div className="text-[11px] text-[#34C759] italic py-3 text-center bg-[#0F0F10] border border-[#262626] rounded">
          ✓ no stagnant pairs — every (node, action) is currently moving SRI above the noise floor (|ΔSRI| ≥ {state.epsilon})
        </div>
      ) : (
        <div className="space-y-1.5 mb-3">
          <div className="text-[10px] uppercase tracking-widest text-[#8A8A8E]">Currently removed (auto-restore on cooldown)</div>
          {removed.map((r) => (
            <div
              key={`${r.node}-${r.action}`}
              className="flex items-center gap-2 bg-[#0F0F10] border border-[#262626] rounded p-2"
              data-testid={`stagnation-row-${r.node}-${r.action}`}
            >
              <span className="text-[10px] font-mono text-white w-20 font-bold">{r.node}</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#FF453A]/10 text-[#FF453A] border border-[#FF453A]/30 flex-1">
                {r.action}
              </span>
              <span className="text-[10px] font-mono text-[#8A8A8E]">
                mean |ΔSRI|={r.mean_abs_delta.toExponential(1)}
              </span>
              <span className="text-[10px] font-mono text-[#FFCC00] w-20 text-right">
                {r.cooldown_remaining_s.toFixed(0)}s
              </span>
              <button
                onClick={() => restore(r.node, r.action)}
                disabled={busy}
                className="text-[10px] px-1.5 py-0.5 rounded font-mono uppercase border bg-[#34C759]/15 text-[#34C759] border-[#34C759]/40 hover:bg-[#34C759]/25 disabled:opacity-40 flex items-center gap-1"
                data-testid={`stagnation-restore-${r.node}-${r.action}`}
              >
                <RotateCcw className="w-2.5 h-2.5" /> Restore
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Recent events */}
      {events.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-widest text-[#8A8A8E] mb-1">Recent events</div>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {events.slice(0, 8).map((e, i) => (
              <div
                key={`evt-${e.timestamp}-${i}`}
                className="text-[10px] font-mono px-2 py-1 bg-[#0F0F10] border border-[#262626] rounded flex items-center gap-2"
              >
                <span className={e.kind === 'stagnated' ? 'text-[#FF453A]' : e.kind === 'restored' ? 'text-[#34C759]' : 'text-[#8A8A8E]'}>
                  {e.kind === 'stagnated' ? '✗' : e.kind === 'restored' ? '✓' : '—'}
                </span>
                <span className="text-[#cfcfcf]">{e.kind}</span>
                {e.node && e.action && (
                  <span className="text-[#cfcfcf]">{e.node}@{e.action}</span>
                )}
                {e.reason && <span className="text-[#5A5A5E]">· {e.reason}</span>}
                {e.was_stagnant_for_s !== undefined && (
                  <span className="text-[#5A5A5E]">· stagnant for {e.was_stagnant_for_s.toFixed(0)}s</span>
                )}
                <span className="text-[#5A5A5E] ml-auto">{new Date(e.timestamp * 1000).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-3 text-[10px] text-[#5A5A5E] leading-relaxed">
        Pairs removed when last {state.window} attempts all |ΔSRI| &lt; {state.epsilon} ·
        synthesizer + auto-heal cycle both consult this list before picking actions
      </div>
    </div>
  );
}

function Stat({ label, value, mono, accent }) {
  return (
    <div className="bg-[#0F0F10] border border-[#262626] rounded p-2">
      <div className="text-[9px] uppercase tracking-widest text-[#5A5A5E] mb-0.5">{label}</div>
      <div className={`${mono ? 'font-mono' : ''} text-xs text-white`} style={accent ? { color: accent } : undefined}>
        {value ?? '—'}
      </div>
    </div>
  );
}

export default ActionStagnationCard;
