import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Skull } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Implements Eq. 7 from the SRI/SAI paper:
 *   d(SRI)/dt ≈ 0  ∧  SRI < SRI_threshold  →  non-recoverable state.
 * Polls /api/healing/trend every 5s and renders a loud banner when triggered.
 */
export function NonRecoverableBanner() {
  const [trend, setTrend] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const { data } = await axios.get(`${API}/healing/trend`, { withCredentials: true });
        if (!cancelled) setTrend(data);
      } catch (e) { /* silent */ }
    };
    load();
    const iv = setInterval(load, 5000);
    return () => { cancelled = true; clearInterval(iv); };
  }, []);

  if (!trend?.non_recoverable) return null;

  const c = trend.non_recoverable_criterion || {};
  return (
    <div className="bg-[#FF3B30] border-y-2 border-[#FF3B30]/80 px-6 py-3 animate-pulse" data-testid="non-recoverable-banner">
      <div className="max-w-[1600px] mx-auto flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Skull className="w-6 h-6 text-white" />
          <div>
            <div className="text-white font-bold uppercase tracking-wider text-sm">
              Non-Recoverable State Detected
            </div>
            <div className="text-white/90 text-xs font-mono">
              SRI={trend.current_sri.toFixed(4)} &lt; {c.sri_threshold} ∧ |dSRI/dt|={Math.abs(trend.velocity).toFixed(5)} &lt; {c.plateau_eps} (Eq. 7, SRI/SAI paper)
            </div>
          </div>
        </div>
        <div className="text-white/90 text-xs">
          Auto-healing escalation engaged
        </div>
      </div>
    </div>
  );
}
