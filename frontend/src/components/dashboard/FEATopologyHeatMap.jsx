import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import axios from 'axios';
import { AlertTriangle, Activity, Zap, Shield, ZoomIn, ZoomOut, Maximize2, ChevronsDownUp, Flame, Square } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Default service node layout (pentagon-ish) — used as fallback before the
// backend topology schema loads. Kept identical to backend TOPOLOGY_SCHEMA
// so the map renders correctly even if /healing/topology/schema is slow.
const DEFAULT_NODE_POS = {
  API:     { x: 300, y: 80 },
  Cache:   { x: 110, y: 200 },
  DB:      { x: 210, y: 340 },
  Queue:   { x: 410, y: 340 },
  Backend: { x: 500, y: 200 },
};

const DEFAULT_EDGES = [
  ['API', 'Cache'], ['API', 'DB'], ['API', 'Queue'],
  ['Cache', 'DB'], ['Queue', 'Backend'],
];

// Layout sub-components around their parent service (expanded halo layout)
function layoutComponents(components, centerX, centerY, expandedRadius) {
  const n = components.length;
  if (n === 0) return {};
  const positions = {};
  const angleStep = (Math.PI * 2) / n;
  // Start from top (-PI/2) for deterministic visual
  const startAngle = -Math.PI / 2;
  components.forEach((c, i) => {
    const angle = startAngle + i * angleStep;
    positions[c.component] = {
      x: centerX + Math.cos(angle) * expandedRadius,
      y: centerY + Math.sin(angle) * expandedRadius,
    };
  });
  return positions;
}

// Layout tier-3 endpoint dots in a tight ring around the parent component
function layoutEndpoints(endpoints, centerX, centerY, ringRadius) {
  const n = endpoints.length;
  if (n === 0) return {};
  const positions = {};
  const angleStep = (Math.PI * 2) / Math.max(n, 1);
  const startAngle = -Math.PI / 2 + 0.1; // small offset so first leaf isn't behind connector line
  endpoints.forEach((ep, i) => {
    const angle = startAngle + i * angleStep;
    positions[ep.endpoint] = {
      x: centerX + Math.cos(angle) * ringRadius,
      y: centerY + Math.sin(angle) * ringRadius,
    };
  });
  return positions;
}

function stressColor(val, max) {
  const ratio = max > 0 ? Math.min(val / max, 1) : 0;
  if (ratio < 0.3) return '#00FF9D';
  if (ratio < 0.6) return '#FFCC00';
  if (ratio < 0.8) return '#FF9500';
  return '#FF3B30';
}

function strainColor(val, max) {
  const ratio = max > 0 ? Math.min(val / max, 1) : 0;
  if (ratio < 0.25) return '#00FF9D';
  if (ratio < 0.5) return '#FFCC00';
  if (ratio < 0.75) return '#FF9500';
  return '#FF3B30';
}

function strainWidth(val, max) {
  const ratio = max > 0 ? Math.min(val / max, 1) : 0;
  return 2 + ratio * 6;
}

const BASE_VB = { x: 0, y: 0, w: 600, h: 420 };

