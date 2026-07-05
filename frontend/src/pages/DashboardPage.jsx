import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Play, Pause, Activity, AlertCircle, TrendingUp, DollarSign, Users, ShoppingBag, 
  ExternalLink, RefreshCw, ShoppingCart, Package, CreditCard, Truck, BarChart3,
  Zap, Database, Server, Globe, ArrowUpRight, ArrowDownRight, Bell, X, AlertTriangle,
  CheckCircle, Volume2, VolumeX, Settings, Shield, Heart, RotateCcw, Power, Clock
} from 'lucide-react';
import axios from 'axios';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, 
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell, Legend 
} from 'recharts';
import { Button } from '../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Slider } from '../components/ui/slider';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { useAuth } from '../contexts/AuthContext';
import { SpectralResilienceGraph } from '../components/dashboard/SpectralResilienceGraph';
import { MetricsPanel } from '../components/dashboard/MetricsPanel';
import { SRIDisplay } from '../components/dashboard/SRIDisplay';
import { FEATopologyHeatMap } from '../components/dashboard/FEATopologyHeatMap';
import { WebhookSettingsCard } from '../components/dashboard/WebhookSettingsCard';
import { NonRecoverableBanner } from '../components/dashboard/NonRecoverableBanner';
import { ResilienceDebtCard } from '../components/dashboard/ResilienceDebtCard';
import { ConversionFunnelCorrelationChart } from '../components/dashboard/ConversionFunnelCorrelationChart';
import { FEATerminologyCard } from '../components/dashboard/FEATerminologyCard';
import { ActivePropagationsPanel } from '../components/dashboard/ActivePropagationsPanel';
import { AggressiveHealingCard } from '../components/dashboard/AggressiveHealingCard';
import { LadderSynthesizerCard } from '../components/dashboard/LadderSynthesizerCard';
import { PhaseTransitionCard } from '../components/dashboard/PhaseTransitionCard';
import { PhaseDiagramView } from '../components/dashboard/PhaseDiagramView';
import { RumValidatedSequencesCard } from '../components/dashboard/RumValidatedSequencesCard';
import { ActionStagnationCard } from '../components/dashboard/ActionStagnationCard';
import { EconomicReliabilityCard } from '../components/dashboard/EconomicReliabilityCard';
import { StabilityFunctionalCard } from '../components/dashboard/StabilityFunctionalCard';
import { PathToStableCard } from '../components/dashboard/PathToStableCard';
import { CustomerExperiencePanel } from '../components/dashboard/CustomerExperiencePanel';
import { RSTCompositionPanel } from '../components/dashboard/RSTCompositionPanel';
import { StressStrainPanel } from '../components/dashboard/StressStrainPanel';
import { StructuralTwinGraph } from '../components/dashboard/StructuralTwinGraph';
import { SpectralResiliencePanel } from '../components/dashboard/SpectralResiliencePanel';
import { PhysicalAnalogyView } from '../components/dashboard/PhysicalAnalogyView';
import { ALL_NODES, SCENARIOS, computeNodeTensor, computeSpectral } from '../lib/rstSimulator';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const WS_URL = process.env.REACT_APP_BACKEND_URL?.replace('https://', 'wss://').replace('http://', 'ws://');

const COLORS = ['#00FF9D', '#FFCC00', '#FF3B30', '#00A3FF', '#A855F7'];

