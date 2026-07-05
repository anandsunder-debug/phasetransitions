import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Webhook, Send, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function WebhookSettingsCard() {
  const [status, setStatus] = useState(null);
  const [sending, setSending] = useState(false);
  const [lastResult, setLastResult] = useState(null);

  const fetchStatus = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/admin/webhooks/status`, { withCredentials: true });
      setStatus(data);
    } catch (e) {
      setStatus({ error: e?.response?.data?.detail || 'Failed to load' });
    }
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const handleTest = async () => {
    setSending(true);
    setLastResult(null);
    try {
      const { data } = await axios.post(`${API}/admin/webhooks/test`, {}, { withCredentials: true });
      setLastResult(data);
      const results = data?.results || {};
      if (results.skipped) {
        toast.warning(`Test skipped: ${results.reason}`);
      } else {
        const oks = Object.entries(results).filter(([, v]) => v?.ok);
        const fails = Object.entries(results).filter(([, v]) => !v?.ok);
        if (oks.length) toast.success(`Test sent: ${oks.map(([k]) => k).join(', ')}`);
        if (fails.length) toast.error(`Failed: ${fails.map(([k, v]) => `${k} (${v?.status || v?.error || 'err'})`).join(', ')}`);
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Webhook test failed');
    } finally {
      setSending(false);
    }
  };

  const cfg = status?.configured || {};
  const anyConfigured = !!status?.any_configured;

  return (
    <div className="bg-[#121212] border border-[#262626] rounded-lg p-6" data-testid="webhook-settings-card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm uppercase tracking-[0.2em] text-[#8A8A8E] flex items-center gap-2">
          <Webhook className="w-4 h-4 text-[#5AC8FA]" />
          External Webhook Notifications
        </h3>
        <button
          onClick={handleTest}
          disabled={sending || !anyConfigured}
          className={`text-xs px-3 py-1.5 rounded border flex items-center gap-1.5 transition ${
            anyConfigured
              ? 'bg-[#5AC8FA]/10 border-[#5AC8FA]/40 text-[#5AC8FA] hover:bg-[#5AC8FA]/20'
              : 'bg-[#1F1F1F] border-[#262626] text-[#8A8A8E] cursor-not-allowed'
          }`}
          data-testid="webhook-test-btn"
        >
          <Send className="w-3 h-3" />
          {sending ? 'Sending…' : 'Send Test Alert'}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-3">
        <div className="p-3 bg-[#1F1F1F] rounded-lg flex items-center justify-between" data-testid="webhook-slack-status">
          <span className="text-sm text-[#FFFFFF]">Slack</span>
          {cfg.slack ? (
            <span className="text-xs flex items-center gap-1 text-[#00FF9D]"><CheckCircle className="w-3 h-3" /> Configured</span>
          ) : (
            <span className="text-xs flex items-center gap-1 text-[#8A8A8E]"><XCircle className="w-3 h-3" /> Not set</span>
          )}
        </div>
        <div className="p-3 bg-[#1F1F1F] rounded-lg flex items-center justify-between" data-testid="webhook-discord-status">
          <span className="text-sm text-[#FFFFFF]">Discord</span>
          {cfg.discord ? (
            <span className="text-xs flex items-center gap-1 text-[#00FF9D]"><CheckCircle className="w-3 h-3" /> Configured</span>
          ) : (
            <span className="text-xs flex items-center gap-1 text-[#8A8A8E]"><XCircle className="w-3 h-3" /> Not set</span>
          )}
        </div>
      </div>

      {!anyConfigured && (
        <div className="p-3 bg-[#FFCC00]/10 border border-[#FFCC00]/30 rounded-lg text-xs text-[#FFCC00] flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <div>
            Add <code className="font-mono">SLACK_WEBHOOK_URL</code> and/or <code className="font-mono">DISCORD_WEBHOOK_URL</code> to <code className="font-mono">backend/.env</code> and restart the backend to enable critical-alert delivery.
          </div>
        </div>
      )}

      {anyConfigured && (
        <p className="text-[10px] text-[#8A8A8E]">
          Fires on <strong className="text-[#FF3B30]">critical</strong> alerts only. Cooldown: {status?.cooldown_seconds || 120}s per alert key.
        </p>
      )}

      {lastResult?.results && !lastResult.results.skipped && (
        <div className="mt-3 p-2 bg-[#0F0F0F] rounded text-[10px] font-mono text-[#8A8A8E]" data-testid="webhook-last-result">
          {Object.entries(lastResult.results).map(([k, v]) => (
            <div key={k}>
              {k}: {v.ok ? `✓ ${v.status}` : `✗ ${v.status || v.error}`}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