export function FEATopologyHeatMap({ isRunning }) {
  const [fea, setFea] = useState(null);
  const [schema, setSchema] = useState(null);
  const [phaseState, setPhaseState] = useState(null); // iter 38: per-node eutectic distance
  const [expandedNodes, setExpandedNodes] = useState({}); // { API: true, DB: true }
  const [expandedComponents, setExpandedComponents] = useState({}); // { "API.auth": true }
  const [hoveredNode, setHoveredNode] = useState(null);
  const [hoveredComp, setHoveredComp] = useState(null);
  const [hoveredEndpoint, setHoveredEndpoint] = useState(null);
  const [hoveredEdge, setHoveredEdge] = useState(null);
  const [viewBox, setViewBox] = useState(BASE_VB);
  const [isPanning, setIsPanning] = useState(false);
  const panStart = useRef({ x: 0, y: 0, vbX: 0, vbY: 0 });
  const svgRef = useRef(null);

  // --- Fault propagation (Chaos Mode) ---
  // When chaosMode is true, clicking a node injects a fault and animates
  // the Laplacian-diffusion timeline returned by /api/healing/fault-propagation.
  const [chaosMode, setChaosMode] = useState(false);
  const [propagation, setPropagation] = useState(null);   // { source, timeline, node_summary }
  const [animIndex, setAnimIndex] = useState(0);
  const animTimerRef = useRef(null);

  // --- Auto-Dampener ---
  // When autoArrestMode is on, a fault injection automatically calls
  // /api/healing/auto-dampen-wave with auto_execute=true and renders the
  // BEFORE/AFTER simulation. The "Dampen Now" button does the same thing
  // on demand for an existing propagation.
  const [autoArrestMode, setAutoArrestMode] = useState(false);
  const [dampener, setDampener] = useState(null);          // { wave_arrested, cut_edge, recommended_action, wave_metrics, ... }
  const [showDampenedView, setShowDampenedView] = useState(false);

  // Topology schema (service list, positions, inter-edges) — fetched once,
  // falls back to built-in defaults if unavailable.
  const nodePos = useMemo(() => {
    if (!schema?.services) return DEFAULT_NODE_POS;
    return schema.services.reduce((acc, s) => {
      acc[s.name] = s.position || DEFAULT_NODE_POS[s.name] || { x: 300, y: 200 };
      return acc;
    }, {});
  }, [schema]);

  const edges = useMemo(() => {
    if (!schema?.inter_edges) return DEFAULT_EDGES;
    return schema.inter_edges;
  }, [schema]);

  const hasExpanded = Object.values(expandedNodes).some(Boolean);
  const hasComponentExpanded = Object.values(expandedComponents).some(Boolean);
  const granularity = hasComponentExpanded ? 'endpoint' : (hasExpanded ? 'component' : 'service');

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/healing/topology/schema`, { withCredentials: true })
      .then(({ data }) => { if (!cancelled) setSchema(data); })
      .catch(() => { /* fallback to defaults */ });
    return () => { cancelled = true; };
  }, []);

  const fetchFEA = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/healing/fea`, {
        params: { granularity },
        withCredentials: true,
      });
      setFea(data);
    } catch (e) { /* silent */ }
  }, [granularity]);

  // iter 38: per-node eutectic distance + active capacity boosts —
  // surface the eutectic-pull metric on every service node so operators
  // can SEE how far each component is from Ψ_s and which ones are
  // currently scaled out.
  const fetchPhaseState = useCallback(async () => {
    try {
      const [{ data: phase }, { data: heal }] = await Promise.all([
        axios.get(`${API}/phase/state`, { withCredentials: true }),
        axios.get(`${API}/healing/status`, { withCredentials: true }),
      ]);
      setPhaseState({
        per_node: phase.per_node || {},
        eutectic_target: phase.flags?.eutectic_target || null,
        capacity_boosts: heal.capacity_boosts || {},
      });
    } catch (e) { /* silent — heat map still works without it */ }
  }, []);

  useEffect(() => {
    fetchPhaseState();
    if (!isRunning) return;
    const iv = setInterval(fetchPhaseState, 5000);
    return () => clearInterval(iv);
  }, [isRunning, fetchPhaseState]);

  useEffect(() => {
    fetchFEA();
    if (!isRunning) return;
    const iv = setInterval(fetchFEA, 5000);
    return () => clearInterval(iv);
  }, [isRunning, fetchFEA]);

  const toggleExpand = useCallback((nodeName) => {
    setExpandedNodes(prev => ({ ...prev, [nodeName]: !prev[nodeName] }));
  }, []);

  const toggleExpandComponent = useCallback((compName) => {
    setExpandedComponents(prev => ({ ...prev, [compName]: !prev[compName] }));
  }, []);

  const expandAll = useCallback(() => {
    setExpandedNodes(Object.keys(nodePos).reduce((acc, k) => ({ ...acc, [k]: true }), {}));
  }, [nodePos]);

  const collapseAll = useCallback(() => {
    setExpandedNodes({});
    setExpandedComponents({});
  }, []);

  // --- Chaos: inject a fault at a node and animate propagation ---
  const stopAnimation = useCallback(() => {
    if (animTimerRef.current) {
      clearInterval(animTimerRef.current);
      animTimerRef.current = null;
    }
  }, []);

  const injectFault = useCallback(async (sourceName, gran = 'service') => {
    stopAnimation();
    setDampener(null);
    setShowDampenedView(false);
    try {
      const { data } = await axios.post(`${API}/healing/fault-propagation`, {
        source: sourceName,
        fault_strength: 1.0,
        steps: 30,
        dt: 0.5,
        granularity: gran,
      }, { withCredentials: true });
      setPropagation(data);
      setAnimIndex(0);
      toast.error(`💥 Fault injected at ${sourceName} — watching ${data.mesh_size} nodes propagate`, { duration: 2500 });
      // Animate ~80ms per frame → 30 frames in ~2.4s
      animTimerRef.current = setInterval(() => {
        setAnimIndex(prev => {
          const next = prev + 1;
          if (next >= data.timeline.length) {
            stopAnimation();
            return data.timeline.length - 1;
          }
          return next;
        });
      }, 90);

      // Auto-Arrest: fire dampener immediately
      if (autoArrestMode) {
        try {
          const { data: damp } = await axios.post(`${API}/healing/auto-dampen-wave`, {
            source: sourceName,
            fault_strength: 1.0,
            steps: 30,
            dt: 0.5,
            granularity: gran,
            critical_arrival_threshold: 0.05,
            auto_execute: true,
          }, { withCredentials: true });
          setDampener(damp);
          if (damp.wave_arrested) {
            const pct = damp.wave_metrics?.arrest_percentage || 0;
            const cd = damp.execution_result?.reason === 'cooldown';
            if (cd) {
              toast.warning(`🌊 Recommendation: ${damp.recommended_action.action_id} (cooling down ${damp.execution_result.cooldown_remaining_seconds?.toFixed(0)}s)`, { duration: 4000 });
            } else if (pct > 1) {
              toast.success(`🌊 Auto-arrested ${pct.toFixed(0)}% via ${damp.recommended_action.action_id} on ${damp.cut_edge.source}→${damp.cut_edge.target}`, { duration: 4000 });
            } else {
              toast.success(`🌊 Dampener applied: ${damp.recommended_action.action_id} on ${damp.cut_edge.source}→${damp.cut_edge.target}`, { duration: 4000 });
            }
          }
        } catch (e2) {
          toast.error('Auto-dampen failed: ' + (e2?.response?.data?.detail || e2.message));
        }
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Fault injection failed');
    }
  }, [stopAnimation, autoArrestMode]);

  const dampenWaveNow = useCallback(async () => {
    if (!propagation) return;
    try {
      const { data } = await axios.post(`${API}/healing/auto-dampen-wave`, {
        source: propagation.source,
        fault_strength: propagation.fault_strength,
        steps: propagation.steps,
        dt: propagation.dt,
        granularity: propagation.granularity,
        critical_arrival_threshold: 0.05,
        auto_execute: true,
      }, { withCredentials: true });
      setDampener(data);
      setShowDampenedView(true);
      const pct = data.wave_metrics?.arrest_percentage || 0;
      const cd = data.execution_result?.reason === 'cooldown';
      if (data.wave_arrested) {
        if (cd) {
          toast.warning(`🌊 Recommendation: ${data.recommended_action.action_id} (cooling down ${data.execution_result.cooldown_remaining_seconds?.toFixed(0)}s)`, { duration: 4000 });
        } else if (pct > 1) {
          toast.success(`🌊 Wave arrested ${pct.toFixed(0)}% at ${data.cut_edge.source}→${data.cut_edge.target}`, { duration: 4000 });
        } else {
          toast.success(`🌊 Dampener applied at ${data.cut_edge.source}→${data.cut_edge.target}`, { duration: 4000 });
        }
      } else {
        toast.warning(`No critical arrivals — wave not arrested (reason: ${data.reason})`);
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Dampen failed');
    }
  }, [propagation]);

  const clearFault = useCallback(() => {
    stopAnimation();
    setPropagation(null);
    setDampener(null);
    setShowDampenedView(false);
    setAnimIndex(0);
  }, [stopAnimation]);

  useEffect(() => () => stopAnimation(), [stopAnimation]);

  // Current per-node fault intensity (during animation)
  const faultMap = useMemo(() => {
    // If user toggled the dampened view and we have a dampener result, show that instead
    const source = (showDampenedView && dampener?.dampened?.timeline) ? dampener.dampened.timeline : propagation?.timeline;
    if (!source?.length) return {};
    const idx = Math.min(animIndex, source.length - 1);
    return source[idx]?.x || {};
  }, [propagation, animIndex, showDampenedView, dampener]);

  // Zoom controls
  const zoom = useCallback((factor, cx, cy) => {
    setViewBox(vb => {
      const newW = Math.max(150, Math.min(1800, vb.w * factor));
      const newH = Math.max(105, Math.min(1260, vb.h * factor));
      // zoom toward (cx, cy)
      const ratio = newW / vb.w;
      const newX = cx - (cx - vb.x) * ratio;
      const newY = cy - (cy - vb.y) * ratio;
      return { x: newX, y: newY, w: newW, h: newH };
    });
  }, []);

  const resetView = useCallback(() => setViewBox(BASE_VB), []);

  const handleWheel = useCallback((e) => {
    e.preventDefault();
    if (!svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const mx = ((e.clientX - rect.left) / rect.width) * viewBox.w + viewBox.x;
    const my = ((e.clientY - rect.top) / rect.height) * viewBox.h + viewBox.y;
    const factor = e.deltaY > 0 ? 1.1 : 0.9;
    zoom(factor, mx, my);
  }, [viewBox, zoom]);

  // Attach non-passive wheel listener so preventDefault works in React 18+
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => el.removeEventListener('wheel', handleWheel);
  }, [handleWheel]);

  const onMouseDown = (e) => {
    if (e.button !== 0) return;
    // Only pan when clicking empty space
    if (e.target === svgRef.current) {
      setIsPanning(true);
      panStart.current = { x: e.clientX, y: e.clientY, vbX: viewBox.x, vbY: viewBox.y };
    }
  };

  const onMouseMove = (e) => {
    if (!isPanning || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const dx = ((e.clientX - panStart.current.x) / rect.width) * viewBox.w;
    const dy = ((e.clientY - panStart.current.y) / rect.height) * viewBox.h;
    setViewBox(vb => ({ ...vb, x: panStart.current.vbX - dx, y: panStart.current.vbY - dy }));
  };

  const endPan = () => setIsPanning(false);

  // Derived data
  const { nodeMap, edgeMap, maxVM, maxStrain, maxCompVM, yieldNodes, weakestEdge } = useMemo(() => {
    if (!fea) return { nodeMap: {}, edgeMap: {}, maxVM: 0.01, maxStrain: 0.01, maxCompVM: 0.01, yieldNodes: [], weakestEdge: null };
    const nm = {};
    (fea.elements || []).forEach(e => { nm[e.node] = e; });
    const em = {};
    (fea.edge_analysis || []).forEach(e => { em[`${e.source}-${e.target}`] = e; });
    const mVM = fea.max_von_mises || 0.01;
    const mStrain = Math.max(...(fea.edge_analysis || []).map(e => e.edge_strain), 0.01);
    let mCompVM = 0.01;
    (fea.elements || []).forEach(svc => {
      (svc.components || []).forEach(c => {
        if (c.von_mises_stress > mCompVM) mCompVM = c.von_mises_stress;
      });
    });
    return {
      nodeMap: nm,
      edgeMap: em,
      maxVM: mVM,
      maxStrain: mStrain,
      maxCompVM: mCompVM,
      yieldNodes: fea.yield_nodes || [],
      weakestEdge: fea.edge_analysis?.[0],
    };
  }, [fea]);

  if (!fea) {
    return (
      <div className="h-[420px] flex items-center justify-center text-[#8A8A8E] text-sm" data-testid="fea-heatmap-loading">
        Loading FEA topology...
      </div>
    );
  }

  const compYieldThreshold = fea.component_yield_threshold || fea.yield_threshold || 0;

  return (
    <div className="relative">
      {/* Legend + Controls */}
      <div className="flex items-center gap-4 mb-3 text-[10px] text-[#8A8A8E] flex-wrap">
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-[#00FF9D]" /> Healthy</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-[#FFCC00]" /> Moderate</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-[#FF9500]" /> Stressed</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-[#FF3B30]" /> Critical</span>
        <span className="flex items-center gap-1 ml-2 text-[#8A8A8E]/80 italic">
          Double-click a service to expand components · double-click a component to drill into endpoints
        </span>
        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={() => zoom(0.85, viewBox.x + viewBox.w / 2, viewBox.y + viewBox.h / 2)}
            className="p-1.5 bg-[#1F1F1F] hover:bg-[#2A2A2A] rounded border border-[#262626] text-[#8A8A8E]"
            data-testid="fea-zoom-in"
            title="Zoom in"
          >
            <ZoomIn className="w-3 h-3" />
          </button>
          <button
            onClick={() => zoom(1.15, viewBox.x + viewBox.w / 2, viewBox.y + viewBox.h / 2)}
            className="p-1.5 bg-[#1F1F1F] hover:bg-[#2A2A2A] rounded border border-[#262626] text-[#8A8A8E]"
            data-testid="fea-zoom-out"
            title="Zoom out"
          >
            <ZoomOut className="w-3 h-3" />
          </button>
          <button
            onClick={resetView}
            className="p-1.5 bg-[#1F1F1F] hover:bg-[#2A2A2A] rounded border border-[#262626] text-[#8A8A8E]"
            data-testid="fea-reset-view"
            title="Reset view"
          >
            <Maximize2 className="w-3 h-3" />
          </button>
          {hasExpanded ? (
            <button
              onClick={collapseAll}
              className="px-2 py-1 bg-[#1F1F1F] hover:bg-[#2A2A2A] rounded border border-[#262626] text-[#8A8A8E] flex items-center gap-1"
              data-testid="fea-collapse-all"
            >
              <ChevronsDownUp className="w-3 h-3" /> Collapse
            </button>
          ) : (
            <button
              onClick={expandAll}
              className="px-2 py-1 bg-[#1F1F1F] hover:bg-[#2A2A2A] rounded border border-[#262626] text-[#8A8A8E] flex items-center gap-1"
              data-testid="fea-expand-all"
            >
              <ChevronsDownUp className="w-3 h-3 rotate-180" /> Expand All
            </button>
          )}
          <button
            onClick={() => { setChaosMode(m => !m); if (chaosMode) clearFault(); }}
            className={`px-2 py-1 rounded border flex items-center gap-1 transition ${
              chaosMode
                ? 'bg-[#FF3B30]/20 border-[#FF3B30] text-[#FF3B30]'
                : 'bg-[#1F1F1F] hover:bg-[#2A2A2A] border-[#262626] text-[#8A8A8E]'
            }`}
            data-testid="fea-chaos-toggle"
            title="Toggle Chaos mode — click a node to inject a fault"
          >
            <Flame className="w-3 h-3" /> {chaosMode ? 'Chaos: ON' : 'Chaos'}
          </button>
          <button
            onClick={() => setAutoArrestMode(m => !m)}
            className={`px-2 py-1 rounded border flex items-center gap-1 transition ${
              autoArrestMode
                ? 'bg-[#00FF9D]/20 border-[#00FF9D] text-[#00FF9D]'
                : 'bg-[#1F1F1F] hover:bg-[#2A2A2A] border-[#262626] text-[#8A8A8E]'
            }`}
            data-testid="fea-auto-arrest-toggle"
            title="Auto-Arrest: when ON, every fault is automatically dampened"
          >
            <Shield className="w-3 h-3" /> {autoArrestMode ? 'Auto-Arrest: ON' : 'Auto-Arrest'}
          </button>
          {propagation && (
            <button
              onClick={clearFault}
              className="px-2 py-1 bg-[#1F1F1F] hover:bg-[#2A2A2A] rounded border border-[#262626] text-[#8A8A8E] flex items-center gap-1"
              data-testid="fea-clear-fault"
            >
              <Square className="w-3 h-3" /> Clear
            </button>
          )}
        </div>
      </div>

      {/* SVG Topology */}
      <svg
        ref={svgRef}
        viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`}
        className="w-full h-[420px] select-none"
        style={{ cursor: isPanning ? 'grabbing' : 'grab', background: 'transparent', touchAction: 'none' }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={endPan}
        onMouseLeave={endPan}
        data-testid="fea-heatmap"
      >
        <defs>
          <filter id="glow-red">
            <feGaussianBlur stdDeviation="6" result="coloredBlur"/>
            <feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <filter id="glow-green">
            <feGaussianBlur stdDeviation="4" result="coloredBlur"/>
            <feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <radialGradient id="expanded-bg" cx="50%" cy="50%">
            <stop offset="0%" stopColor="#00FF9D" stopOpacity="0.06" />
            <stop offset="70%" stopColor="#00FF9D" stopOpacity="0.02" />
            <stop offset="100%" stopColor="#00FF9D" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* Inter-service edges */}
        {edges.map(([src, tgt]) => {
          const key = `${src}-${tgt}`;
          const edge = edgeMap[key] || edgeMap[`${tgt}-${src}`] || {};
          const strain = edge.edge_strain || 0;
          const color = strainColor(strain, maxStrain);
          const width = strainWidth(strain, maxStrain);
          const p1 = nodePos[src];
          const p2 = nodePos[tgt];
          if (!p1 || !p2) return null;
          const isHovered = hoveredEdge === key;
          const isFragile = weakestEdge && (
            (weakestEdge.source === src && weakestEdge.target === tgt) ||
            (weakestEdge.source === tgt && weakestEdge.target === src)
          );

          return (
            <g key={key}>
              <line
                x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y}
                stroke={color}
                strokeWidth={isHovered ? width + 2 : width}
                strokeOpacity={isHovered ? 1 : 0.7}
                strokeDasharray={isFragile ? '8 4' : 'none'}
                style={{ cursor: 'pointer', transition: 'stroke-opacity 0.3s, stroke-width 0.3s' }}
                onMouseEnter={() => setHoveredEdge(key)}
                onMouseLeave={() => setHoveredEdge(null)}
              />
              {isFragile && (
                <g>
                  <circle cx={(p1.x + p2.x) / 2} cy={(p1.y + p2.y) / 2} r="10" fill="#FF3B30" fillOpacity="0.15" />
                  <text x={(p1.x + p2.x) / 2} y={(p1.y + p2.y) / 2 + 3} textAnchor="middle" fill="#FF3B30" fontSize="9" fontWeight="bold">!</text>
                </g>
              )}
              {isHovered && (
                <g pointerEvents="none">
                  <rect x={(p1.x + p2.x) / 2 - 60} y={(p1.y + p2.y) / 2 - 50} width="120" height="42" rx="4" fill="#1F1F1F" stroke="#262626" />
                  <text x={(p1.x + p2.x) / 2} y={(p1.y + p2.y) / 2 - 36} textAnchor="middle" fill="#8A8A8E" fontSize="8">
                    Fragility: {strain.toFixed(4)} | Strength: {(edge.stiffness || 0).toFixed(2)}
                  </text>
                  <text x={(p1.x + p2.x) / 2} y={(p1.y + p2.y) / 2 - 26} textAnchor="middle" fill="#FFCC00" fontSize="8">
                    Cascade risk: {((edge.cascade_risk || 0) * 100).toFixed(0)}%
                  </text>
                  <text x={(p1.x + p2.x) / 2} y={(p1.y + p2.y) / 2 - 14} textAnchor="middle" fill={color} fontSize="8" fontWeight="bold">
                    {strain > maxStrain * 0.75 ? 'FRAGILE' : strain > maxStrain * 0.5 ? 'Degraded' : 'Healthy'}
                  </text>
                </g>
              )}
            </g>
          );
        })}

        {/* Nodes — with inline component expansion */}
        {Object.entries(nodePos).map(([name, pos]) => {
          const node = nodeMap[name] || {};
          const vm = node.von_mises_stress || 0;
          const isYield = node.yield_exceeded || false;
          // Honour incident-edge strain when coloring: a healthy node connected
          // by a fragile edge should still glow warm (operator clarity).
          const incidentEdgeStrain = (fea?.edge_analysis || [])
            .filter(e => e.source === name || e.target === name)
            .reduce((m, e) => Math.max(m, e.edge_strain || 0), 0);
          const colorByPressure = stressColor(vm, maxVM);
          const colorByEdge = strainColor(incidentEdgeStrain, maxStrain);
          // Take the warmer of the two (whichever is closer to red on the scale)
          const colorOrder = ['#00FF9D', '#FFCC00', '#FF9500', '#FF3B30'];
          const color = colorOrder.indexOf(colorByEdge) > colorOrder.indexOf(colorByPressure) ? colorByEdge : colorByPressure;
          const isExpanded = !!expandedNodes[name];
          const components = node.components || [];
          const intraEdges = node.intra_edges || [];
          const baseRadius = isYield ? 28 : 22;
          // Ring radius scales modestly with component count so 8–9 components don't overlap
          const expandedRingRadius = Math.max(70, 55 + components.length * 4);
          const radius = isExpanded ? baseRadius - 6 : baseRadius;
          const isHovered = hoveredNode === name;
          const faultIntensity = faultMap[name] || 0;
          const isFaultSource = propagation?.source === name;

          const compPositions = isExpanded ? layoutComponents(components, pos.x, pos.y, expandedRingRadius) : {};

          return (
            <g
              key={name}
              style={{ cursor: chaosMode ? 'crosshair' : 'pointer' }}
              onClick={(e) => {
                if (chaosMode) {
                  e.stopPropagation();
                  injectFault(name, 'service');
                }
              }}
              onDoubleClick={(e) => { e.stopPropagation(); if (!chaosMode) toggleExpand(name); }}
              onMouseEnter={() => setHoveredNode(name)}
              onMouseLeave={() => setHoveredNode(null)}
              data-testid={`fea-node-${name}`}
            >
              {/* Fault propagation overlay (intensity-based amber→red glow) */}
              {faultIntensity > 0.02 && (
                <g pointerEvents="none">
                  <circle
                    cx={pos.x} cy={pos.y}
                    r={radius + 6 + faultIntensity * 12}
                    fill="#FF3B30"
                    fillOpacity={0.05 + faultIntensity * 0.35}
                  />
                  {isFaultSource && (
                    <circle cx={pos.x} cy={pos.y} r={radius + 18} fill="none" stroke="#FF3B30" strokeWidth="2" strokeOpacity="0.8">
                      <animate attributeName="r" from={radius + 12} to={radius + 32} dur="0.9s" repeatCount="indefinite" />
                      <animate attributeName="stroke-opacity" from="0.9" to="0" dur="0.9s" repeatCount="indefinite" />
                    </circle>
                  )}
                  <text
                    x={pos.x} y={pos.y - radius - 16}
                    textAnchor="middle"
                    fill="#FF3B30"
                    fontSize="9"
                    fontWeight="bold"
                    fontFamily="'JetBrains Mono', monospace"
                  >
                    {isFaultSource ? '🔥 SOURCE' : `x=${faultIntensity.toFixed(2)}`}
                  </text>
                </g>
              )}

              {/* Expanded halo background */}
              {isExpanded && (
                <circle cx={pos.x} cy={pos.y} r={expandedRingRadius + 25} fill="url(#expanded-bg)" stroke={color} strokeOpacity="0.35" strokeWidth="1" strokeDasharray="4 3" />
              )}

              {/* Pulse ring for critical */}
              {isYield && !isExpanded && (
                <circle cx={pos.x} cy={pos.y} r={radius + 8} fill="none" stroke="#FF3B30" strokeWidth="1.5" strokeOpacity="0.4">
                  <animate attributeName="r" from={radius + 4} to={radius + 16} dur="1.5s" repeatCount="indefinite" />
                  <animate attributeName="stroke-opacity" from="0.5" to="0" dur="1.5s" repeatCount="indefinite" />
                </circle>
              )}

              {/* Intra-service edges (only when expanded) */}
              {isExpanded && intraEdges.map((e, idx) => {
                const sp = compPositions[e.source];
                const tp = compPositions[e.target];
                if (!sp || !tp) return null;
                const eColor = strainColor(e.edge_strain || 0, maxStrain || 0.01);
                return (
                  <line
                    key={`${name}-intra-${idx}`}
                    x1={sp.x} y1={sp.y} x2={tp.x} y2={tp.y}
                    stroke={eColor}
                    strokeWidth={strainWidth(e.edge_strain || 0, maxStrain || 0.01) * 0.6}
                    strokeOpacity="0.6"
                    strokeDasharray="2 2"
                  />
                );
              })}

              {/* Component sub-nodes (when expanded) */}
              {isExpanded && components.map((c) => {
                const cp = compPositions[c.component];
                if (!cp) return null;
                const cColor = stressColor(c.von_mises_stress, maxCompVM);
                const cIsYield = c.yield_exceeded;
                const cIsHovered = hoveredComp === c.component;
                const cFault = faultMap[c.component] || 0;
                const cIsFaultSrc = propagation?.source === c.component;
                const cIsExpanded = !!expandedComponents[c.component];
                const endpoints = c.endpoints || [];
                const endpointEdges = c.endpoint_edges || [];
                const endpointRingRadius = 22; // tight cluster around component
                const compBaseR = cIsExpanded ? 9 : (cIsHovered ? 14 : 12);
                const epPositions = cIsExpanded ? layoutEndpoints(endpoints, cp.x, cp.y, endpointRingRadius) : {};
                return (
                  <g
                    key={c.component}
                    style={{ cursor: chaosMode ? 'crosshair' : 'pointer' }}
                    onClick={(ev) => {
                      if (chaosMode) {
                        ev.stopPropagation();
                        injectFault(c.component, 'component');
                      }
                    }}
                    onDoubleClick={(ev) => {
                      ev.stopPropagation();
                      if (!chaosMode) toggleExpandComponent(c.component);
                    }}
                    onMouseEnter={(ev) => { ev.stopPropagation(); setHoveredComp(c.component); }}
                    onMouseLeave={() => setHoveredComp(null)}
                    data-testid={`fea-component-${c.component}`}
                  >
                    {/* Component fault overlay */}
                    {cFault > 0.02 && (
                      <g pointerEvents="none">
                        <circle cx={cp.x} cy={cp.y} r={12 + cFault * 10} fill="#FF3B30" fillOpacity={0.05 + cFault * 0.4} />
                        {cIsFaultSrc && (
                          <circle cx={cp.x} cy={cp.y} r="20" fill="none" stroke="#FF3B30" strokeWidth="1.5" strokeOpacity="0.9">
                            <animate attributeName="r" from="14" to="26" dur="0.9s" repeatCount="indefinite" />
                            <animate attributeName="stroke-opacity" from="1" to="0" dur="0.9s" repeatCount="indefinite" />
                          </circle>
                        )}
                      </g>
                    )}
                    {/* Connector line from parent to component */}
                    <line x1={pos.x} y1={pos.y} x2={cp.x} y2={cp.y}
                      stroke={cColor} strokeOpacity="0.25" strokeWidth="1" strokeDasharray="1 2" />
                    {cIsYield && !cIsExpanded && (
                      <circle cx={cp.x} cy={cp.y} r="18" fill="none" stroke="#FF3B30" strokeWidth="1" strokeOpacity="0.45">
                        <animate attributeName="r" from="14" to="22" dur="1.5s" repeatCount="indefinite" />
                        <animate attributeName="stroke-opacity" from="0.6" to="0" dur="1.5s" repeatCount="indefinite" />
                      </circle>
                    )}

                    {/* Endpoint ring background (when drilled-in) */}
                    {cIsExpanded && endpoints.length > 0 && (
                      <circle cx={cp.x} cy={cp.y} r={endpointRingRadius + 8}
                        fill="none"
                        stroke={cColor}
                        strokeOpacity="0.25"
                        strokeWidth="0.6"
                        strokeDasharray="2 3" />
                    )}

                    {/* Endpoint-level edges (intra-component) */}
                    {cIsExpanded && endpointEdges.map((ee, idx) => {
                      const ep1 = epPositions[ee.source];
                      const ep2 = epPositions[ee.target];
                      if (!ep1 || !ep2) return null;
                      return (
                        <line key={`${c.component}-eedge-${idx}`}
                          x1={ep1.x} y1={ep1.y} x2={ep2.x} y2={ep2.y}
                          stroke={cColor} strokeOpacity="0.3" strokeWidth="0.7" />
                      );
                    })}

                    {/* Endpoint leaf dots (tier-3) */}
                    {cIsExpanded && endpoints.map((ep) => {
                      const epp = epPositions[ep.endpoint];
                      if (!epp) return null;
                      const epColor = stressColor(ep.von_mises_stress, maxCompVM || 0.01);
                      const epHovered = hoveredEndpoint === ep.endpoint;
                      const epYield = ep.yield_exceeded;
                      return (
                        <g key={ep.endpoint}
                           onMouseEnter={(ev) => { ev.stopPropagation(); setHoveredEndpoint(ep.endpoint); }}
                           onMouseLeave={() => setHoveredEndpoint(null)}
                           data-testid={`fea-endpoint-${ep.endpoint}`}>
                          <line x1={cp.x} y1={cp.y} x2={epp.x} y2={epp.y} stroke={epColor} strokeOpacity="0.18" strokeWidth="0.5" />
                          <circle cx={epp.x} cy={epp.y} r={epHovered ? 4 : 3}
                            fill={epColor} fillOpacity="0.6"
                            stroke={epColor} strokeWidth={epYield ? 1.5 : 0.7}
                            filter={epYield ? 'url(#glow-red)' : undefined} />
                          {epHovered && (
                            <g pointerEvents="none">
                              <rect x={epp.x - 70} y={epp.y + 6} width="140" height="38" rx="4" fill="#0A0A0A" stroke={epColor} strokeOpacity="0.6" />
                              <text x={epp.x} y={epp.y + 17} textAnchor="middle" fill="#FFFFFF" fontSize="7" fontWeight="bold">
                                {ep.short_name} {epYield ? '⚠' : ''}
                              </text>
                              <text x={epp.x} y={epp.y + 27} textAnchor="middle" fill="#8A8A8E" fontSize="6.5">
                                σvm: {ep.von_mises_stress.toFixed(4)}
                              </text>
                              <text x={epp.x} y={epp.y + 37} textAnchor="middle" fill="#8A8A8E" fontSize="6.5">
                                load: {(ep.load || 0).toFixed(3)}
                              </text>
                            </g>
                          )}
                        </g>
                      );
                    })}

                    {/* Component circle */}
                    <circle
                      cx={cp.x} cy={cp.y} r={compBaseR}
                      fill={cColor}
                      fillOpacity={cIsExpanded ? 0.35 : 0.2}
                      stroke={cColor}
                      strokeWidth={cIsYield ? 2 : 1.2}
                      filter={cIsYield ? 'url(#glow-red)' : undefined}
                    />
                    {/* Drill-down indicator (only show when not yet expanded and endpoints available) */}
                    {endpoints.length > 0 && !cIsExpanded && (
                      <text x={cp.x + compBaseR - 1} y={cp.y - compBaseR + 5} textAnchor="middle" fill={cColor} fontSize="7" fontWeight="bold" pointerEvents="none">⋮</text>
                    )}
                    <text x={cp.x} y={cp.y + 2} textAnchor="middle" fill="#FFFFFF" fontSize="7" fontWeight="bold" fontFamily="'JetBrains Mono', monospace" pointerEvents="none">
                      {cIsExpanded ? '' : c.short_name}
                    </text>
                    {cIsHovered && (
                      <g pointerEvents="none">
                        <rect x={cp.x - 78} y={cp.y + 16} width="156" height={endpoints.length > 0 ? 80 : 68} rx="5" fill="#0F0F0F" stroke={cColor} strokeOpacity="0.6" />
                        <text x={cp.x} y={cp.y + 28} textAnchor="middle" fill="#FFFFFF" fontSize="8" fontWeight="bold">
                          {c.component} {cIsYield ? '⚠' : ''}
                        </text>
                        <text x={cp.x} y={cp.y + 40} textAnchor="middle" fill="#8A8A8E" fontSize="7">
                          von-Mises: {c.von_mises_stress.toFixed(4)}
                        </text>
                        <text x={cp.x} y={cp.y + 50} textAnchor="middle" fill="#8A8A8E" fontSize="7">
                          Strain E: {(c.strain_energy || 0).toFixed(6)}  Load: {(c.load || 0).toFixed(3)}
                        </text>
                        <text x={cp.x} y={cp.y + 60} textAnchor="middle" fill="#8A8A8E" fontSize="7">
                          Lat:{c.metrics?.latency_ms?.toFixed(0) || 0}ms  Err:{c.metrics?.error_rate_pct?.toFixed(1) || 0}%  Sat:{c.metrics?.saturation_pct?.toFixed(0) || 0}%
                        </text>
                        <text x={cp.x} y={cp.y + 70} textAnchor="middle" fill={cColor} fontSize="7" fontWeight="bold">
                          {cIsYield ? `YIELD (> ${compYieldThreshold.toFixed(3)})` : `Yield @ ${compYieldThreshold.toFixed(3)}`}
                        </text>
                        {endpoints.length > 0 && (
                          <text x={cp.x} y={cp.y + 82} textAnchor="middle" fill="#8A8A8E" fontSize="6.5" fontStyle="italic">
                            {endpoints.length} endpoints — double-click to {cIsExpanded ? 'collapse' : 'drill in'}
                          </text>
                        )}
                      </g>
                    )}
                  </g>
                );
              })}

              {/* Node circle */}
              <circle
                cx={pos.x} cy={pos.y} r={isHovered ? radius + 3 : radius}
                fill={color}
                fillOpacity={isExpanded ? 0.22 : 0.15}
                stroke={color}
                strokeWidth={isYield ? 3 : 2}
                filter={isYield ? 'url(#glow-red)' : undefined}
                style={{ transition: 'r 0.2s' }}
              />

              {/* Node label */}
              <text x={pos.x} y={pos.y - 2} textAnchor="middle" fill="#FFFFFF" fontSize={isExpanded ? 9 : 11} fontWeight="bold" fontFamily="'JetBrains Mono', monospace" pointerEvents="none">
                {name}
              </text>
              <text x={pos.x} y={pos.y + (isExpanded ? 8 : 10)} textAnchor="middle" fill={color} fontSize={isExpanded ? 7 : 9} fontFamily="'JetBrains Mono', monospace" pointerEvents="none">
                {vm.toFixed(3)}
              </text>

              {/* iter 38 — Eutectic-pull badge: shows distance to Ψ_s and
                  active capacity boost. Distance color-codes the pull urgency:
                  green = near Ψ_s (< 0.20), amber = transient (0.20–0.40),
                  red = far from Ψ_s (> 0.40). Arrow → indicates the system
                  is pulling the node toward Ψ_s via the eutectic-guided
                  scale-out / scale-in actions. */}
              {phaseState?.per_node?.[name] && (
                <EutecticBadge
                  cx={pos.x}
                  cy={pos.y - radius - (isYield ? 30 : 16)}
                  distance={phaseState.per_node[name].eutectic_distance}
                  boost={phaseState.capacity_boosts?.[name]?.multiplier}
                  isExpanded={isExpanded}
                />
              )}

              {/* Expansion indicator badge */}
              {components.length > 0 && !isExpanded && (
                <g pointerEvents="none">
                  <circle cx={pos.x + radius - 4} cy={pos.y + radius - 4} r="7" fill="#0A0A0A" stroke={color} strokeWidth="1" />
                  <text x={pos.x + radius - 4} y={pos.y + radius - 1} textAnchor="middle" fill={color} fontSize="8" fontWeight="bold">+</text>
                </g>
              )}
              {isExpanded && (
                <g pointerEvents="none">
                  <circle cx={pos.x + radius - 4} cy={pos.y + radius - 4} r="7" fill="#0A0A0A" stroke={color} strokeWidth="1" />
                  <text x={pos.x + radius - 4} y={pos.y + radius - 1} textAnchor="middle" fill={color} fontSize="8" fontWeight="bold">−</text>
                </g>
              )}

              {/* Yield badge */}
              {isYield && (
                <g pointerEvents="none">
                  <rect x={pos.x + radius - 8} y={pos.y - radius - 2} width="24" height="14" rx="3" fill="#FF3B30" />
                  <text x={pos.x + radius + 4} y={pos.y - radius + 9} textAnchor="middle" fill="#FFFFFF" fontSize="7" fontWeight="bold">
                    YIELD
                  </text>
                </g>
              )}

              {/* Hover detail card (service-level) */}
              {isHovered && !isExpanded && (
                <g pointerEvents="none">
                  <rect x={pos.x - 75} y={pos.y + radius + 8} width="150" height="76" rx="6" fill="#1F1F1F" stroke="#262626" />
                  <text x={pos.x} y={pos.y + radius + 22} textAnchor="middle" fill="#FFFFFF" fontSize="8" fontWeight="bold">
                    {name} {isYield ? '(CRITICAL)' : ''}
                  </text>
                  <text x={pos.x} y={pos.y + radius + 34} textAnchor="middle" fill="#8A8A8E" fontSize="8">
                    Pressure: {vm.toFixed(4)}  Debt: {(node.strain_energy || 0).toFixed(5)}
                  </text>
                  <text x={pos.x} y={pos.y + radius + 46} textAnchor="middle" fill="#8A8A8E" fontSize="8">
                    Lat:{node.metrics?.latency_ms?.toFixed(0) || 0}ms Err:{node.metrics?.error_rate_pct?.toFixed(1) || 0}% Sat:{node.metrics?.saturation_pct?.toFixed(0) || 0}%
                  </text>
                  <text x={pos.x} y={pos.y + radius + 58} textAnchor="middle" fill={color} fontSize="8" fontWeight="bold">
                    Action: {node.corrective_action || 'none'}
                  </text>
                  <text x={pos.x} y={pos.y + radius + 70} textAnchor="middle" fill="#8A8A8E" fontSize="7" fontStyle="italic">
                    Double-click to expand components
                  </text>
                </g>
              )}
            </g>
          );
        })}
      </svg>

      {/* Fault Propagation Summary */}
      {propagation && (
        <div className="mt-3 bg-[#0F0F0F] border border-[#FF3B30]/40 rounded-lg p-4" data-testid="fea-propagation-summary">
          <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
            <h4 className="text-xs uppercase tracking-[0.2em] text-[#FF3B30] flex items-center gap-2">
              <Flame className="w-3 h-3" /> {showDampenedView ? 'Dampened wave' : 'Fault propagating'} from {propagation.source}
            </h4>
            <div className="flex items-center gap-2">
              {!dampener && (
                <button
                  onClick={dampenWaveNow}
                  className="text-[10px] px-3 py-1 rounded border bg-[#00FF9D]/10 border-[#00FF9D]/40 text-[#00FF9D] hover:bg-[#00FF9D]/20 flex items-center gap-1"
                  data-testid="fea-dampen-now"
                  title="Auto-compute and execute the dampening action"
                >
                  <Shield className="w-3 h-3" /> Dampen Now
                </button>
              )}
              {dampener?.wave_arrested && (
                <button
                  onClick={() => { setShowDampenedView(v => !v); setAnimIndex(0); }}
                  className="text-[10px] px-3 py-1 rounded border bg-[#5AC8FA]/10 border-[#5AC8FA]/40 text-[#5AC8FA] hover:bg-[#5AC8FA]/20"
                  data-testid="fea-toggle-dampened-view"
                >
                  Show: {showDampenedView ? 'Baseline' : 'Dampened'}
                </button>
              )}
              <div className="text-[10px] text-[#8A8A8E] font-mono">
                t={(propagation.timeline[Math.min(animIndex, propagation.timeline.length - 1)]?.t || 0).toFixed(1)}s · Φ={(propagation.timeline[Math.min(animIndex, propagation.timeline.length - 1)]?.phi || 0).toFixed(3)} · {propagation.timeline[Math.min(animIndex, propagation.timeline.length - 1)]?.infected_count || 0}/{propagation.mesh_size}
              </div>
            </div>
          </div>

          {/* Dampener summary card */}
          {dampener?.wave_arrested && (
            <div className="mb-3 bg-[#00FF9D]/5 border border-[#00FF9D]/30 rounded p-3" data-testid="fea-dampener-summary">
              <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
                <div className="text-[11px] text-[#00FF9D] flex items-center gap-2">
                  <Shield className="w-3 h-3" />
                  {dampener.wave_metrics.arrest_percentage > 1
                    ? <>Downstream wave arrested <span className="font-bold">{dampener.wave_metrics.arrest_percentage.toFixed(0)}%</span> via <span className="font-bold">{dampener.recommended_action.action_id}</span> on <span className="font-bold">{dampener.recommended_action.target_node}</span></>
                    : <>Dampener engaged: <span className="font-bold">{dampener.recommended_action.action_id}</span> on <span className="font-bold">{dampener.recommended_action.target_node}</span></>
                  }
                </div>
                {dampener.auto_executed && <span className="text-[10px] px-2 py-0.5 rounded bg-[#00FF9D]/20 text-[#00FF9D]">EXECUTED</span>}
                {dampener.execution_result?.reason === 'cooldown' && (
                  <span className="text-[10px] px-2 py-0.5 rounded bg-[#FFCC00]/20 text-[#FFCC00]" title={dampener.execution_result.message}>
                    COOLDOWN {dampener.execution_result.cooldown_remaining_seconds?.toFixed(0)}s
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[10px] font-mono">
                <div className="text-[#8A8A8E]">cut edge: <span className="text-[#FFFFFF]">{dampener.cut_edge.source}→{dampener.cut_edge.target}</span></div>
                <div className="text-[#8A8A8E]">cascade_risk: <span className="text-[#FFCC00]">{(dampener.cut_edge.cascade_risk * 100).toFixed(0)}%</span></div>
                <div className="text-[#8A8A8E]">peak beyond cut (base): <span className="text-[#FF3B30]">{dampener.wave_metrics.baseline_peak_downstream.toFixed(3)}</span></div>
                <div className="text-[#8A8A8E]">peak beyond cut (damp): <span className="text-[#00FF9D]">{dampener.wave_metrics.dampened_peak_downstream.toFixed(3)}</span></div>
              </div>
              <p className="text-[10px] text-[#8A8A8E] italic mt-1">{dampener.recommended_action.rationale}</p>
            </div>
          )}

          {/* Animation scrubber */}
          <input
            type="range"
            min="0"
            max={(showDampenedView && dampener?.dampened?.timeline ? dampener.dampened.timeline : propagation.timeline).length - 1}
            value={animIndex}
            onChange={(e) => { stopAnimation(); setAnimIndex(parseInt(e.target.value, 10)); }}
            className="w-full accent-[#FF3B30] mb-2"
            data-testid="fea-propagation-scrubber"
          />
          {/* Per-node arrival timeline */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 text-[10px] font-mono">
            {(showDampenedView && dampener?.dampened?.node_summary ? dampener.dampened.node_summary : propagation.node_summary).slice(0, 12).map(s => (
              <div key={s.node} className={`px-2 py-1 rounded ${s.is_source ? 'bg-[#FF3B30]/20 text-[#FF3B30]' : s.first_arrival_step !== null ? 'bg-[#FFCC00]/10 text-[#FFCC00]' : 'bg-[#1F1F1F] text-[#8A8A8E]'}`}>
                <div className="flex justify-between">
                  <span className="truncate">{s.node}</span>
                  <span>peak {s.peak_fault.toFixed(2)}</span>
                </div>
                <div className="text-[#8A8A8E]">
                  {s.is_source ? 'source' : s.first_arrival_t !== null ? `arr ${s.first_arrival_t.toFixed(1)}s` : 'never reached'}
                </div>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-[#8A8A8E] mt-2 italic">
            Laplacian diffusion ẋ = −α·L·x — implements the propagation kernel from the SRI/Unified-View papers (Φ = xᵀLx).
          </p>
        </div>
      )}

      {/* Structural Intelligence Summary */}
      <div className="grid grid-cols-4 gap-3 mt-3">
        <div className="bg-[#1F1F1F] rounded-lg p-3 border border-[#262626]">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle className="w-3 h-3 text-[#FF3B30]" />
            <span className="text-[10px] text-[#8A8A8E] uppercase tracking-wider">Critical Services</span>
          </div>
          <p className="text-lg font-bold font-['JetBrains_Mono']" style={{ color: yieldNodes.length > 0 ? '#FF3B30' : '#00FF9D' }}>
            {yieldNodes.length}
          </p>
          <p className="text-[10px] text-[#8A8A8E] truncate">
            {yieldNodes.length > 0 ? yieldNodes.map(n => n.node).join(', ') : 'All healthy'}
          </p>
        </div>
        <div className="bg-[#1F1F1F] rounded-lg p-3 border border-[#262626]">
          <div className="flex items-center gap-2 mb-1">
            <Zap className="w-3 h-3 text-[#FFCC00]" />
            <span className="text-[10px] text-[#8A8A8E] uppercase tracking-wider">Fragile Path</span>
          </div>
          <p className="text-lg font-bold font-['JetBrains_Mono'] text-[#FFCC00]">
            {weakestEdge ? `${weakestEdge.source}-${weakestEdge.target}` : '-'}
          </p>
          <p className="text-[10px] text-[#8A8A8E]">
            Fragility: {weakestEdge?.edge_strain?.toFixed(4) || 0}
          </p>
        </div>
        <div className="bg-[#1F1F1F] rounded-lg p-3 border border-[#262626]">
          <div className="flex items-center gap-2 mb-1">
            <Shield className="w-3 h-3 text-[#00FF9D]" />
            <span className="text-[10px] text-[#8A8A8E] uppercase tracking-wider">Failure Threshold</span>
          </div>
          <p className="text-lg font-bold font-['JetBrains_Mono'] text-[#00FF9D]">
            {fea.yield_threshold?.toFixed(4) || 0}
          </p>
          <p className="text-[10px] text-[#8A8A8E]">
            Max σvm: {fea.max_von_mises?.toFixed(4) || 0}
          </p>
        </div>
        <div className="bg-[#1F1F1F] rounded-lg p-3 border border-[#262626]">
          <div className="flex items-center gap-2 mb-1">
            <Activity className="w-3 h-3 text-[#5AC8FA]" />
            <span className="text-[10px] text-[#8A8A8E] uppercase tracking-wider">Mesh Granularity</span>
          </div>
          <p className="text-lg font-bold font-['JetBrains_Mono'] text-[#5AC8FA]">
            {hasComponentExpanded
              ? `${fea.mesh_size_endpoint || 0} endpoints`
              : hasExpanded
                ? `${fea.mesh_size_fine || 0} components`
                : `${fea.elements?.length || 0} services`}
          </p>
          <p className="text-[10px] text-[#8A8A8E]">
            {hasComponentExpanded
              ? `Yield @ σ > ${(fea.endpoint_yield_threshold || 0).toFixed(3)} · in ${fea.mesh_size_fine || 0} components`
              : hasExpanded
                ? `Yield @ σ > ${compYieldThreshold.toFixed(3)}`
                : 'Double-click to drill in'}
          </p>
        </div>
      </div>
    </div>
  );
}


// iter 38 — Eutectic-pull badge. Renders a compact "→Ψ_s d=0.12 [×N]" pill
// above the service node. Distance is color-coded: green near Ψ_s, amber
// mid-range, red far. The optional ×N multiplier renders only when an
// active capacity boost is present, signalling the node is currently
// scaled out / in by the eutectic-guided gate.
function EutecticBadge({ cx, cy, distance, boost, isExpanded }) {
  if (distance === undefined || distance === null) return null;
  const d = Number(distance);
  // Color thresholds tuned to the L2-distance scale [0, 1.0]:
  //   < 0.20 → green (at or near Ψ_s)
  //   0.20–0.40 → amber (in transit)
  //   > 0.40 → red (far from Ψ_s, system actively pulling)
  let color = '#34C759';
  if (d > 0.40) color = '#FF453A';
  else if (d > 0.20) color = '#FFCC00';
  const showBoost = boost && Number(boost) > 1.05;
  const fontSize = isExpanded ? 7 : 8;
  const padX = 4;
  const labelText = `→Ψ_s d=${d.toFixed(2)}`;
  const boostText = showBoost ? ` ×${Number(boost).toFixed(2)}` : '';
  const txt = labelText + boostText;
  // approximate text width (monospace ~5px / char @ font 8)
  const charW = isExpanded ? 4.4 : 5.0;
  const w = Math.max(54, txt.length * charW + padX * 2);
  const h = isExpanded ? 11 : 13;
  // `cy` is interpreted as the TOP-LEFT y of the badge so the caller
  // can place it cleanly above the node without overlap.
  return (
    <g pointerEvents="none" data-testid={`eutectic-badge-${labelText}`}>
      <rect
        x={cx - w / 2}
        y={cy}
        width={w}
        height={h}
        rx={3}
        fill="#0A0A0A"
        stroke={color}
        strokeOpacity="0.65"
        strokeWidth="0.75"
      />
      <text
        x={cx}
        y={cy + h - (isExpanded ? 3 : 3.5)}
        textAnchor="middle"
        fill={color}
        fontSize={fontSize}
        fontFamily="'JetBrains Mono', monospace"
        fontWeight={showBoost ? 'bold' : 'normal'}
      >
        {txt}
      </text>
    </g>
  );
}
