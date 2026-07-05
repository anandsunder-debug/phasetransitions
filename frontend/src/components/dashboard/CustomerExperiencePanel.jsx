import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Legend } from 'recharts';
import { Smile, Frown, Meh, UserCheck, Play, Sparkles, TrendingUp, TrendingDown, AlertTriangle, Gauge } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const VERDICT_ICON = {
  delightful: Smile,
  acceptable: Meh,
  frustrating: Frown,
  broken: AlertTriangle,
};

const VERDICT_LABEL = {
  delightful: 'Delightful',
  acceptable: 'Acceptable',
  frustrating: 'Frustrating',
  broken: 'Broken',
};

function ScoreTile({ label, value, suffix, color, sublabel, testid }) {
  return (
    <div className="p-3 bg-[#1F1F1F] rounded-lg" data-testid={testid}>
      <p className="text-[10px] text-[#8A8A8E] uppercase tracking-wider mb-1">{label}</p>
      <p className="text-xl font-bold font-['JetBrains_Mono']" style={{ color }}>
        {value}{suffix}
      </p>
      {sublabel && <p className="text-[10px] text-[#8A8A8E]">{sublabel}</p>}
    </div>
  );
}

export function CustomerExperiencePanel({ isRunning }) {
  const [data, setData] = useState(null);
  const [journey, setJourney] = useState(null);
  const [running, setRunning] = useState(false);
  const [animStep, setAnimStep] = useState(-1);

  const load = async () => {
    try {
      const { data } = await axios.get(`${API}/cx/metrics`, {
        params: { window_seconds: 300 },
        withCredentials: true,
      });
      setData(data);
    } catch (e) { /* silent */ }
  };

  useEffect(() => {
    load();
    if (!isRunning) return;
    const iv = setInterval(load, 4000);
    return () => clearInterval(iv);
  }, [isRunning]);

  const runSynthetic = async () => {
    setRunning(true);
    setJourney(null);
    setAnimStep(-1);
    try {
      const { data: j } = await axios.post(`${API}/cx/synthetic-user/run`, {}, { withCredentials: true });
      setJourney(j);
      // Animate step-by-step
      j.steps.forEach((_, i) => setTimeout(() => setAnimStep(i), (i + 1) * 500));
      const toaster = { delightful: toast.success, acceptable: toast.info, frustrating: toast.warning, broken: toast.error }[j.verdict] || toast;
      toaster(`User journey: ${VERDICT_LABEL[j.verdict]} — avg ${j.avg_latency_ms.toFixed(0)}ms, ${j.errors_seen} error${j.errors_seen === 1 ? '' : 's'}`);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Synthetic user failed');
    } finally {
      setRunning(false);
    }
  };

  const chartData = useMemo(() => {
    if (!data?.series) return [];
    return data.series.map(s => ({
      tLabel: `${s.t.toFixed(0)}s`,
      t: s.t,
      page_load: s.page_load_ms,
      perceived: s.perceived_speed,
      error_rate: s.error_shown_rate,
    }));
  }, [data]);

  // Derived annotation lists — memoised to avoid recomputing filter/slice/map on every render
  const chartAnnotations = useMemo(
    () => (data?.annotations || [])
      .filter(a => typeof a?.t_relative === 'number')
      .slice(-6),
    [data?.annotations],
  );

  const healingImpacts = useMemo(
    () => (data?.annotations || [])
      .filter(a => a.cx_delta?.samples_before > 0 && a.cx_delta?.samples_after > 0)
      .slice(-5)
      .reverse(),
    [data?.annotations],
  );

  const r30 = data?.rolling_30s || {};
  const plColor = r30.page_load_ms > 1000 ? '#FF3B30' : r30.page_load_ms > 500 ? '#FFCC00' : '#00FF9D';
  const psColor = r30.perceived_speed >= 85 ? '#00FF9D' : r30.perceived_speed >= 60 ? '#FFCC00' : '#FF3B30';
  const erColor = r30.error_shown_rate > 2 ? '#FF3B30' : r30.error_shown_rate > 0.5 ? '#FFCC00' : '#00FF9D';

  return (
    <div className="bg-[#121212] border border-[#262626] rounded-lg p-6" data-testid="cx-panel">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <h3 className="text-xs uppercase tracking-[0.2em] text-[#8A8A8E] flex items-center gap-2">
            <UserCheck className="w-3 h-3 text-[#00FF9D]" />
            Customer Experience — What the user feels
          </h3>
          <p className="text-[10px] text-[#8A8A8E] mt-1">
            User-facing metrics + healing-action impact deltas (30s before/after).
          </p>
        </div>
        <button
          onClick={runSynthetic}
          disabled={running}
          className="text-xs px-3 py-1.5 rounded border bg-[#00FF9D]/10 border-[#00FF9D]/40 text-[#00FF9D] hover:bg-[#00FF9D]/20 flex items-center gap-1.5 disabled:opacity-50"
          data-testid="cx-run-synthetic-btn"
        >
          <Play className="w-3 h-3" />
          {running ? 'Running…' : 'Run Synthetic User'}
        </button>
      </div>

      {/* Scorecard */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
        <ScoreTile
          label="Page Load"
          value={r30.page_load_ms != null ? r30.page_load_ms.toFixed(0) : '—'}
          suffix={r30.page_load_ms != null ? ' ms' : ''}
          color={plColor}
          sublabel="30s avg"
          testid="cx-score-page-load"
        />
        <ScoreTile
          label="Add to Cart"
          value={r30.add_to_cart_ms != null ? r30.add_to_cart_ms.toFixed(0) : '—'}
          suffix={r30.add_to_cart_ms != null ? ' ms' : ''}
          color="#5AC8FA"
          sublabel="cache-latency proxy"
          testid="cx-score-cart"
        />
        <ScoreTile
          label="Error Shown"
          value={r30.error_shown_rate != null ? r30.error_shown_rate.toFixed(2) : '—'}
          suffix={r30.error_shown_rate != null ? '%' : ''}
          color={erColor}
          sublabel="of requests"
          testid="cx-score-errors"
        />
        <ScoreTile
          label="Conversion"
          value={r30.conversion != null ? (r30.conversion * 100).toFixed(2) : '—'}
          suffix={r30.conversion != null ? '%' : ''}
          color="#FFCC00"
          sublabel="rolling rate"
          testid="cx-score-conversion"
        />
        <ScoreTile
          label="Perceived Speed"
          value={r30.perceived_speed != null ? r30.perceived_speed.toFixed(0) : '—'}
          suffix={r30.perceived_speed != null ? '/100' : ''}
          color={psColor}
          sublabel="composite UX"
          testid="cx-score-perceived"
        />
      </div>

      {/* Timeline chart */}
      {chartData.length > 1 && (
        <div style={{ width: '100%', height: 220 }} data-testid="cx-chart">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
              <XAxis dataKey="tLabel" stroke="#8A8A8E" fontSize={10} />
              <YAxis yAxisId="left" stroke="#00FF9D" fontSize={10} domain={[0, 100]} />
              <YAxis yAxisId="right" orientation="right" stroke="#FF9500" fontSize={10} />
              <Tooltip contentStyle={{ backgroundColor: '#0F0F0F', border: '1px solid #262626', fontSize: 11 }} />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Line yAxisId="left" type="monotone" dataKey="perceived" name="Perceived Speed (0-100)" stroke="#00FF9D" strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line yAxisId="right" type="monotone" dataKey="page_load" name="Page Load (ms)" stroke="#FF9500" strokeWidth={2} dot={false} isAnimationActive={false} />
              {chartAnnotations.map((a) => (
                <ReferenceLine key={`anno-${a.t_relative}-${a.action_id || ''}`} yAxisId="left" x={`${a.t_relative.toFixed(0)}s`} stroke="#00A3FF" strokeDasharray="3 3" label={{ value: '⚡', position: 'top', fill: '#00A3FF', fontSize: 12 }} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Healing Impact deltas */}
      {healingImpacts.length > 0 && (
        <div className="mt-4" data-testid="cx-healing-impacts">
          <p className="text-[10px] text-[#8A8A8E] uppercase tracking-wider mb-2 flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-[#00A3FF]" />
            Healing impact on user experience (Δ over 30s before/after)
          </p>
          <div className="space-y-1">
            {healingImpacts.map((a, i) => {
              const d = a.cx_delta;
              const plGood = (d.page_load_ms_delta || 0) < 0;
              const psGood = (d.perceived_speed_delta || 0) > 0;
              const erGood = (d.error_rate_delta || 0) < 0;
              return (
                <div key={`impact-${a.t_relative}-${a.action_id || i}`} className="flex items-center gap-2 text-[10px] font-mono px-2 py-1 bg-[#1F1F1F] rounded">
                  <span className="text-[#00A3FF]">⚡ {a.t_relative.toFixed(0)}s</span>
                  <span className="text-[#FFFFFF]">{a.action_id}</span>
                  <span className="text-[#8A8A8E]">@ {a.target_node || '-'}</span>
                  {d.page_load_ms_delta != null && (
                    <span className={plGood ? 'text-[#00FF9D]' : 'text-[#FF3B30]'}>
                      {plGood ? <TrendingDown className="w-3 h-3 inline" /> : <TrendingUp className="w-3 h-3 inline" />}
                      {' '}Page {d.page_load_ms_delta >= 0 ? '+' : ''}{d.page_load_ms_delta.toFixed(0)}ms
                    </span>
                  )}
                  {d.perceived_speed_delta != null && (
                    <span className={psGood ? 'text-[#00FF9D]' : 'text-[#FF3B30]'}>
                      {psGood ? <TrendingUp className="w-3 h-3 inline" /> : <TrendingDown className="w-3 h-3 inline" />}
                      {' '}UX {d.perceived_speed_delta >= 0 ? '+' : ''}{d.perceived_speed_delta.toFixed(1)}
                    </span>
                  )}
                  {d.error_rate_delta != null && (
                    <span className={erGood ? 'text-[#00FF9D]' : 'text-[#FF3B30]'}>
                      Err {d.error_rate_delta >= 0 ? '+' : ''}{d.error_rate_delta.toFixed(2)}%
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Synthetic user journey visualization */}
      {journey && (
        <div className="mt-4 border border-[#262626] rounded-lg p-4 bg-[#0F0F0F]" data-testid="cx-journey-card">
          <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
            <div className="flex items-center gap-2">
              {(() => {
                const Icon = VERDICT_ICON[journey.verdict] || Meh;
                return <Icon className="w-5 h-5" style={{ color: journey.verdict_color }} />;
              })()}
              <span className="text-sm font-bold" style={{ color: journey.verdict_color }}>
                {VERDICT_LABEL[journey.verdict]}
              </span>
              <span className="text-[10px] text-[#8A8A8E] font-mono">
                total {journey.total_ms.toFixed(0)}ms · avg {journey.avg_latency_ms.toFixed(0)}ms · UX {journey.avg_perceived_speed.toFixed(0)}/100 · SRI {journey.sri_at_run}
              </span>
            </div>
            {journey.errors_seen > 0 && (
              <span className="text-[10px] px-2 py-0.5 rounded bg-[#FF3B30]/20 text-[#FF3B30]">
                {journey.errors_seen} error{journey.errors_seen === 1 ? '' : 's'} shown
              </span>
            )}
          </div>
          <div className="space-y-1" data-testid="cx-journey-steps">
            {journey.steps.map((s, i) => {
              const visible = i <= animStep;
              const stepColor = !s.success ? '#FF3B30' : s.perceived_speed >= 85 ? '#00FF9D' : s.perceived_speed >= 60 ? '#FFCC00' : '#FF9500';
              return (
                <div
                  key={`${s.name}-${s.method}-${s.path}-${i}`}
                  className={`flex items-center gap-3 px-3 py-2 rounded transition-all duration-300 ${visible ? 'opacity-100 translate-x-0' : 'opacity-0 -translate-x-2'}`}
                  style={{ backgroundColor: visible ? '#1F1F1F' : 'transparent' }}
                  data-testid={`cx-journey-step-${i}`}
                >
                  <Gauge className="w-3 h-3" style={{ color: stepColor }} />
                  <div className="flex-1 flex items-center gap-2">
                    <span className="text-xs text-[#FFFFFF] truncate">{s.name}</span>
                    <span className="text-[10px] text-[#8A8A8E] font-mono">{s.method}</span>
                    <span className="text-[10px] text-[#8A8A8E] font-mono truncate">{s.path}</span>
                  </div>
                  <span className="text-[10px] font-mono" style={{ color: stepColor }}>
                    {s.status_code || '—'} · {s.latency_ms.toFixed(0)}ms · UX {s.perceived_speed.toFixed(0)}
                  </span>
                </div>
              );
            })}
          </div>
          <p className="text-[10px] text-[#8A8A8E] italic mt-2">
            This journey used real API calls. Run again after an auto-heal to see the same path improve.
          </p>
        </div>
      )}

      {!journey && (
        <div className="mt-4 p-3 bg-[#1F1F1F] rounded text-center text-[10px] text-[#8A8A8E] italic">
          Click <strong>Run Synthetic User</strong> to see a real customer's journey through the portal.
        </div>
      )}
    </div>
  );
}