export default function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  
  const [activeTab, setActiveTab] = useState('overview');
  const [isRunning, setIsRunning] = useState(true);
  const [config, setConfig] = useState({
    traffic_scale: 1000,
    latency_scale: 50,
    error_rate: 0.05,
    saturation: 0.3,
    failure_mode: 'None',
  });
  
  const [metrics, setMetrics] = useState(null);
  const [sriHistory, setSriHistory] = useState([]);
  const [prevSri, setPrevSri] = useState(null);
  const [deltaSri, setDeltaSri] = useState(0);
  const [summary, setSummary] = useState(null);
  const [transactions, setTransactions] = useState(null);
  const [loading, setLoading] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const [showAlerts, setShowAlerts] = useState(false);
  const [alertSound, setAlertSound] = useState(true);
  const [unreadAlerts, setUnreadAlerts] = useState(0);
  const [healingStatus, setHealingStatus] = useState(null);
  const [healingHistory, setHealingHistory] = useState([]);
  const [healingLoading, setHealingLoading] = useState(false);
  const [reliability, setReliability] = useState(null);
  const [rstState, setRstState] = useState(null);
  const [rstHistory, setRstHistory] = useState([]);
  const [rstScenario, setRstScenario] = useState('normal');
  const [rstScenarioLoading, setRstScenarioLoading] = useState(false);
  
  const intervalRef = useRef(null);
  const wsRef = useRef(null);

  // WebSocket for real-time alerts
  useEffect(() => {
    const connectWebSocket = () => {
      if (WS_URL) {
        try {
          wsRef.current = new WebSocket(`${WS_URL}/ws/alerts`);
          
          wsRef.current.onopen = () => {
            
          };
          
          wsRef.current.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'alert') {
              setAlerts(prev => [data.alert, ...prev].slice(0, 50));
              setUnreadAlerts(prev => prev + 1);
              
              // Show toast notification
              const alertToast = data.alert.type === 'critical' ? toast.error : toast.warning;
              alertToast(data.alert.title, {
                description: data.alert.message,
                duration: 10000,
              });
              
              // Play sound for critical alerts
              if (alertSound && data.alert.type === 'critical') {
                // Browser beep
                const audio = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdW9tenBxcnFwcXJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJycnJy');
                audio.play().catch(() => {});
              }
            } else if (data.type === 'history') {
              setAlerts(data.alerts.reverse());
            } else if (data.type === 'healing') {
              toast.info(`Auto-Heal: ${data.record.action_name}`, {
                description: `SRI ${data.record.sri_before} → ${data.record.sri_after}`,
                duration: 8000,
              });
            }
          };
          
          wsRef.current.onclose = () => {
            
            setTimeout(connectWebSocket, 3000);
          };
          
          wsRef.current.onerror = (error) => {
            console.error('WebSocket error:', error);
          };
        } catch (e) {
          console.error('Failed to open WebSocket:', e);
        }
      }
    };
    
    connectWebSocket();
    
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [alertSound]);

  // Fetch initial alerts
  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        const { data } = await axios.get(`${API}/alerts`, { withCredentials: true });
        setAlerts(data.reverse());
      } catch (e) {
        console.error('Failed to fetch alerts:', e);
      }
    };
    fetchAlerts();
  }, []);

  // Fetch all data
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [summaryRes, transactionsRes] = await Promise.all([
          axios.get(`${API}/metrics/summary`, { withCredentials: true }),
          axios.get(`${API}/metrics/transactions`, { withCredentials: true }).catch(() => ({ data: null }))
        ]);
        setSummary(summaryRes.data);
        setTransactions(transactionsRes.data);
      } catch (e) {
        console.error('Failed to fetch summary/transactions:', e);
      }
    };
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchMetrics = useCallback(async () => {
    try {
      const [metricsRes, reliabilityRes, rstRes, rstHistRes] = await Promise.all([
        axios.get(`${API}/metrics/real`, { withCredentials: true }),
        axios.get(`${API}/metrics/reliability`, { withCredentials: true }).catch(() => ({ data: null })),
        axios.get(`${API}/rst/state`, { withCredentials: true }).catch(() => ({ data: null })),
        axios.get(`${API}/rst/history?limit=60`, { withCredentials: true }).catch(() => ({ data: null })),
      ]);
      const data = metricsRes.data;
      setMetrics(data);
      if (reliabilityRes.data) setReliability(reliabilityRes.data);
      if (rstRes.data?.ready) {
        setRstState(rstRes.data);
        const liveScenario = SCENARIOS.find(sc => sc.name === rstRes.data.scenario);
        if (liveScenario && liveScenario.id !== rstScenario) setRstScenario(liveScenario.id);
        if (!rstRes.data.scenario && rstScenario !== 'normal') setRstScenario('normal');
      } else if (data?.nodes?.length) {
        const metricsByNode = Object.fromEntries(data.nodes.map(node => [node.id, node]));
        const scenario = SCENARIOS.find(sc => sc.id === rstScenario);
        const nodes = Object.fromEntries(ALL_NODES.map(node => [
          node,
          computeNodeTensor(node, metricsByNode[node] ?? {}, {}, scenario?.overrides?.[node] ?? {}),
        ]));
        const localSnap = {
          ready: true,
          ts: Date.now() / 1000,
          nodes,
          spectral: computeSpectral(nodes),
          scenario: rstScenario === 'normal' ? null : scenario?.name,
          source: 'browser_metrics_fallback',
        };
        setRstState(localSnap);
        setRstHistory(prev => [...prev, localSnap].slice(-60));
      }
      if (rstHistRes.data?.samples?.length) setRstHistory(rstHistRes.data.samples);
      
      if (prevSri !== null) {
        setDeltaSri(data.sri - prevSri);
      }
      setPrevSri(data.sri);
      
      setSriHistory(prev => {
        const newHistory = [...prev, { 
          time: new Date().toLocaleTimeString(), 
          sri: data.sri, 
          latency: data.avg_latency 
        }];
        return newHistory.slice(-30);
      });
    } catch (e) {
      console.error('Failed to fetch metrics:', e);
    }
  }, [prevSri, rstScenario]);

  useEffect(() => {
    if (isRunning) {
      fetchMetrics();
      intervalRef.current = setInterval(fetchMetrics, 2000);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [isRunning, fetchMetrics]);

  const generateTraffic = async () => {
    setLoading(true);
    try {
      await axios.post(`${API}/metrics/generate-traffic`, {}, { withCredentials: true });
      await fetchMetrics();
    } catch (e) {
      // Fallback: make multiple API calls
      const promises = [];
      for (let i = 0; i < 20; i++) {
        promises.push(axios.get(`${API}/products`, { withCredentials: true }));
        promises.push(axios.get(`${API}/categories`, { withCredentials: true }));
      }
      await Promise.allSettled(promises);
      await fetchMetrics();
    } finally {
      setLoading(false);
    }
  };

  const applyRstScenario = async (scenarioId) => {
    setRstScenario(scenarioId);
    setRstScenarioLoading(true);
    try {
      const scenario = SCENARIOS.find(s => s.id === scenarioId);
      if (!scenario) return;
      if (scenarioId === 'normal') {
        await axios.delete(`${API}/rst/scenario`, { withCredentials: true });
      } else {
        await axios.post(`${API}/rst/scenario`, {
          name: scenario.name,
          overrides: scenario.overrides,
          duration_s: 60,
        }, { withCredentials: true });
      }
      await fetchMetrics();
    } catch (e) {
      // Backend may not be connected; ignore silently
    } finally {
      setRstScenarioLoading(false);
    }
  };

  // Fetch healing status
  const fetchHealingStatus = useCallback(async () => {
    try {
      const [statusRes, historyRes] = await Promise.all([
        axios.get(`${API}/healing/status`, { withCredentials: true }),
        axios.get(`${API}/healing/history`, { withCredentials: true })
      ]);
      setHealingStatus(statusRes.data);
      setHealingHistory(historyRes.data);
    } catch (e) {
      console.error('Failed to fetch healing status:', e);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'autoheal') {
      fetchHealingStatus();
      const interval = setInterval(fetchHealingStatus, 5000);
      return () => clearInterval(interval);
    }
  }, [activeTab, fetchHealingStatus]);

  const toggleAutoHeal = async () => {
    try {
      const newState = !healingStatus?.enabled;
      await axios.post(`${API}/healing/toggle`, { enabled: newState }, { withCredentials: true });
      toast.success(`Auto-healing ${newState ? 'enabled' : 'disabled'}`);
      fetchHealingStatus();
    } catch (e) {
      toast.error('Failed to toggle auto-healing');
    }
  };

  const toggleAlertDriven = async () => {
    try {
      const newState = !healingStatus?.alert_driven;
      await axios.post(`${API}/healing/toggle`, { alert_driven: newState }, { withCredentials: true });
      toast.success(`Alert-driven healing ${newState ? 'enabled' : 'disabled'}`);
      fetchHealingStatus();
    } catch (e) {
      toast.error('Failed to toggle alert-driven healing');
    }
  };

  const triggerHealingAction = async (actionId) => {
    setHealingLoading(true);
    try {
      const { data } = await axios.post(`${API}/healing/trigger`, { action_id: actionId }, { withCredentials: true });
      toast.success(`${data.action_name} executed`, { description: `SRI: ${data.sri_before} → ${data.sri_after}` });
      fetchHealingStatus();
      fetchMetrics();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to execute healing action');
    } finally {
      setHealingLoading(false);
    }
  };

  if (!user || user.role !== 'admin') {
    return (
      <div className="min-h-screen bg-[#0A0A0A] text-white flex items-center justify-center">
        <div className="text-center">
          <AlertCircle className="w-16 h-16 text-[#FF3B30] mx-auto mb-4" />
          <h1 className="text-2xl font-bold font-['Outfit'] mb-2">Access Denied</h1>
          <p className="text-[#8A8A8E] mb-6">Admin access required to view the dashboard</p>
          <Button onClick={() => navigate('/login')} variant="outline" className="border-[#262626]">
            Sign In as Admin
          </Button>
        </div>
      </div>
    );
  }

  // Prepare transaction data for charts
  const categoryData = transactions?.by_category || [];
  const hourlyData = transactions?.hourly || [];
  const statusData = transactions?.by_status || [];

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-[#F5F5F5]">
      {/* Header */}
      <header className="border-b border-[#262626] px-6 py-4 sticky top-0 bg-[#0A0A0A]/95 backdrop-blur z-50">
        <div className="max-w-[1600px] mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Activity className="w-7 h-7 text-[#00FF9D]" />
            <div>
              <h1 className="text-xl font-bold font-['Outfit']">FreshCart Operations Center</h1>
              <p className="text-xs text-[#8A8A8E]">Full-Stack Observability & Business Intelligence</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ${
              isRunning ? 'bg-[#00FF9D]/20 text-[#00FF9D]' : 'bg-[#262626] text-[#8A8A8E]'
            }`}>
              <span className={`w-2 h-2 rounded-full ${isRunning ? 'bg-[#00FF9D] animate-pulse' : 'bg-[#8A8A8E]'}`} />
              {isRunning ? 'LIVE' : 'PAUSED'}
            </div>
            
            {/* Alert Bell */}
            <div className="relative">
              <button
                onClick={() => { setShowAlerts(!showAlerts); setUnreadAlerts(0); }}
                className={`p-2 rounded-lg transition-colors ${
                  alerts.some(a => a.type === 'critical') ? 'bg-[#FF3B30]/20 text-[#FF3B30]' : 'bg-[#262626] text-[#8A8A8E] hover:text-white'
                }`}
                data-testid="alerts-button"
              >
                <Bell className="w-5 h-5" />
                {unreadAlerts > 0 && (
                  <span className="absolute -top-1 -right-1 w-5 h-5 bg-[#FF3B30] rounded-full text-[10px] flex items-center justify-center text-white font-bold">
                    {unreadAlerts > 9 ? '9+' : unreadAlerts}
                  </span>
                )}
              </button>
              
              {/* Alerts Dropdown */}
              {showAlerts && (
                <div className="absolute right-0 top-12 w-96 max-h-[500px] bg-[#121212] border border-[#262626] rounded-lg shadow-2xl z-50 overflow-hidden">
                  <div className="flex items-center justify-between p-4 border-b border-[#262626]">
                    <h3 className="font-semibold flex items-center gap-2">
                      <Bell className="w-4 h-4" />
                      System Alerts
                    </h3>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setAlertSound(!alertSound)}
                        className="p-1.5 rounded hover:bg-[#262626]"
                        title={alertSound ? 'Mute alerts' : 'Unmute alerts'}
                      >
                        {alertSound ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4 text-[#8A8A8E]" />}
                      </button>
                      <button onClick={() => setShowAlerts(false)} className="p-1.5 rounded hover:bg-[#262626]">
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                  <div className="max-h-[400px] overflow-y-auto">
                    {alerts.length === 0 ? (
                      <div className="p-8 text-center text-[#8A8A8E]">
                        <CheckCircle className="w-8 h-8 mx-auto mb-2 text-[#00FF9D]" />
                        <p>All systems operational</p>
                        <p className="text-xs mt-1">No alerts at this time</p>
                      </div>
                    ) : (
                      alerts.map((alert, idx) => (
                        <div 
                          key={alert.id || idx} 
                          className={`p-4 border-b border-[#262626] last:border-0 ${
                            alert.type === 'critical' ? 'bg-[#FF3B30]/5' : 'bg-[#FFCC00]/5'
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            {alert.type === 'critical' ? (
                              <AlertCircle className="w-5 h-5 text-[#FF3B30] flex-shrink-0 mt-0.5" />
                            ) : (
                              <AlertTriangle className="w-5 h-5 text-[#FFCC00] flex-shrink-0 mt-0.5" />
                            )}
                            <div className="flex-1 min-w-0">
                              <p className={`font-medium text-sm ${alert.type === 'critical' ? 'text-[#FF3B30]' : 'text-[#FFCC00]'}`}>
                                {alert.title}
                              </p>
                              <p className="text-xs text-[#8A8A8E] mt-1">{alert.message}</p>
                              {alert.action && (
                                <p className="text-xs text-[#00A3FF] mt-2">Action: {alert.action}</p>
                              )}
                              <p className="text-[10px] text-[#6B6761] mt-2">
                                {new Date(alert.timestamp).toLocaleString()}
                              </p>
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
            
            <Button
              onClick={() => navigate('/')}
              variant="outline"
              size="sm"
              className="border-[#262626] text-[#8A8A8E] hover:text-white"
            >
              Back to Store
            </Button>
          </div>
        </div>
      </header>

      {/* Critical Alert Banner */}
      {alerts.length > 0 && alerts[0].type === 'critical' && (
        <div className="bg-[#FF3B30] px-6 py-3">
          <div className="max-w-[1600px] mx-auto flex items-center justify-between">
            <div className="flex items-center gap-3">
              <AlertCircle className="w-5 h-5 text-white animate-pulse" />
              <span className="text-white font-medium">{alerts[0].title}</span>
              <span className="text-white/80 text-sm">{alerts[0].message}</span>
            </div>
            <button 
              onClick={() => setShowAlerts(true)}
              className="text-white/80 hover:text-white text-sm underline"
            >
              View Details
            </button>
          </div>
        </div>
      )}

      {/* Non-Recoverable State Banner (Eq. 7 SRI/SAI) */}
      <NonRecoverableBanner />

      <div className="max-w-[1600px] mx-auto p-6">
        {/* Quick Stats Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mb-6">
          {[
            { icon: ShoppingBag, label: 'Orders', value: summary?.total_orders || 0, color: '#00FF9D', trend: '+12%' },
            { icon: Users, label: 'Customers', value: summary?.total_users || 0, color: '#00A3FF', trend: '+5%' },
            { icon: DollarSign, label: 'Revenue', value: `$${(summary?.total_revenue || 0).toFixed(0)}`, color: '#FFCC00', trend: '+18%' },
            { icon: Package, label: 'Products', value: summary?.total_products || 0, color: '#A855F7', trend: '0%' },
            { icon: TrendingUp, label: 'Today', value: summary?.today_orders || 0, color: '#00FF9D', trend: '+8%' },
            { icon: Activity, label: 'SRI', value: metrics?.sri?.toFixed(3) || '—', color: metrics?.sri > 0.3 ? '#00FF9D' : metrics?.sri > 0.1 ? '#FFCC00' : '#FF3B30', trend: deltaSri >= 0 ? '+' : '' },
          ].map((stat) => (
            <div key={stat.label} className="bg-[#121212] border border-[#262626] rounded-lg p-4 hover:border-[#333] transition-colors">
              <div className="flex items-center justify-between mb-2">
                <stat.icon className="w-4 h-4" style={{ color: stat.color }} />
                <span className={`text-xs flex items-center gap-0.5 ${stat.trend.startsWith('+') ? 'text-[#00FF9D]' : stat.trend.startsWith('-') ? 'text-[#FF3B30]' : 'text-[#8A8A8E]'}`}>
                  {stat.trend.startsWith('+') ? <ArrowUpRight className="w-3 h-3" /> : stat.trend.startsWith('-') ? <ArrowDownRight className="w-3 h-3" /> : null}
                  {stat.trend}
                </span>
              </div>
              <p className="text-2xl font-bold font-['JetBrains_Mono']" style={{ color: stat.color }}>{stat.value}</p>
              <p className="text-xs text-[#8A8A8E] mt-1">{stat.label}</p>
            </div>
          ))}
        </div>

        {/* Main Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <div className="flex items-center justify-between">
            <TabsList className="bg-[#1F1F1F]">
              <TabsTrigger value="overview" className="data-[state=active]:bg-[#00FF9D] data-[state=active]:text-black">
                <BarChart3 className="w-4 h-4 mr-2" />
                Overview
              </TabsTrigger>
              <TabsTrigger value="resilience" className="data-[state=active]:bg-[#00FF9D] data-[state=active]:text-black">
                <Activity className="w-4 h-4 mr-2" />
                System Health
              </TabsTrigger>
              <TabsTrigger value="transactions" className="data-[state=active]:bg-[#00FF9D] data-[state=active]:text-black">
                <CreditCard className="w-4 h-4 mr-2" />
                Transactions
              </TabsTrigger>
              <TabsTrigger value="alerts" className="data-[state=active]:bg-[#FF3B30] data-[state=active]:text-white relative">
                <Bell className="w-4 h-4 mr-2" />
                Alerts
                {alerts.filter(a => a.type === 'critical').length > 0 && (
                  <span className="absolute -top-1 -right-1 w-4 h-4 bg-[#FF3B30] rounded-full text-[9px] flex items-center justify-center text-white">
                    {alerts.filter(a => a.type === 'critical').length}
                  </span>
                )}
              </TabsTrigger>
              <TabsTrigger value="infrastructure" className="data-[state=active]:bg-[#00FF9D] data-[state=active]:text-black">
                <Server className="w-4 h-4 mr-2" />
                Infrastructure
              </TabsTrigger>
              <TabsTrigger value="autoheal" className="data-[state=active]:bg-[#00A3FF] data-[state=active]:text-white">
                <Shield className="w-4 h-4 mr-2" />
                Auto-Heal
              </TabsTrigger>
              <TabsTrigger value="rst" className="data-[state=active]:bg-[#FF8C00] data-[state=active]:text-white">
                <Zap className="w-4 h-4 mr-2" />
                RST
              </TabsTrigger>
            </TabsList>

            <div className="flex items-center gap-3">
              <Button
                onClick={generateTraffic}
                disabled={loading}
                variant="outline"
                size="sm"
                className="border-[#262626]"
                data-testid="generate-traffic-btn"
              >
                <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                Generate Traffic
              </Button>
              <Button
                onClick={() => setIsRunning(!isRunning)}
                size="sm"
                className={isRunning ? 'bg-[#FF3B30] hover:bg-[#FF3B30]/80' : 'bg-[#00FF9D] hover:bg-[#00FF9D]/80 text-black'}
                data-testid="simulation-toggle"
              >
                {isRunning ? <><Pause className="w-4 h-4 mr-2" /> Stop</> : <><Play className="w-4 h-4 mr-2" /> Start</>}
              </Button>
            </div>
          </div>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* SRI Gauge */}
              <div className="bg-[#121212] border border-[#262626] rounded-lg p-6">
                <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4">System Resilience Index</h3>
                {metrics ? (
                  <SRIDisplay sri={metrics.sri} deltaSri={deltaSri} avgLatency={metrics.avg_latency} />
                ) : (
                  <div className="text-center py-8 text-[#8A8A8E]">Start monitoring to see SRI</div>
                )}
              </div>

              {/* SRI Trend */}
              <div className="lg:col-span-2 bg-[#121212] border border-[#262626] rounded-lg p-6">
                <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4">SRI Trend (Real-Time)</h3>
                <div className="h-[200px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={sriHistory}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
                      <XAxis dataKey="time" stroke="#8A8A8E" fontSize={10} />
                      <YAxis domain={[0, 1]} stroke="#8A8A8E" fontSize={10} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#1F1F1F', border: '1px solid #262626', borderRadius: '8px' }}
                        labelStyle={{ color: '#8A8A8E' }}
                      />
                      <Area type="monotone" dataKey="sri" stroke="#00FF9D" fill="#00FF9D" fillOpacity={0.1} strokeWidth={2} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            {/* Golden Signals */}
            <div className="bg-[#121212] border border-[#262626] rounded-lg p-6" data-testid="golden-signals-section">
              <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4 flex items-center gap-2">
                <Activity className="w-4 h-4 text-[#00A3FF]" />
                Golden Signals — SRI Breakdown
              </h3>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {[
                  { key: 'latency', label: 'Latency', icon: Clock, color: '#00A3FF', format: v => `${v}ms` },
                  { key: 'traffic', label: 'Traffic', icon: Globe, color: '#00FF9D', format: v => `${v} req` },
                  { key: 'errors', label: 'Errors', icon: AlertTriangle, color: '#FF3B30', format: v => `${v}%` },
                  { key: 'saturation', label: 'Saturation', icon: Database, color: '#FFCC00', format: v => `${v}%` },
                ].map(signal => {
                  const gs = metrics?.golden_signals?.[signal.key];
                  const contrib = metrics?.signal_contributions?.[signal.key];
                  const health = gs?.health || 0;
                  const Icon = signal.icon;
                  return (
                    <div key={signal.key} className="bg-[#1F1F1F] rounded-lg p-4 border border-[#262626]">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <Icon className="w-4 h-4" style={{ color: signal.color }} />
                          <span className="text-xs text-[#8A8A8E] uppercase tracking-wider">{signal.label}</span>
                        </div>
                        <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                          health > 0.8 ? 'bg-[#00FF9D]/10 text-[#00FF9D]' : health > 0.5 ? 'bg-[#FFCC00]/10 text-[#FFCC00]' : 'bg-[#FF3B30]/10 text-[#FF3B30]'
                        }`}>
                          {(health * 100).toFixed(0)}%
                        </span>
                      </div>
                      <p className="text-xl font-bold font-['JetBrains_Mono']" style={{ color: signal.color }}>
                        {gs ? signal.format(gs.value) : '—'}
                      </p>
                      <div className="mt-2">
                        <div className="flex items-center justify-between text-[10px] text-[#8A8A8E] mb-1">
                          <span>Health</span>
                          <span>SRI contrib: {contrib ? `+${(contrib * 100).toFixed(0)}%` : '—'}</span>
                        </div>
                        <div className="w-full h-1.5 bg-[#262626] rounded-full overflow-hidden">
                          <div className="h-full rounded-full transition-all duration-500" style={{
                            width: `${health * 100}%`,
                            backgroundColor: health > 0.8 ? '#00FF9D' : health > 0.5 ? '#FFCC00' : '#FF3B30'
                          }} />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Customer Experience */}
            <div className="bg-[#121212] border border-[#262626] rounded-lg p-6" data-testid="customer-experience-section">
              <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4 flex items-center gap-2">
                <Users className="w-4 h-4 text-[#A855F7]" />
                Customer Experience
              </h3>
              <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                {/* Apdex */}
                <div className="bg-[#1F1F1F] rounded-lg p-4 border border-[#262626]">
                  <p className="text-xs text-[#8A8A8E] uppercase tracking-wider">Apdex Score</p>
                  <p className={`text-2xl font-bold font-['JetBrains_Mono'] mt-1 ${
                    (metrics?.customer_experience?.apdex || 0) >= 0.85 ? 'text-[#00FF9D]' : 
                    (metrics?.customer_experience?.apdex || 0) >= 0.7 ? 'text-[#FFCC00]' : 'text-[#FF3B30]'
                  }`}>
                    {metrics?.customer_experience?.apdex?.toFixed(2) || '—'}
                  </p>
                  <p className="text-[10px] text-[#8A8A8E] mt-1">{metrics?.customer_experience?.apdex_label || 'N/A'}</p>
                </div>
                {/* P50/P95/P99 */}
                <div className="bg-[#1F1F1F] rounded-lg p-4 border border-[#262626]">
                  <p className="text-xs text-[#8A8A8E] uppercase tracking-wider">Latency Percentiles</p>
                  <div className="mt-2 space-y-1">
                    <div className="flex justify-between"><span className="text-[10px] text-[#8A8A8E]">P50</span><span className="text-xs font-['JetBrains_Mono'] text-[#00A3FF]">{metrics?.customer_experience?.p50?.toFixed(0) || 0}ms</span></div>
                    <div className="flex justify-between"><span className="text-[10px] text-[#8A8A8E]">P95</span><span className="text-xs font-['JetBrains_Mono'] text-[#FFCC00]">{metrics?.customer_experience?.p95?.toFixed(0) || 0}ms</span></div>
                    <div className="flex justify-between"><span className="text-[10px] text-[#8A8A8E]">P99</span><span className="text-xs font-['JetBrains_Mono'] text-[#FF3B30]">{metrics?.customer_experience?.p99?.toFixed(0) || 0}ms</span></div>
                  </div>
                </div>
                {/* Availability */}
                <div className="bg-[#1F1F1F] rounded-lg p-4 border border-[#262626]">
                  <p className="text-xs text-[#8A8A8E] uppercase tracking-wider">Availability</p>
                  <p className={`text-2xl font-bold font-['JetBrains_Mono'] mt-1 ${
                    (metrics?.customer_experience?.availability || 0) >= 99.5 ? 'text-[#00FF9D]' : 'text-[#FFCC00]'
                  }`}>
                    {metrics?.customer_experience?.availability?.toFixed(2) || '—'}%
                  </p>
                  <p className="text-[10px] text-[#8A8A8E] mt-1">SLO: 99.5%</p>
                </div>
                {/* Error Budget */}
                <div className="bg-[#1F1F1F] rounded-lg p-4 border border-[#262626]">
                  <p className="text-xs text-[#8A8A8E] uppercase tracking-wider">Error Budget</p>
                  <p className={`text-2xl font-bold font-['JetBrains_Mono'] mt-1 ${
                    (metrics?.customer_experience?.error_budget?.remaining_pct || 0) > 50 ? 'text-[#00FF9D]' : 'text-[#FF3B30]'
                  }`}>
                    {metrics?.customer_experience?.error_budget?.remaining_pct?.toFixed(0) || '—'}%
                  </p>
                  <p className="text-[10px] text-[#8A8A8E] mt-1">remaining of {metrics?.customer_experience?.error_budget?.total || 0.5}%</p>
                </div>
                {/* Request Stats */}
                <div className="bg-[#1F1F1F] rounded-lg p-4 border border-[#262626]">
                  <p className="text-xs text-[#8A8A8E] uppercase tracking-wider">Throughput</p>
                  <p className="text-2xl font-bold font-['JetBrains_Mono'] text-[#00A3FF] mt-1">
                    {metrics?.customer_experience?.total_requests || 0}
                  </p>
                  <p className="text-[10px] text-[#8A8A8E] mt-1">{metrics?.customer_experience?.total_errors || 0} errors</p>
                </div>
              </div>
            </div>

            {/* Reliability & Conversion Funnel */}
            <div className="bg-[#121212] border border-[#262626] rounded-lg p-6" data-testid="reliability-funnel-section">
              <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4 flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-[#00FF9D]" />
                Reliability Score & Conversion Funnel
              </h3>
              
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Reliability Score Gauge */}
                <div className="bg-[#1F1F1F] rounded-lg p-5 border border-[#262626]">
                  <p className="text-xs text-[#8A8A8E] uppercase tracking-wider mb-3">Overall Reliability</p>
                  <div className="text-center">
                    <span className={`text-4xl font-bold font-['JetBrains_Mono'] ${
                      (reliability?.score || 0) >= 0.9 ? 'text-[#00FF9D]' : 
                      (reliability?.score || 0) >= 0.75 ? 'text-[#00A3FF]' : 
                      (reliability?.score || 0) >= 0.5 ? 'text-[#FFCC00]' : 'text-[#FF3B30]'
                    }`}>
                      {((reliability?.score || 0) * 100).toFixed(1)}%
                    </span>
                    <p className={`text-sm mt-1 capitalize ${
                      reliability?.label === 'excellent' ? 'text-[#00FF9D]' :
                      reliability?.label === 'good' ? 'text-[#00A3FF]' :
                      reliability?.label === 'fair' ? 'text-[#FFCC00]' : 'text-[#FF3B30]'
                    }`}>{reliability?.label || 'Loading...'}</p>
                  </div>
                  {/* Component breakdown */}
                  <div className="mt-4 space-y-2">
                    {reliability?.components && Object.entries(reliability.components).map(([key, comp]) => (
                      <div key={key} className="flex items-center gap-2">
                        <span className="text-[10px] text-[#8A8A8E] w-24 truncate">{key.replace('_', ' ')}</span>
                        <div className="flex-1 bg-[#262626] rounded-full h-1.5">
                          <div 
                            className="h-1.5 rounded-full transition-all duration-500"
                            style={{ 
                              width: `${(comp.value || 0) * 100}%`,
                              backgroundColor: comp.value >= 0.8 ? '#00FF9D' : comp.value >= 0.5 ? '#FFCC00' : '#FF3B30'
                            }}
                          />
                        </div>
                        <span className="text-[10px] font-['JetBrains_Mono'] text-[#8A8A8E] w-10 text-right">
                          {((comp.value || 0) * 100).toFixed(0)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Conversion Funnel Visualization */}
                <div className="bg-[#1F1F1F] rounded-lg p-5 border border-[#262626]">
                  <p className="text-xs text-[#8A8A8E] uppercase tracking-wider mb-3">Conversion Funnel</p>
                  {(() => {
                    const funnel = reliability?.funnel?.modeled_conversion?.health_adjusted_funnel || {};
                    const stages = [
                      { label: 'View → Cart', rate: funnel.view_to_cart || 0, color: '#00A3FF' },
                      { label: 'Cart → Checkout', rate: funnel.cart_to_checkout || 0, color: '#FFCC00' },
                      { label: 'Checkout → Order', rate: funnel.checkout_to_order || 0, color: '#00FF9D' },
                    ];
                    return (
                      <div className="space-y-4">
                        {stages.map(stage => (
                          <div key={stage.label}>
                            <div className="flex justify-between mb-1">
                              <span className="text-xs text-[#8A8A8E]">{stage.label}</span>
                              <span className="text-xs font-['JetBrains_Mono']" style={{ color: stage.color }}>
                                {(stage.rate * 100).toFixed(1)}%
                              </span>
                            </div>
                            <div className="bg-[#262626] rounded-full h-3 overflow-hidden">
                              <div 
                                className="h-3 rounded-full transition-all duration-700"
                                style={{ width: `${stage.rate * 100}%`, backgroundColor: stage.color }}
                              />
                            </div>
                          </div>
                        ))}
                        <div className="mt-3 pt-3 border-t border-[#262626]">
                          <div className="flex justify-between">
                            <span className="text-xs text-[#8A8A8E]">Effective Conversion</span>
                            <span className="text-sm font-bold font-['JetBrains_Mono'] text-[#00FF9D]">
                              {((reliability?.funnel?.modeled_conversion?.effective_conversion_rate || 0) * 100).toFixed(2)}%
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  })()}
                </div>

                {/* Revenue & Impact */}
                <div className="bg-[#1F1F1F] rounded-lg p-5 border border-[#262626]">
                  <p className="text-xs text-[#8A8A8E] uppercase tracking-wider mb-3">Business Impact</p>
                  <div className="space-y-4">
                    <div>
                      <p className="text-[10px] text-[#8A8A8E]">Projected Revenue/min</p>
                      <p className="text-2xl font-bold font-['JetBrains_Mono'] text-[#00FF9D]">
                        ${(reliability?.funnel?.modeled_conversion?.projected_revenue_per_min || 0).toFixed(0)}
                      </p>
                    </div>
                    <div>
                      <p className="text-[10px] text-[#8A8A8E]">Latency Impact Factor</p>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 bg-[#262626] rounded-full h-2">
                          <div 
                            className="h-2 rounded-full bg-[#00A3FF] transition-all duration-500"
                            style={{ width: `${(reliability?.funnel?.modeled_conversion?.latency_impact_factor || 0) * 100}%` }}
                          />
                        </div>
                        <span className="text-xs font-['JetBrains_Mono'] text-[#00A3FF]">
                          {((reliability?.funnel?.modeled_conversion?.latency_impact_factor || 0) * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                    <div>
                      <p className="text-[10px] text-[#8A8A8E]">Error Impact Factor</p>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 bg-[#262626] rounded-full h-2">
                          <div 
                            className="h-2 rounded-full bg-[#FF3B30] transition-all duration-500"
                            style={{ width: `${(reliability?.funnel?.modeled_conversion?.error_impact_factor || 0) * 100}%` }}
                          />
                        </div>
                        <span className="text-xs font-['JetBrains_Mono'] text-[#FF3B30]">
                          {((reliability?.funnel?.modeled_conversion?.error_impact_factor || 0) * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                    <div className="pt-3 border-t border-[#262626]">
                      <p className="text-[10px] text-[#8A8A8E] mb-1">Improvement if latency halved</p>
                      <p className="text-sm font-['JetBrains_Mono'] text-[#FFCC00]">
                        {((reliability?.funnel?.modeled_conversion?.improvement_opportunity?.if_latency_halved || 0) * 100).toFixed(2)}% conversion
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Business Metrics Row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Revenue by Category */}
              <div className="bg-[#121212] border border-[#262626] rounded-lg p-6">
                <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4">Sales by Category</h3>
                <div className="h-[250px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={categoryData.length > 0 ? categoryData : [
                          { name: 'Vegetables', value: 35 },
                          { name: 'Fruits', value: 25 },
                          { name: 'Dairy', value: 20 },
                          { name: 'Bakery', value: 12 },
                          { name: 'Other', value: 8 },
                        ]}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={90}
                        paddingAngle={2}
                        dataKey="value"
                      >
                        {(categoryData.length > 0 ? categoryData : [1,2,3,4,5]).map((_, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={{ backgroundColor: '#1F1F1F', border: '1px solid #262626' }} />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Order Status Distribution */}
              <div className="bg-[#121212] border border-[#262626] rounded-lg p-6">
                <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4">Order Pipeline</h3>
                <div className="h-[250px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={statusData.length > 0 ? statusData : [
                      { status: 'Pending', count: 5 },
                      { status: 'Confirmed', count: 8 },
                      { status: 'Preparing', count: 3 },
                      { status: 'Delivered', count: 12 },
                    ]} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
                      <XAxis type="number" stroke="#8A8A8E" fontSize={10} />
                      <YAxis dataKey="status" type="category" stroke="#8A8A8E" fontSize={10} width={80} />
                      <Tooltip contentStyle={{ backgroundColor: '#1F1F1F', border: '1px solid #262626' }} />
                      <Bar dataKey="count" fill="#00FF9D" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </TabsContent>

          {/* System Health Tab */}
          <TabsContent value="resilience" className="space-y-6">
            {/* FEA Topology Heat Map */}
            <div className="bg-[#121212] border border-[#262626] rounded-lg p-6" data-testid="fea-topology-section">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] flex items-center gap-2">
                  <Activity className="w-4 h-4 text-[#FF9500]" />
                  Structural Topology Heat Map — FEA Stress Analysis
                </h3>
                {metrics && (
                  <span className="text-xs px-2 py-1 rounded bg-[#FF9500]/10 text-[#FF9500]">
                    Von-Mises + Edge Strain
                  </span>
                )}
              </div>
              <FEATopologyHeatMap isRunning={isRunning} />
            </div>

            {/* Auto-detected failure propagations + optimized healing plans */}
            <ActivePropagationsPanel isRunning={isRunning} />
            <AggressiveHealingCard isRunning={isRunning} />

            {/* Phase Transition Classifier — operational phase, σ, eutectic distance */}
            <PhaseTransitionCard isRunning={isRunning} />

            {/* Phase Diagram (iron-carbide style) — 2D phase chart with live trajectories */}
            <PhaseDiagramView isRunning={isRunning} />

            {/* Ladder Synthesizer — programs writing programs */}
            <LadderSynthesizerCard isRunning={isRunning} />

            {/* RUM-validated healing sequences — closes the user-feedback loop */}
            <RumValidatedSequencesCard isRunning={isRunning} />

            {/* Action Stagnation Guard — dynamically removes misfiring actions */}
            <ActionStagnationCard isRunning={isRunning} />

            {/* Economic Reliability (Phase 3 of Unified Model) — R_econ = W/C_T */}
            <EconomicReliabilityCard isRunning={isRunning} />

            {/* Stability Functional Ψ (Phase 2 of Unified Model) — Lyapunov scalar */}
            <StabilityFunctionalCard isRunning={isRunning} />

            {/* Fastest-path-to-Ψ_s planner (iter 45) — per-node greedy IPC plan */}
            <PathToStableCard isRunning={isRunning} />

            {/* Customer Experience — what the actual user feels */}
            <CustomerExperiencePanel isRunning={isRunning} />

            {/* SRI ↔ Conversion live correlation */}
            <ConversionFunnelCorrelationChart isRunning={isRunning} />

            {/* FEA strict-sense terminology mapping */}
            <FEATerminologyCard />

            {/* Resilience Debt — E(t) = ∫Φ dt + Cost ∝ 1/SRI (Unified-View paper) */}
            <ResilienceDebtCard isRunning={isRunning} />

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Original Service Graph */}
              <div className="bg-[#121212] border border-[#262626] rounded-lg p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E]">Spectral Resilience Graph</h3>
                  {metrics && (
                    <span className="text-xs px-2 py-1 rounded bg-[#00FF9D]/10 text-[#00FF9D]">
                      Source: {metrics.source}
                    </span>
                  )}
                </div>
                {metrics ? (
                  <SpectralResilienceGraph 
                    nodes={metrics.nodes} 
                    edges={metrics.edges} 
                    weakEdges={metrics.weak_edges} 
                  />
                ) : (
                  <div className="h-[300px] flex items-center justify-center text-[#8A8A8E]">
                    Start monitoring to see graph
                  </div>
                )}
              </div>

              {/* Latency Distribution */}
              <div className="bg-[#121212] border border-[#262626] rounded-lg p-6">
                <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4">Latency by Service</h3>
                <div className="h-[300px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={metrics?.nodes || []}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
                      <XAxis dataKey="id" stroke="#8A8A8E" fontSize={10} />
                      <YAxis stroke="#8A8A8E" fontSize={10} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#1F1F1F', border: '1px solid #262626' }}
                        formatter={(value) => [`${value.toFixed(2)}ms`, 'Latency']}
                      />
                      <Bar dataKey="latency" fill="#FFCC00" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            {/* Node Metrics Table */}
            <div className="bg-[#121212] border border-[#262626] rounded-lg p-6">
              <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4">Node Metrics Detail</h3>
              {metrics ? (
                <MetricsPanel nodes={metrics.nodes} />
              ) : (
                <div className="text-center py-8 text-[#8A8A8E]">Start monitoring to see metrics</div>
              )}
            </div>
          </TabsContent>

          {/* Transactions Tab */}
          <TabsContent value="transactions" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Transaction Flow */}
              <div className="lg:col-span-2 bg-[#121212] border border-[#262626] rounded-lg p-6">
                <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4">Transaction Flow</h3>
                <div className="grid grid-cols-5 gap-4">
                  {[
                    { icon: Globe, label: 'Visit', count: (summary?.total_users || 0) * 5, color: '#00A3FF' },
                    { icon: ShoppingCart, label: 'Add to Cart', count: (summary?.total_orders || 0) * 3, color: '#A855F7' },
                    { icon: CreditCard, label: 'Checkout', count: summary?.total_orders || 0, color: '#FFCC00' },
                    { icon: Package, label: 'Fulfilled', count: Math.floor((summary?.total_orders || 0) * 0.8), color: '#00FF9D' },
                    { icon: Truck, label: 'Delivered', count: Math.floor((summary?.total_orders || 0) * 0.6), color: '#00FF9D' },
                  ].map((step, idx) => (
                    <div key={step.label} className="text-center">
                      <div className="w-12 h-12 rounded-full mx-auto mb-2 flex items-center justify-center" style={{ backgroundColor: `${step.color}20` }}>
                        <step.icon className="w-6 h-6" style={{ color: step.color }} />
                      </div>
                      <p className="text-lg font-bold font-['JetBrains_Mono']" style={{ color: step.color }}>{step.count}</p>
                      <p className="text-xs text-[#8A8A8E]">{step.label}</p>
                      {idx < 4 && (
                        <div className="hidden lg:block absolute right-0 top-1/2 -translate-y-1/2 w-8 h-0.5 bg-[#262626]" />
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Conversion Rate */}
              <div className="bg-[#121212] border border-[#262626] rounded-lg p-6">
                <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4">Conversion Funnel</h3>
                <div className="space-y-4">
                  {[
                    { label: 'Visit → Cart', rate: 60 },
                    { label: 'Cart → Checkout', rate: 33 },
                    { label: 'Checkout → Order', rate: 100 },
                    { label: 'Order → Delivered', rate: 75 },
                  ].map((item) => (
                    <div key={item.label}>
                      <div className="flex justify-between text-sm mb-1">
                        <span className="text-[#8A8A8E]">{item.label}</span>
                        <span className="text-[#00FF9D]">{item.rate}%</span>
                      </div>
                      <div className="h-2 bg-[#262626] rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-[#00FF9D] rounded-full transition-all"
                          style={{ width: `${item.rate}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Recent Orders */}
            <div className="bg-[#121212] border border-[#262626] rounded-lg p-6">
              <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4">Live Order Feed</h3>
              <div className="text-sm text-[#8A8A8E] text-center py-8">
                Order feed updates in real-time as transactions occur
              </div>
            </div>
          </TabsContent>

          {/* Alerts Tab */}
          <TabsContent value="alerts" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Alert Stats */}
              <div className="bg-[#121212] border border-[#262626] rounded-lg p-6">
                <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4">Alert Summary</h3>
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-3 bg-[#FF3B30]/10 rounded-lg">
                    <div className="flex items-center gap-2">
                      <AlertCircle className="w-5 h-5 text-[#FF3B30]" />
                      <span className="text-[#FF3B30]">Critical</span>
                    </div>
                    <span className="text-2xl font-bold font-['JetBrains_Mono'] text-[#FF3B30]">
                      {alerts.filter(a => a.type === 'critical').length}
                    </span>
                  </div>
                  <div className="flex items-center justify-between p-3 bg-[#FFCC00]/10 rounded-lg">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="w-5 h-5 text-[#FFCC00]" />
                      <span className="text-[#FFCC00]">Warning</span>
                    </div>
                    <span className="text-2xl font-bold font-['JetBrains_Mono'] text-[#FFCC00]">
                      {alerts.filter(a => a.type === 'warning').length}
                    </span>
                  </div>
                  <div className="flex items-center justify-between p-3 bg-[#00FF9D]/10 rounded-lg">
                    <div className="flex items-center gap-2">
                      <CheckCircle className="w-5 h-5 text-[#00FF9D]" />
                      <span className="text-[#00FF9D]">Resolved</span>
                    </div>
                    <span className="text-2xl font-bold font-['JetBrains_Mono'] text-[#00FF9D]">0</span>
                  </div>
                </div>
              </div>

              {/* Alert Thresholds */}
              <div className="lg:col-span-2 bg-[#121212] border border-[#262626] rounded-lg p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E]">Alert Thresholds</h3>
                  <Settings className="w-4 h-4 text-[#8A8A8E]" />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-[#1F1F1F] rounded-lg">
                    <p className="text-xs text-[#8A8A8E] mb-1">SRI Critical</p>
                    <p className="text-xl font-bold font-['JetBrains_Mono'] text-[#FF3B30]">&lt; 0.1</p>
                  </div>
                  <div className="p-4 bg-[#1F1F1F] rounded-lg">
                    <p className="text-xs text-[#8A8A8E] mb-1">SRI Warning</p>
                    <p className="text-xl font-bold font-['JetBrains_Mono'] text-[#FFCC00]">&lt; 0.3</p>
                  </div>
                  <div className="p-4 bg-[#1F1F1F] rounded-lg">
                    <p className="text-xs text-[#8A8A8E] mb-1">Latency Critical</p>
                    <p className="text-xl font-bold font-['JetBrains_Mono'] text-[#FF3B30]">&gt; 200ms</p>
                  </div>
                  <div className="p-4 bg-[#1F1F1F] rounded-lg">
                    <p className="text-xs text-[#8A8A8E] mb-1">Error Rate Critical</p>
                    <p className="text-xl font-bold font-['JetBrains_Mono'] text-[#FF3B30]">&gt; 10%</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Webhook Settings */}
            <WebhookSettingsCard />

            {/* Alert History */}
            <div className="bg-[#121212] border border-[#262626] rounded-lg p-6">
              <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4">Alert History</h3>
              {alerts.length === 0 ? (
                <div className="text-center py-12">
                  <CheckCircle className="w-12 h-12 text-[#00FF9D] mx-auto mb-4" />
                  <p className="text-lg font-medium text-[#00FF9D]">All Systems Operational</p>
                  <p className="text-sm text-[#8A8A8E] mt-2">No alerts have been triggered</p>
                </div>
              ) : (
                <div className="space-y-3 max-h-[400px] overflow-y-auto">
                  {alerts.map((alert, idx) => (
                    <div 
                      key={alert.id || idx}
                      className={`p-4 rounded-lg border ${
                        alert.type === 'critical' 
                          ? 'bg-[#FF3B30]/5 border-[#FF3B30]/30' 
                          : 'bg-[#FFCC00]/5 border-[#FFCC00]/30'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        {alert.type === 'critical' ? (
                          <AlertCircle className="w-5 h-5 text-[#FF3B30] flex-shrink-0" />
                        ) : (
                          <AlertTriangle className="w-5 h-5 text-[#FFCC00] flex-shrink-0" />
                        )}
                        <div className="flex-1">
                          <div className="flex items-center justify-between">
                            <p className={`font-medium ${alert.type === 'critical' ? 'text-[#FF3B30]' : 'text-[#FFCC00]'}`}>
                              {alert.title}
                            </p>
                            <span className="text-xs text-[#8A8A8E]">
                              {new Date(alert.timestamp).toLocaleTimeString()}
                            </span>
                          </div>
                          <p className="text-sm text-[#8A8A8E] mt-1">{alert.message}</p>
                          {alert.action && (
                            <p className="text-xs text-[#00A3FF] mt-2 flex items-center gap-1">
                              <Zap className="w-3 h-3" />
                              {alert.action}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </TabsContent>

          {/* Infrastructure Tab */}
          <TabsContent value="infrastructure" className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {[
                { name: 'API Server', status: 'healthy', port: 8001, type: 'FastAPI' },
                { name: 'Frontend', status: 'healthy', port: 3000, type: 'React' },
                { name: 'MongoDB', status: 'healthy', port: 27017, type: 'Database' },
                { name: 'InfluxDB', status: 'healthy', port: 8086, type: 'Time-Series' },
                { name: 'Grafana', status: 'healthy', port: 3002, type: 'Visualization' },
              ].map((service) => (
                <div key={service.name} className="bg-[#121212] border border-[#262626] rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <Database className="w-4 h-4 text-[#00A3FF]" />
                      <span className="font-medium">{service.name}</span>
                    </div>
                    <span className={`w-2 h-2 rounded-full ${service.status === 'healthy' ? 'bg-[#00FF9D]' : 'bg-[#FF3B30]'}`} />
                  </div>
                  <div className="text-xs text-[#8A8A8E] space-y-1">
                    <p>Port: <span className="text-[#FFCC00] font-['JetBrains_Mono']">{service.port}</span></p>
                    <p>Type: {service.type}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Grafana Embed Info */}
            <div className="bg-[#121212] border border-[#262626] rounded-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E]">Grafana Dashboard</h3>
                <a 
                  href={`${process.env.REACT_APP_BACKEND_URL}/api/grafana`}
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 bg-[#00FF9D] text-black px-4 py-2 rounded-lg hover:bg-[#00FF9D]/80 text-sm font-medium transition-colors"
                  data-testid="open-grafana-btn"
                >
                  <ExternalLink className="w-4 h-4" />
                  Open Grafana
                </a>
              </div>
              <div className="bg-[#1F1F1F] rounded-lg overflow-hidden">
                <iframe 
                  src={`${process.env.REACT_APP_BACKEND_URL}/api/grafana/d/spectral-resilience?orgId=1&kiosk&refresh=5s`}
                  className="w-full h-[600px] border-0"
                  title="Grafana Dashboard"
                  allow="fullscreen"
                  data-testid="grafana-iframe"
                />
              </div>
              <div className="mt-4 grid grid-cols-3 gap-4 text-sm">
                <div className="p-3 bg-[#262626] rounded text-center">
                  <p className="text-[#FFCC00] font-['JetBrains_Mono']">admin</p>
                  <p className="text-xs text-[#8A8A8E]">Username</p>
                </div>
                <div className="p-3 bg-[#262626] rounded text-center">
                  <p className="text-[#FFCC00] font-['JetBrains_Mono']">freshcart123</p>
                  <p className="text-xs text-[#8A8A8E]">Password</p>
                </div>
                <div className="p-3 bg-[#262626] rounded text-center">
                  <p className="text-[#00FF9D] font-['JetBrains_Mono']">Connected</p>
                  <p className="text-xs text-[#8A8A8E]">InfluxDB</p>
                </div>
              </div>
            </div>

            {/* Simulation Controls */}
            <div className="bg-[#121212] border border-[#262626] rounded-lg p-6">
              <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4">Failure Simulation</h3>
              <p className="text-sm text-[#8A8A8E] mb-4">Inject failures to test system resilience and observe SRI changes.</p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {['None', 'DB Overload', 'Latency Spike', 'Error Storm'].map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setConfig({ ...config, failure_mode: mode })}
                    className={`p-3 rounded-lg border transition-colors ${
                      config.failure_mode === mode 
                        ? 'border-[#FF3B30] bg-[#FF3B30]/10 text-[#FF3B30]' 
                        : 'border-[#262626] text-[#8A8A8E] hover:border-[#333]'
                    }`}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>
          </TabsContent>

          {/* Auto-Heal Tab */}
          <TabsContent value="autoheal" className="space-y-6" data-testid="autoheal-tab">
            {/* Engine Status Header */}
            <div className="bg-[#121212] border border-[#262626] rounded-lg p-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                    healingStatus?.enabled ? 'bg-[#00A3FF]/20' : 'bg-[#262626]'
                  }`}>
                    <Shield className={`w-6 h-6 ${healingStatus?.enabled ? 'text-[#00A3FF]' : 'text-[#8A8A8E]'}`} />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold font-['Outfit']">Auto-Healing Engine</h3>
                    <p className="text-sm text-[#8A8A8E]">
                      {healingStatus?.enabled && healingStatus?.alert_driven
                        ? 'Alert-driven healing active — reacting to alerts automatically' 
                        : healingStatus?.enabled 
                        ? 'Background healing active — checking every 15s' 
                        : 'Engine paused — manual triggers available'}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right mr-2">
                    <p className="text-xs text-[#8A8A8E]">Current SRI</p>
                    <p className={`text-2xl font-bold font-['JetBrains_Mono'] ${
                      (healingStatus?.current_sri || 0) > 0.3 ? 'text-[#00FF9D]' : (healingStatus?.current_sri || 0) > 0.1 ? 'text-[#FFCC00]' : 'text-[#FF3B30]'
                    }`}>
                      {(healingStatus?.current_sri || 0).toFixed(4)}
                    </p>
                  </div>
                  <div className="flex flex-col gap-2">
                    <Button
                      onClick={toggleAutoHeal}
                      size="sm"
                      className={`gap-2 ${
                        healingStatus?.enabled 
                          ? 'bg-[#FF3B30] hover:bg-[#FF3B30]/80 text-white' 
                          : 'bg-[#00A3FF] hover:bg-[#00A3FF]/80 text-white'
                      }`}
                      data-testid="toggle-autoheal-btn"
                    >
                      <Power className="w-3 h-3" />
                      {healingStatus?.enabled ? 'Disable' : 'Enable'}
                    </Button>
                    <Button
                      onClick={toggleAlertDriven}
                      size="sm"
                      variant="outline"
                      className={`gap-2 text-xs ${
                        healingStatus?.alert_driven
                          ? 'border-[#A855F7] text-[#A855F7]' 
                          : 'border-[#262626] text-[#8A8A8E]'
                      }`}
                      data-testid="toggle-alert-driven-btn"
                    >
                      <Bell className="w-3 h-3" />
                      Alert-Heal {healingStatus?.alert_driven ? 'ON' : 'OFF'}
                    </Button>
                  </div>
                </div>
              </div>

              {/* Active Healers */}
              {healingStatus?.active_healers?.length > 0 && (
                <div className="mt-4 pt-4 border-t border-[#262626]">
                  <p className="text-xs text-[#8A8A8E] mb-2">Active Healers</p>
                  <div className="flex flex-wrap gap-2">
                    {healingStatus.active_healers.map((h) => (
                      <span key={h.action_id} className="px-3 py-1 bg-[#00A3FF]/10 text-[#00A3FF] rounded-full text-xs font-medium">
                        {h.action_id.replace(/_/g, ' ')}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* SRI vs Golden Signals */}
            <div className="bg-[#121212] border border-[#262626] rounded-lg p-6" data-testid="sri-golden-signals">
              <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4 flex items-center gap-2">
                <Activity className="w-4 h-4 text-[#00A3FF]" />
                SRI vs Golden Signals — Signal Health
              </h3>
              <div className="grid grid-cols-4 gap-4 mb-4">
                {healingStatus?.golden_signals && Object.entries(healingStatus.golden_signals).map(([key, signal]) => {
                  const contrib = healingStatus?.signal_contributions?.[key] || 0;
                  const colors = { latency: '#00A3FF', traffic: '#00FF9D', errors: '#FF3B30', saturation: '#FFCC00' };
                  return (
                    <div key={key} className="text-center">
                      <div className="relative w-16 h-16 mx-auto mb-2">
                        <svg viewBox="0 0 36 36" className="w-16 h-16 -rotate-90">
                          <circle cx="18" cy="18" r="15" fill="none" stroke="#262626" strokeWidth="3" />
                          <circle cx="18" cy="18" r="15" fill="none" stroke={colors[key]} strokeWidth="3"
                            strokeDasharray={`${signal.health * 94.2} 94.2`} strokeLinecap="round" />
                        </svg>
                        <span className="absolute inset-0 flex items-center justify-center text-xs font-bold font-['JetBrains_Mono']" style={{color: colors[key]}}>
                          {(signal.health * 100).toFixed(0)}
                        </span>
                      </div>
                      <p className="text-xs font-medium capitalize">{key}</p>
                      <p className="text-[10px] text-[#8A8A8E]">{signal.value}{signal.unit === 'ms' ? 'ms' : signal.unit === '%' ? '%' : ` ${signal.unit}`}</p>
                      <p className="text-[10px] mt-1" style={{color: colors[key]}}>+{(contrib * 100).toFixed(0)}% SRI</p>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Recovery Path + Recommendations */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Recovery Path */}
              <div className="bg-[#121212] border border-[#262626] rounded-lg p-6">
                <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-[#00A3FF]" />
                  Recovery Path
                </h3>
                {healingStatus?.recommendations?.length > 0 ? (
                  <div className="space-y-3">
                    {(healingStatus.recommendations || []).map((rec, idx) => (
                      <div key={rec.action_id || `rec-${idx}`} className="relative">
                        {idx < (healingStatus.recommendations.length - 1) && (
                          <div className="absolute left-[18px] top-[44px] bottom-[-12px] w-px bg-[#262626]" />
                        )}
                        <div className="flex items-start gap-3">
                          <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 text-xs font-bold ${
                            rec.priority === 'critical' ? 'bg-[#FF3B30]/20 text-[#FF3B30]' :
                            rec.priority === 'high' ? 'bg-[#FFCC00]/20 text-[#FFCC00]' :
                            'bg-[#00A3FF]/20 text-[#00A3FF]'
                          }`}>
                            {idx + 1}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between">
                              <p className="font-medium text-sm">{rec.action_name}</p>
                              <span className={`text-xs px-2 py-0.5 rounded ${
                                rec.priority === 'critical' ? 'bg-[#FF3B30]/10 text-[#FF3B30]' :
                                rec.priority === 'high' ? 'bg-[#FFCC00]/10 text-[#FFCC00]' :
                                'bg-[#00A3FF]/10 text-[#00A3FF]'
                              }`}>{rec.priority}</span>
                            </div>
                            <p className="text-xs text-[#8A8A8E] mt-1">{rec.description}</p>
                            <div className="flex items-center gap-4 mt-2">
                              <span className="text-xs font-['JetBrains_Mono']">
                                <span className="text-[#8A8A8E]">SRI:</span>{' '}
                                <span className="text-[#FF3B30]">{rec.current_sri}</span>
                                <span className="text-[#8A8A8E]"> → </span>
                                <span className="text-[#00FF9D]">{rec.projected_sri}</span>
                              </span>
                              <span className="text-xs text-[#00FF9D]">+{(rec.sri_improvement * 100).toFixed(1)}%</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-[#8A8A8E]">
                    <CheckCircle className="w-10 h-10 mx-auto mb-3 text-[#00FF9D]" />
                    <p className="font-medium">No Recovery Needed</p>
                    <p className="text-xs mt-1">All nodes operating within thresholds</p>
                  </div>
                )}
              </div>

              {/* Healing Stats */}
              <div className="space-y-6">
                <div className="bg-[#121212] border border-[#262626] rounded-lg p-6">
                  <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4">Engine Stats</h3>
                  <div className="grid grid-cols-3 gap-4">
                    <div className="text-center">
                      <p className="text-2xl font-bold font-['JetBrains_Mono'] text-[#00A3FF]">
                        {healingStatus?.total_actions_executed || 0}
                      </p>
                      <p className="text-xs text-[#8A8A8E] mt-1">Total Actions</p>
                    </div>
                    <div className="text-center">
                      <p className="text-2xl font-bold font-['JetBrains_Mono'] text-[#00FF9D]">
                        {healingStatus?.active_healers?.length || 0}
                      </p>
                      <p className="text-xs text-[#8A8A8E] mt-1">Active Now</p>
                    </div>
                    <div className="text-center">
                      <p className="text-2xl font-bold font-['JetBrains_Mono'] text-[#FFCC00]">
                        {healingStatus?.recommendations?.length || 0}
                      </p>
                      <p className="text-xs text-[#8A8A8E] mt-1">Recommended</p>
                    </div>
                  </div>
                </div>

                {/* Node Health at a glance */}
                <div className="bg-[#121212] border border-[#262626] rounded-lg p-6">
                  <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4">Node Targets</h3>
                  <div className="space-y-3">
                    {healingStatus?.actions && Object.values(healingStatus.actions).map((action) => {
                      const rec = healingStatus.recommendations?.find(r => r.action_id === action.action_id);
                      return (
                        <div key={action.action_id} className="flex items-center justify-between py-2 border-b border-[#1F1F1F] last:border-0">
                          <div className="flex items-center gap-3">
                            <div className={`w-2 h-2 rounded-full ${rec ? 'bg-[#FFCC00] animate-pulse' : 'bg-[#00FF9D]'}`} />
                            <div>
                              <p className="text-sm font-medium">{action.target_node}</p>
                              <p className="text-xs text-[#8A8A8E]">{action.name}</p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            {rec && (
                              <span className="text-xs bg-[#FFCC00]/10 text-[#FFCC00] px-2 py-0.5 rounded">
                                needs heal
                              </span>
                            )}
                            <span className="text-xs text-[#8A8A8E] font-['JetBrains_Mono']">
                              x{action.execution_count}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>

            {/* Manual Action Triggers */}
            <div className="bg-[#121212] border border-[#262626] rounded-lg p-6">
              <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] mb-4 flex items-center gap-2">
                <Zap className="w-4 h-4 text-[#FFCC00]" />
                Manual Healing Actions
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
                {healingStatus?.actions && Object.values(healingStatus.actions).map((action) => (
                  <div key={action.action_id} className="bg-[#1F1F1F] rounded-lg p-4 border border-[#262626] hover:border-[#333] transition-colors">
                    <div className="flex items-center gap-2 mb-3">
                      {action.target_node === 'Cache' && <Database className="w-4 h-4 text-[#A855F7]" />}
                      {action.target_node === 'API' && <Globe className="w-4 h-4 text-[#00FF9D]" />}
                      {action.target_node === 'Backend' && <Server className="w-4 h-4 text-[#00A3FF]" />}
                      {action.target_node === 'DB' && <Database className="w-4 h-4 text-[#FFCC00]" />}
                      {action.target_node === 'Queue' && <RotateCcw className="w-4 h-4 text-[#FF3B30]" />}
                      <span className="font-medium text-sm">{action.name}</span>
                    </div>
                    <p className="text-xs text-[#8A8A8E] mb-3 line-clamp-2">{action.description}</p>
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs text-[#00FF9D] font-['JetBrains_Mono']">+{(action.sri_impact * 100).toFixed(0)}% SRI</span>
                      <span className="text-xs text-[#8A8A8E]">{action.cooldown}s cooldown</span>
                    </div>
                    <Button
                      onClick={() => triggerHealingAction(action.action_id)}
                      disabled={!action.can_execute || healingLoading}
                      size="sm"
                      className="w-full bg-[#262626] hover:bg-[#333] text-white disabled:opacity-40"
                      data-testid={`heal-${action.action_id}-btn`}
                    >
                      {action.can_execute ? (
                        <><Zap className="w-3 h-3 mr-1" /> Execute</>
                      ) : (
                        <><Clock className="w-3 h-3 mr-1" /> Cooldown</>
                      )}
                    </Button>
                  </div>
                ))}
              </div>
            </div>

            {/* Healing Timeline with Correction Factors */}
            <div className="bg-[#121212] border border-[#262626] rounded-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] flex items-center gap-2">
                  <Clock className="w-4 h-4 text-[#00A3FF]" />
                  Healing Timeline — Correction Factors
                </h3>
                <span className="text-xs text-[#8A8A8E]">{healingHistory.length} actions logged</span>
              </div>
              {healingHistory.length > 0 ? (
                <div className="space-y-3 max-h-[500px] overflow-y-auto">
                  {[...healingHistory].reverse().map((record, idx) => (
                    <div key={record.timestamp ? `${record.timestamp}-${record.action_id || idx}` : `heal-${idx}`} className="p-4 bg-[#1F1F1F] rounded-lg border border-[#262626]">
                      <div className="flex items-center gap-4">
                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                          record.sri_delta > 0 ? 'bg-[#00FF9D]/20' : 'bg-[#8A8A8E]/20'
                        }`}>
                          <Heart className={`w-4 h-4 ${record.sri_delta > 0 ? 'text-[#00FF9D]' : 'text-[#8A8A8E]'}`} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-medium text-sm">{record.action_name}</span>
                            <span className="text-xs px-2 py-0.5 rounded bg-[#262626] text-[#8A8A8E]">{record.target_node}</span>
                            <span className={`text-xs px-2 py-0.5 rounded ${
                              record.triggered_by === 'alert' ? 'bg-[#FF3B30]/10 text-[#FF3B30]' :
                              record.triggered_by === 'auto' ? 'bg-[#00A3FF]/10 text-[#00A3FF]' : 'bg-[#A855F7]/10 text-[#A855F7]'
                            }`}>{record.triggered_by}{record.trigger_alert ? ` (${record.trigger_alert})` : ''}</span>
                          </div>
                        </div>
                        <div className="text-right flex-shrink-0">
                          <div className="text-xs font-['JetBrains_Mono']">
                            <span className="text-[#FF3B30]">{record.sri_before}</span>
                            <span className="text-[#8A8A8E]"> → </span>
                            <span className="text-[#00FF9D]">{record.sri_after}</span>
                          </div>
                          <p className="text-[10px] text-[#6B6761] mt-1">
                            {new Date(record.timestamp).toLocaleTimeString()}
                          </p>
                        </div>
                      </div>
                      {/* Correction Factors per Golden Signal */}
                      {record.correction_factors && (
                        <div className="mt-3 pt-3 border-t border-[#262626]">
                          <p className="text-[10px] text-[#8A8A8E] mb-2 uppercase tracking-wider">Correction Factors</p>
                          <div className="grid grid-cols-4 gap-2">
                            {Object.entries(record.correction_factors).map(([signal, data]) => {
                              const colors = { latency: '#00A3FF', traffic: '#00FF9D', errors: '#FF3B30', saturation: '#FFCC00' };
                              return (
                                <div key={signal} className="text-center">
                                  <p className="text-[10px] capitalize" style={{color: colors[signal]}}>{signal}</p>
                                  <p className="text-xs font-['JetBrains_Mono'] font-bold" style={{color: data.delta > 0 ? '#00FF9D' : data.delta < 0 ? '#FF3B30' : '#8A8A8E'}}>
                                    {data.delta > 0 ? '+' : ''}{(data.delta * 100).toFixed(1)}%
                                  </p>
                                  <p className="text-[9px] text-[#8A8A8E]">CF: {(data.correction_factor * 100).toFixed(0)}%</p>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                      {/* Golden Signals Before/After */}
                      {record.golden_signals_before && record.golden_signals_after && (
                        <div className="mt-2 flex gap-4 text-[10px] text-[#8A8A8E]">
                          <span>Latency: {record.golden_signals_before.latency?.toFixed(0)}→{record.golden_signals_after.latency?.toFixed(0)}ms</span>
                          <span>Errors: {record.golden_signals_before.errors?.toFixed(1)}→{record.golden_signals_after.errors?.toFixed(1)}%</span>
                          <span>Saturation: {record.golden_signals_before.saturation?.toFixed(0)}→{record.golden_signals_after.saturation?.toFixed(0)}%</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-[#8A8A8E]">
                  <Shield className="w-10 h-10 mx-auto mb-3 opacity-30" />
                  <p>No healing actions taken yet</p>
                  <p className="text-xs mt-1">Trigger actions manually or enable auto-healing</p>
                </div>
              )}
            </div>
          </TabsContent>

          {/* ==================== RST TAB ==================== */}
          <TabsContent value="rst" className="space-y-6" data-testid="rst-tab">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <h2 className="text-lg font-bold text-white">Runtime Stiffness Tensor</h2>
                <p className="text-xs text-[#8A8A8E] mt-1">
                  Models each service as a structural element with a 6-component stiffness tensor K.
                  Effective stiffness K_eff encodes resilience via Hooke's law: ε = σ / K_eff.
                </p>
              </div>

              {/* Scenario selector */}
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs text-[#8A8A8E]">Scenario:</span>
                {SCENARIOS.map(sc => (
                  <button
                    key={sc.id}
                    onClick={() => applyRstScenario(sc.id)}
                    disabled={rstScenarioLoading}
                    className={`text-xs px-3 py-1.5 rounded font-medium transition-all ${
                      rstScenario === sc.id
                        ? 'bg-[#FF8C00] text-white'
                        : 'bg-[#2A2A2A] text-[#8A8A8E] hover:bg-[#333] hover:text-white'
                    }`}
                    title={sc.description}
                  >
                    {sc.name}
                  </button>
                ))}
              </div>
            </div>

            {/* Scenario description */}
            {rstScenario !== 'normal' && (
              <div className="bg-[#FF8C00]/10 border border-[#FF8C00]/30 rounded-lg p-3 text-xs text-[#FF8C00]">
                <span className="font-bold">Active scenario: </span>
                {SCENARIOS.find(s => s.id === rstScenario)?.description}
                <span className="text-[#8A8A8E]"> · expires in 60 s · click "Normal operation" to clear</span>
              </div>
            )}

            {/* Stiffness tensor composition heatmap */}
            <RSTCompositionPanel nodes={rstState?.nodes ?? {}} />

            {/* Stress / strain grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <StressStrainPanel
                nodes={rstState?.nodes ?? {}}
                history={rstHistory}
              />
              <SpectralResiliencePanel
                spectral={rstState?.spectral ?? {}}
                history={rstHistory}
              />
            </div>

            {/* Structural twin graph + spring analogy */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <StructuralTwinGraph nodes={rstState?.nodes ?? {}} />
              <PhysicalAnalogyView nodes={rstState?.nodes ?? {}} />
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
