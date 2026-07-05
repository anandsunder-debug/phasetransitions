import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Users, ArrowRight, RefreshCw, TrendingUp, TrendingDown } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * RUM-Validated Healing Sequences (iter 32).
 *
 * Surfaces the closed-loop output of the RumLadderLearner: healing-action
 * sequences whose RUM (real-user) page_load / perceived_speed /
 * error_shown_rate moved measurably better. Each row shows the full
 * action chain and the three user-felt deltas. These bonuses are
 * already feeding back into LadderSynthesizer.compute_gain_matrix so
 * the engine progressively favors actions appearing in validated chains.
 */
export function RumValidatedSequencesCard({ isRunning }) {
  const [status, setStatus] = useState(null);
  const [sequences, setSequences] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const { data } = await axios.get(`${API}/healing/rum-sequences/top?limit=10`, { withCredentials: true });
      setStatus(data.status || null);
      setSequences(data.sequences || []);
    } catch (e) {
      console.error('Failed to load RUM-validated sequences:', e);
    }
  };

  useEffect(() => {
    load();
    if (!isRunning) return;
    const iv = setInterval(load, 8000);
    return () => clearInterval(iv);
  }, [isRunning]);

  const runNow = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/healing/rum-sequences/run-now`, {}, { withCredentials: true });
      toast.success(`Mined ${data.validated} validated sequence(s) · top_total=${data.top_total}`);
      load();
    } catch {
      toast.error('Run failed (admin only)');
    } finally {
      setBusy(false);
    }
  };

  if (!status) return null;

  const fmt = (n, decimals = 1) =>
    n === null || n === undefined ? '—' : (n >= 0 ? '+' : '') + n.toFixed(decimals);

  return (
    <div
      className="bg-[#1A1A1A] border border-[#34C759]/40 rounded-lg p-4"
      data-testid="rum-validated-sequences-card"
    >
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Users className="w-4 h-4 text-[#34C759]" />
          <h3 className="text-sm font-bold text-white">RUM-Validated Healing Sequences</h3>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#34C759]/15 text-[#34C759] border border-[#34C759]/40">
            users felt this
          </span>
        </div>
        <button
          onClick={runNow}
          disabled={busy}
          data-testid="rum-seq-run-now"
          className="text-[10px] px-2 py-1 rounded font-mono uppercase border bg-[#34C759]/15 text-[#34C759] border-[#34C759]/40 hover:bg-[#34C759]/25 disabled:opacity-40 flex items-center gap-1"
        >
          <RefreshCw className={`w-3 h-3 ${busy ? 'animate-spin' : ''}`} /> Mine now
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3 text-[11px]">
        <Stat label="Top sequences" value={status.top_total} />
        <Stat label="Nodes covered" value={status.nodes_with_validated_sequences} />
        <Stat label="Last pass" value={status.last_pass_ts ? new Date(status.last_pass_ts * 1000).toLocaleTimeString() : '—'} mono />
        <Stat label="Last seq · validated" value={`${status.last_seq_count} · ${status.last_validated_count}`} mono />
      </div>

      {sequences.length === 0 ? (
        <div className="text-[11px] text-[#8A8A8E] italic py-4 text-center">
          No validated sequences yet — waiting for healing actions + RUM beacons to accumulate.
        </div>
      ) : (
        <div className="space-y-2">
          {sequences.map((s, idx) => {
            const d = s.cx_delta || {};
            const plGood = d.page_load_ms_delta != null && d.page_load_ms_delta < 0;
            const psGood = d.perceived_speed_delta != null && d.perceived_speed_delta > 0;
            const erGood = d.error_shown_rate_delta != null && d.error_shown_rate_delta < 0;
            return (
              <div
                key={`${s.node}-${s.chain}-${idx}`}
                className="bg-[#0F0F10] border border-[#262626] rounded p-2"
                data-testid={`rum-seq-row-${idx}`}
              >
                <div className="flex items-center justify-between mb-1 flex-wrap gap-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#34C759]/10 text-[#34C759] border border-[#34C759]/30">
                      {s.node}
                    </span>
                    <span className="text-[10px] font-mono text-[#5A5A5E]">#{idx + 1}</span>
                    <span className="text-[10px] font-mono text-[#cfcfcf]">
                      gain = {s.rum_gain.toFixed(3)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-[9px] font-mono">
                    <span className={plGood ? 'text-[#34C759]' : 'text-[#8A8A8E]'}>
                      {plGood ? <TrendingDown className="inline w-3 h-3 mr-0.5" /> : null}
                      page_load Δ={fmt(d.page_load_ms_delta, 0)} ms
                    </span>
                    <span className={psGood ? 'text-[#34C759]' : 'text-[#8A8A8E]'}>
                      {psGood ? <TrendingUp className="inline w-3 h-3 mr-0.5" /> : null}
                      perceived Δ={fmt(d.perceived_speed_delta, 1)}
                    </span>
                    <span className={erGood ? 'text-[#34C759]' : 'text-[#8A8A8E]'}>
                      {erGood ? <TrendingDown className="inline w-3 h-3 mr-0.5" /> : null}
                      err_rate Δ={fmt(d.error_shown_rate_delta, 3)}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-1 flex-wrap">
                  {s.actions.map((act, i) => (
                    <React.Fragment key={`${s.node}-${s.chain}-${i}-${act}`}>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#1A1A1A] border border-[#3A3A3C] text-white">
                        {act}
                      </span>
                      {i < s.actions.length - 1 && (
                        <ArrowRight className="w-3 h-3 text-[#5A5A5E]" />
                      )}
                    </React.Fragment>
                  ))}
                </div>
                <div className="mt-1 text-[9px] font-mono text-[#5A5A5E]">
                  {d.samples_before} samples before · {d.samples_after} samples after ·
                  discovered {s.discovered_at ? new Date(s.discovered_at).toLocaleTimeString() : '—'}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-3 text-[10px] text-[#5A5A5E] leading-relaxed">
        Bonuses (max +{status.rum_bonus_coeff?.toFixed(2)}) added to LadderSynthesizer gain matrix per node ·
        sequence window {status.window_seconds}s · RUM window ±{status.rum_before_after_s}s
      </div>
    </div>
  );
}

function Stat({ label, value, mono }) {
  return (
    <div className="bg-[#0F0F10] border border-[#262626] rounded p-2">
      <div className="text-[9px] uppercase tracking-widest text-[#5A5A5E] mb-0.5">{label}</div>
      <div className={`${mono ? 'font-mono' : ''} text-xs text-white`}>{value ?? '—'}</div>
    </div>
  );
}

export default RumValidatedSequencesCard;
