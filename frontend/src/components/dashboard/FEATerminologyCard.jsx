import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { BookOpen } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Side-by-side mapping of strict-FEA terminology to software-friendly
 * names so the topology heatmap reads correctly to both reliability
 * engineers and structural-FEA folks.
 */
export function FEATerminologyCard() {
  const [data, setData] = useState(null);

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/healing/fea`, { params: { granularity: 'service' }, withCredentials: true })
      .then(({ data }) => { if (!cancelled) setData(data); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const terminology = data?.terminology || {};
  const equation = data?.fea_equation || 'K · u = F  →  σ = K · ε';

  return (
    <div className="bg-[#121212] border border-[#262626] rounded-lg p-6" data-testid="fea-terminology-card">
      <h3 className="text-xs uppercase tracking-[0.2em] text-[#8A8A8E] flex items-center gap-2 mb-3">
        <BookOpen className="w-3 h-3 text-[#5AC8FA]" />
        FEA in the Strict Sense — Terminology Map
      </h3>
      <div className="bg-[#0F0F0F] rounded-lg p-3 mb-3 border border-[#5AC8FA]/30">
        <p className="text-[10px] text-[#8A8A8E] uppercase tracking-wider mb-1">Governing equation</p>
        <p className="text-[11px] font-['JetBrains_Mono'] text-[#5AC8FA] break-all">{equation}</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px]">
        {Object.entries(terminology).map(([feaTerm, softwareTerm]) => (
          <div key={feaTerm} className="flex items-start gap-2 p-2 bg-[#1F1F1F] rounded" data-testid={`fea-term-${feaTerm.split(' ')[0]}`}>
            <span className="text-[#FFCC00] font-['JetBrains_Mono'] flex-shrink-0 min-w-[100px]">{feaTerm}</span>
            <span className="text-[#8A8A8E]">↔</span>
            <span className="text-[#FFFFFF]">{softwareTerm}</span>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-[#8A8A8E] mt-3 italic">
        Every API field carries both names — the topology heatmap is doing real continuum-mechanics math (assembled stiffness, displacement field, von-Mises stress, yield check) on the service mesh.
      </p>
    </div>
  );
}
