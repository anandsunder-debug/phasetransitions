/**
 * RUM (Real User Monitoring) beacon.
 *
 * Captures real browser-side signals — page-load timing, JS errors,
 * unhandled promise rejections, Axios request latency, and long tasks —
 * and posts them to /api/rum/beacon every BATCH_INTERVAL_MS so the
 * backend's SRI engine treats the Frontend as a first-class topology node.
 */
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const BATCH_INTERVAL_MS = 5000;

let started = false;
let pageLoadCaptured = null;
let fcp = null;
let lcp = null;
let longTaskCount = 0;
let pendingApiCalls = [];
let pendingJsErrors = [];

function getOrCreateSessionId() {
  try {
    let sid = sessionStorage.getItem('rum_session_id');
    if (!sid) {
      sid = `rs-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
      sessionStorage.setItem('rum_session_id', sid);
    }
    return sid;
  } catch {
    return `rs-${Date.now()}`;
  }
}

function capturePageLoad() {
  try {
    const nav = performance.getEntriesByType?.('navigation')?.[0];
    if (nav && nav.loadEventEnd > 0) {
      pageLoadCaptured = Math.round(nav.loadEventEnd - nav.startTime);
    }
    const paintEntries = performance.getEntriesByType?.('paint') || [];
    const fcpEntry = paintEntries.find(p => p.name === 'first-contentful-paint');
    if (fcpEntry) fcp = Math.round(fcpEntry.startTime);
  } catch { /* noop */ }
}

function setupLongTaskObserver() {
  try {
    if (typeof PerformanceObserver === 'undefined') return;
    const obs = new PerformanceObserver((list) => {
      list.getEntries().forEach((entry) => {
        if (entry.duration > 50) longTaskCount += 1;
      });
    });
    obs.observe({ entryTypes: ['longtask'] });
  } catch { /* unsupported in some browsers */ }
}

function setupLcpObserver() {
  try {
    if (typeof PerformanceObserver === 'undefined') return;
    const obs = new PerformanceObserver((list) => {
      const entries = list.getEntries();
      if (entries.length > 0) {
        lcp = Math.round(entries[entries.length - 1].startTime);
      }
    });
    obs.observe({ entryTypes: ['largest-contentful-paint'] });
  } catch { /* unsupported */ }
}

function setupErrorListeners() {
  window.addEventListener('error', (ev) => {
    pendingJsErrors.push({
      message: (ev.error?.message || ev.message || 'unknown')?.toString().slice(0, 200),
      source: ev.filename?.toString().slice(-80) || 'unknown',
      line: ev.lineno || 0,
    });
    if (pendingJsErrors.length > 30) pendingJsErrors = pendingJsErrors.slice(-30);
  });
  window.addEventListener('unhandledrejection', (ev) => {
    pendingJsErrors.push({
      message: (ev.reason?.message || `${ev.reason}`)?.toString().slice(0, 200),
      source: 'unhandled-rejection',
      line: 0,
    });
    if (pendingJsErrors.length > 30) pendingJsErrors = pendingJsErrors.slice(-30);
  });
}

function setupAxiosInterceptors() {
  axios.interceptors.request.use((cfg) => {
    cfg.metadata = { startedAt: performance.now() };
    return cfg;
  });
  axios.interceptors.response.use(
    (resp) => {
      try {
        const path = (resp.config?.url || '').replace(API, '');
        if (path.startsWith('/rum/beacon')) return resp;  // skip our own beacon
        const dur = performance.now() - (resp.config?.metadata?.startedAt || performance.now());
        pendingApiCalls.push({
          path: path.slice(0, 80),
          duration_ms: Math.round(dur),
          status: resp.status,
          error: false,
        });
      } catch { /* noop */ }
      return resp;
    },
    (err) => {
      try {
        const cfg = err.config || {};
        const path = (cfg.url || '').replace(API, '');
        if (!path.startsWith('/rum/beacon')) {
          const dur = performance.now() - (cfg.metadata?.startedAt || performance.now());
          pendingApiCalls.push({
            path: path.slice(0, 80),
            duration_ms: Math.round(dur),
            status: err.response?.status || 0,
            error: true,
          });
        }
      } catch { /* noop */ }
      return Promise.reject(err);
    }
  );
}

async function flush() {
  if (!pageLoadCaptured) capturePageLoad();
  const apiCalls = pendingApiCalls.splice(0, 50);
  const jsErrors = pendingJsErrors.splice(0, 30);
  const longTasks = longTaskCount;
  longTaskCount = 0;

  // Skip empty beacons
  if (!pageLoadCaptured && apiCalls.length === 0 && jsErrors.length === 0 && longTasks === 0) {
    return;
  }

  const payload = {
    session_id: getOrCreateSessionId(),
    page: typeof window !== 'undefined' ? window.location.pathname : '',
    page_load_ms: pageLoadCaptured,
    first_contentful_paint_ms: fcp,
    largest_contentful_paint_ms: lcp,
    long_tasks_count: longTasks,
    api_calls: apiCalls,
    js_errors: jsErrors,
  };

  try {
    // Use sendBeacon when the page is unloading so we don't lose the last batch
    const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
    if (navigator.sendBeacon && document.visibilityState === 'hidden') {
      navigator.sendBeacon(`${API}/rum/beacon`, blob);
    } else {
      await fetch(`${API}/rum/beacon`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        credentials: 'include',
        keepalive: true,
      });
    }
  } catch { /* swallow */ }

  // Reset one-shot metrics so each beacon reflects only the new window
  pageLoadCaptured = null;
}

export function startRumBeacon() {
  if (started) return;
  started = true;

  setupErrorListeners();
  setupAxiosInterceptors();
  setupLongTaskObserver();
  setupLcpObserver();

  // Capture page-load on first paint after document is ready
  if (document.readyState === 'complete') {
    setTimeout(capturePageLoad, 0);
  } else {
    window.addEventListener('load', () => setTimeout(capturePageLoad, 0));
  }

  // Periodic flush
  setInterval(flush, BATCH_INTERVAL_MS);

  // Flush on visibility-hide (tab close/switch)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flush();
  });
}
