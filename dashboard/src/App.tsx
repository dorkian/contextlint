import { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import {
  RefreshCw,
  Terminal,
  Sun,
  Moon,
  Copy,
  Check,
  Search,
  Wrench,
  X,
  AlertCircle,
  AlertTriangle,
  Clock,
  Pencil,
  Inbox,
  ShieldAlert,
} from 'lucide-react';
import './index.css';

interface Asset {
  assistant: string;
  kind: string;
  name: string;
  loading: string;
  path: string | null;
  always_on_tokens: number;
  on_demand_tokens: number;
  id: string;
  meta?: any;
}

interface Finding {
  check: string;
  severity: string;
  title: string;
  detail: string;
  remediation: string;
  tokens_at_stake: number;
  path: string | null;
  confidence?: string;
  fixable?: boolean;
}

interface Dependency {
  skill: string;
  servers: string[];
  tokens: number;
}

interface ReportData {
  meta: {
    project: string;
    version: string;
    assistants_detected: string[];
    tokenizer: string;
    tokenizer_exact: boolean;
    mcp_probed: boolean;
    policy: {
      context_window: number;
    };
    usage?: {
      available: boolean;
      sessions: number;
      span_days: number;
      skills?: Record<string, { count: number; last_used?: string }>;
      mcp_servers?: Record<string, { count: number; last_used?: string }>;
    };
    elapsed_seconds?: number;
    generated_at?: string;
  };
  totals: {
    always_on_tokens: number;
    on_demand_tokens: number;
    recoverable_tokens: number;
    certain_tokens: number;
    candidate_tokens: number;
    asset_count: number;
    by_assistant: Record<string, number>;
    by_kind: Record<string, number>;
    by_severity: Record<string, number>;
  };
  assets: Asset[];
  findings: Finding[];
  dependencies?: Dependency[];
}

const SEV_TONES: Record<string, string> = {
  critical: 'crit',
  high: 'high',
  medium: 'med',
  low: 'low',
  info: 'info',
};

const PATH_STORAGE_KEY = 'contextlint_target_path';
const THEME_STORAGE_KEY = 'contextlint_theme';

// "Always-on cost by asset" column-chart geometry.
const BAR_W = 26, BAR_GAP = 6;
const BAR_PAD_L = 52, BAR_PAD_R = 16, BAR_PAD_T = 16, BAR_PAD_B = 96;
const BAR_PLOT_H = 260;

function fmt(n: number): string {
  return (n || 0).toLocaleString();
}

// ---------------------------------------------------------------------------
// Mechanism diagram: what actually costs tokens on every request, versus what
// only loads when the assistant reaches for it. Draws the split live from the
// current report rather than illustrating it once and hoping the numbers
// still match — the numbers move every time you re-run the audit.
// ---------------------------------------------------------------------------
function MechanismDiagram({ alwaysOn, onDemand }: { alwaysOn: number; onDemand: number }) {
  const total = alwaysOn + onDemand || 1;
  const alwaysPct = Math.round((alwaysOn / total) * 100);

  const W = 540, H = 176;
  const asset = { x: 12, y: 62, w: 106, h: 52 };
  const catalog = { x: 296, y: 14, w: 232, h: 60 };
  const body = { x: 296, y: 100, w: 232, h: 60 };

  const assetRight = { x: asset.x + asset.w, y: asset.y + asset.h / 2 };
  const catalogLeft = { x: catalog.x, y: catalog.y + catalog.h / 2 };
  const bodyLeft = { x: body.x, y: body.y + body.h / 2 };

  const pathTo = (from: { x: number; y: number }, to: { x: number; y: number }) => {
    const midX = from.x + (to.x - from.x) * 0.55;
    return `M ${from.x} ${from.y} C ${midX} ${from.y}, ${midX} ${to.y}, ${to.x} ${to.y}`;
  };

  return (
    <svg
      className="diagram-svg"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={`Diagram: an asset splits into a catalog entry costing ${fmt(
        alwaysOn
      )} tokens injected on every request, and a body costing ${fmt(onDemand)} tokens that only loads when invoked.`}
    >
      <defs>
        <marker id="arrow-accent" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L8,4 L0,8 z" fill="var(--accent)" />
        </marker>
        <marker id="arrow-muted" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L8,4 L0,8 z" fill="currentColor" opacity="0.5" />
        </marker>
      </defs>

      {/* edges, drawn first so nodes sit on top */}
      <path className="diagram-edge accent" d={pathTo(assetRight, catalogLeft)} markerEnd="url(#arrow-accent)" />
      <path className="diagram-edge dashed" d={pathTo(assetRight, bodyLeft)} markerEnd="url(#arrow-muted)" />

      <text className="edge-label accent" x={(assetRight.x + catalogLeft.x) / 2} y={catalog.y - 6} textAnchor="middle">
        every request
      </text>
      <text className="edge-label" x={(assetRight.x + bodyLeft.x) / 2} y={body.y + body.h + 16} textAnchor="middle">
        only when invoked
      </text>

      <g className="diagram-node">
        <rect x={asset.x} y={asset.y} width={asset.w} height={asset.h} rx={8} />
        <text className="title" x={asset.x + asset.w / 2} y={asset.y + 22} textAnchor="middle">
          Any asset
        </text>
        <text className="sub" x={asset.x + asset.w / 2} y={asset.y + 38} textAnchor="middle">
          skill · rule · memory
        </text>
      </g>

      <g className="diagram-node accent">
        <rect x={catalog.x} y={catalog.y} width={catalog.w} height={catalog.h} rx={8} />
        <text className="title" x={catalog.x + 16} y={catalog.y + 24}>
          Catalog entry
        </text>
        <text className="sub" x={catalog.x + 16} y={catalog.y + 42}>
          {fmt(alwaysOn)} tok · {alwaysPct}% of the pair
        </text>
      </g>

      <g className="diagram-node">
        <rect x={body.x} y={body.y} width={body.w} height={body.h} rx={8} strokeDasharray="4 3" />
        <text className="title" x={body.x + 16} y={body.y + 24}>
          Body
        </text>
        <text className="sub" x={body.x + 16} y={body.y + 42}>
          {fmt(onDemand)} tok · loads on demand
        </text>
      </g>
    </svg>
  );
}

function SkeletonOverview() {
  return (
    <div className="overview" aria-hidden="true">
      <div className="hero-row">
        <div className="hero-number-block">
          <span className="skeleton" style={{ display: 'inline-block', width: 180, height: 44 }}>
            0
          </span>
        </div>
      </div>
      <span className="skeleton window-bar" style={{ display: 'block' }} />
      <div className="overview-grid">
        <div className="overview-card">
          <span className="skeleton" style={{ display: 'block', height: 176, borderRadius: 8 }} />
        </div>
        <div className="overview-card">
          <span className="skeleton" style={{ display: 'block', height: 176, borderRadius: 8 }} />
        </div>
      </div>
    </div>
  );
}

type FixPhase = 'confirm' | 'running' | 'dirty' | 'result';

export default function App() {
  const [data, setData] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Every animation on this page is now plain CSS, which already respects
  // prefers-reduced-motion globally (index.css). This is only for the one
  // JS-driven scroll, which CSS can't gate on its own.
  const reduceMotion = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Settings / filters
  const [includeGlobal, setIncludeGlobal] = useState(false);
  const [mcpProbe, setMcpProbe] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState<string | null>(null);
  const [selectedSeverity, setSelectedSeverity] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);

  // Target path — the dashboard defaulted to auditing only its own repo,
  // with no way to point it anywhere else even though the API always
  // supported it. Click-to-edit, remembered per browser. ?path= in the URL
  // wins over the remembered value, so an audit is linkable/shareable and a
  // bookmark or CI dashboard can point at a fixed project on every load.
  const [targetPath, setTargetPath] = useState<string>(() => {
    const fromUrl = new URLSearchParams(window.location.search).get('path');
    return fromUrl ?? localStorage.getItem(PATH_STORAGE_KEY) ?? '';
  });
  const [editingPath, setEditingPath] = useState(false);
  const [pathDraft, setPathDraft] = useState(targetPath);
  const pathInputRef = useRef<HTMLInputElement>(null);

  // Modals
  const [cliModalOpen, setCliModalOpen] = useState(false);
  const [cliOutput, setCliOutput] = useState<string>('');
  const [cliLoading, setCliLoading] = useState(false);

  const [fixModalOpen, setFixModalOpen] = useState(false);
  const [fixPhase, setFixPhase] = useState<FixPhase>('confirm');
  const [fixResult, setFixResult] = useState<{ success: boolean; output: string } | null>(null);

  // Theme
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    return (localStorage.getItem(THEME_STORAGE_KEY) as 'light' | 'dark') || 'dark';
  });

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    localStorage.setItem(THEME_STORAGE_KEY, next);
  };

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  useEffect(() => {
    if (editingPath) pathInputRef.current?.focus();
  }, [editingPath]);

  // Fetch report data
  const fetchReport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        no_global: String(!includeGlobal),
        mcp_probe: String(mcpProbe),
      });
      if (targetPath) params.set('path', targetPath);
      const res = await fetch(`/api/report?${params}`);
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.details || errJson.error || `HTTP error ${res.status}`);
      }
      const json: ReportData = await res.json();
      setData(json);
      setLastRefreshed(new Date().toLocaleTimeString());
    } catch (err: any) {
      setError(err.message || 'Failed to load report');
    } finally {
      setLoading(false);
    }
  }, [includeGlobal, mcpProbe, targetPath]);

  useEffect(() => {
    fetchReport();
  }, [fetchReport]);

  const submitPath = (e: React.FormEvent) => {
    e.preventDefault();
    const next = pathDraft.trim();
    setTargetPath(next);
    localStorage.setItem(PATH_STORAGE_KEY, next);
    setEditingPath(false);
  };

  // Enter is handled explicitly rather than relying only on implicit
  // form-submit-on-Enter — that behavior is spec'd for a single-input form,
  // but not every environment fires it reliably, and there's no visible
  // submit button here to fall back on either.
  const handlePathKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      setEditingPath(false);
      // Both `key` and `code` are checked: some input paths (IME composition,
      // certain automation/remote-input layers) deliver `key: 'Unidentified'`
      // while `code` still reports the physical key correctly.
    } else if (e.key === 'Enter' || e.code === 'Enter' || e.code === 'NumpadEnter') {
      e.preventDefault();
      submitPath(e);
    }
  };

  // View CLI terminal output
  const handleOpenCliModal = async () => {
    setCliModalOpen(true);
    setCliLoading(true);
    try {
      const params = new URLSearchParams({
        no_global: String(!includeGlobal),
        mcp_probe: String(mcpProbe),
      });
      if (targetPath) params.set('path', targetPath);
      const res = await fetch(`/api/terminal-report?${params}`);
      const json = await res.json();
      setCliOutput(json.output || 'No output received');
    } catch (err: any) {
      setCliOutput(`Error loading CLI output: ${err.message}`);
    } finally {
      setCliLoading(false);
    }
  };

  // Fix flow: confirm -> running -> (dirty | result). "dirty" mirrors the
  // CLI's own git-guard rather than the UI silently passing --allow-dirty on
  // every run, which would quietly remove the one safety net contextlint's
  // own design is built around.
  const openFixModal = () => {
    setFixPhase('confirm');
    setFixResult(null);
    setFixModalOpen(true);
  };

  const runFix = async (allowDirty: boolean) => {
    setFixPhase('running');
    try {
      const res = await fetch('/api/run-command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'fix', path: targetPath || undefined, allow_dirty: allowDirty }),
      });
      const json = await res.json();
      if (json.dirty && !allowDirty) {
        setFixPhase('dirty');
        return;
      }
      setFixResult({ success: json.success, output: json.output || json.error || 'Done' });
      setFixPhase('result');
      fetchReport();
    } catch (err: any) {
      setFixResult({ success: false, output: err.message });
      setFixPhase('result');
    }
  };

  // Copy path helper
  const [copiedPath, setCopiedPath] = useState<string | null>(null);
  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedPath(text);
    setTimeout(() => setCopiedPath(null), 2000);
  };

  // "Always-on cost by asset" as a column chart: one bar per asset, sorted
  // descending, height ∝ token cost, an actual value axis instead of area
  // encoding — precise ranking reads better as bars than as a treemap, and a
  // treemap with a single asset (a small project audited on its own) renders
  // as one undifferentiated block that looks broken rather than sparse.
  const barChartData = useMemo(() => {
    if (!data) return null;
    const assets = (data.assets || [])
      .filter((a) => a.always_on_tokens > 0)
      .sort((a, b) => b.always_on_tokens - a.always_on_tokens)
      .slice(0, 80);
    if (assets.length === 0) return null;

    const invokedSkills = new Set(Object.keys(data.meta.usage?.skills || {}));
    const maxTokens = Math.max(...assets.map((a) => a.always_on_tokens), 1);
    const width = BAR_PAD_L + assets.length * (BAR_W + BAR_GAP) - BAR_GAP + BAR_PAD_R;
    const height = BAR_PAD_T + BAR_PLOT_H + BAR_PAD_B;

    const bars = assets.map((a, idx) => {
      let tone = 'memory';
      if (a.kind === 'skill' || a.kind === 'agent' || a.kind === 'command') {
        tone = invokedSkills.has(a.name) ? 'used' : 'unused';
      } else if (a.kind === 'mcp_server') {
        tone = 'mcp';
      }
      // Square-root scaled, same as the usage scatter chart below: with one
      // dominant file, a linear scale flattens every other bar to a sliver
      // and the ranking becomes unreadable for all but the top few. The axis
      // still shows real token values — only the pixel mapping is transformed.
      const h = Math.max(Math.sqrt(a.always_on_tokens / maxTokens) * BAR_PLOT_H, 1);
      const x = BAR_PAD_L + idx * (BAR_W + BAR_GAP);
      const y = BAR_PAD_T + (BAR_PLOT_H - h);
      const label = a.name.length > 15 ? a.name.slice(0, 14) + '…' : a.name;
      return { asset: a, x, y, w: BAR_W, h, tone, label };
    });

    const gridLines = [0, 1, 2, 3, 4].map((i) => {
      const gy = BAR_PAD_T + (BAR_PLOT_H * i) / 4;
      return { gy, val: Math.round(maxTokens * (1 - i / 4) ** 2) };
    });

    return { bars, gridLines, width, height };
  }, [data]);

  // Scatter plot points
  const scatterData = useMemo(() => {
    if (!data || !data.meta.usage?.available) return null;
    const skills = (data.assets || []).filter((a) => ['skill', 'agent', 'command'].includes(a.kind));
    if (skills.length === 0) return null;

    const stats = data.meta.usage.skills || {};
    const pts = skills.map((a) => ({
      asset: a,
      count: stats[a.name]?.count || 0,
    }));

    const maxUses = Math.max(...pts.map((p) => p.count), 1);
    const maxCost = Math.max(...pts.map((p) => p.asset.always_on_tokens), 1);

    const width = 940;
    const height = 280;
    const padL = 54;
    const padB = 38;
    const padT = 16;
    const padR = 16;
    const pw = width - padL - padR;
    const ph = height - padB - padT;

    const points = pts.map((p) => {
      const px = padL + (p.count ** 0.5 / maxUses ** 0.5) * pw;
      const py = padT + ph - (p.asset.always_on_tokens / maxCost) * ph;
      const r = 3.5 + Math.min(p.asset.always_on_tokens / maxCost, 1) * 5;
      const tone = p.count === 0 ? 'unused' : 'used';
      return {
        ...p,
        px,
        py,
        r,
        tone,
      };
    });

    const gridLines = [0, 1, 2, 3, 4].map((i) => {
      const gy = padT + (ph * i) / 4;
      const val = Math.round(maxCost * (1 - i / 4));
      return { gy, val };
    });

    return {
      points,
      gridLines,
      maxUses,
      maxCost,
      width,
      height,
      padL,
      padR,
      padT,
    };
  }, [data]);

  // Filtered findings
  const filteredFindings = useMemo(() => {
    if (!data) return [];
    let list = data.findings || [];
    if (selectedSeverity !== 'all') {
      list = list.filter((f) => f.severity === selectedSeverity);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(
        (f) =>
          f.title.toLowerCase().includes(q) ||
          f.detail.toLowerCase().includes(q) ||
          (f.path && f.path.toLowerCase().includes(q))
      );
    }
    return list;
  }, [data, selectedSeverity, searchQuery]);

  // Real usage top rankings
  const topSkills = useMemo(() => {
    if (!data?.meta.usage?.skills) return [];
    return Object.entries(data.meta.usage.skills)
      .sort((a, b) => b[1].count - a[1].count)
      .slice(0, 8);
  }, [data]);

  const topMcpServers = useMemo(() => {
    if (!data?.meta.usage?.mcp_servers) return [];
    return Object.entries(data.meta.usage.mcp_servers)
      .sort((a, b) => b[1].count - a[1].count)
      .slice(0, 8);
  }, [data]);

  // Caveats list matching report.html
  const caveats = useMemo(() => {
    if (!data) return [];
    const list: string[] = [];
    if (!data.meta.tokenizer_exact) {
      list.push(
        `Token counts come from contextlint's offline heuristic (${data.meta.tokenizer}), not a real tokenizer. Measured error is published in benchmarks/.`
      );
    }
    if (!data.meta.mcp_probed && (data.assets || []).some((a) => a.kind === 'mcp_server')) {
      list.push(
        'MCP tool-schema cost is not included in these totals. Configuration cannot reveal it; toggle MCP Probe to measure live servers.'
      );
    }
    if (!data.meta.usage?.available) {
      list.push('No session history was found, so nothing distinguishes an unused asset from a heavily used one.');
    }
    list.push('Security findings audit static configuration declarations. Contextlint is not a penetration test and cannot guarantee server implementation safety.');
    return list;
  }, [data]);

  if (error && !data) {
    return (
      <div className="dashboard-wrap" style={{ textAlign: 'center', paddingTop: '80px' }}>
        <AlertCircle size={36} color="var(--crit)" style={{ margin: '0 auto 16px' }} />
        <h2 style={{ justifyContent: 'center', color: 'var(--crit)' }}>Audit Failed</h2>
        <p className="section-desc" style={{ marginBottom: '20px' }}>{error}</p>
        <button className="btn primary" onClick={() => fetchReport()}>
          <RefreshCw size={14} /> Retry Audit
        </button>
      </div>
    );
  }

  if (loading && !data) {
    return (
      <div className="dashboard-wrap">
        <header className="header-bar">
          <div className="brand-area">
            <h1>
              contextlint <span className="brand-badge">auditing…</span>
            </h1>
          </div>
        </header>
        <SkeletonOverview />
      </div>
    );
  }

  if (!data) return null;

  const { meta, totals } = data;
  const contextWindow = meta.policy.context_window || 200000;
  const windowShare = totals.always_on_tokens ? (totals.always_on_tokens / contextWindow) * 100 : 0;
  const sevCounts = totals.by_severity || {};
  const riskCount = (sevCounts.critical || 0) + (sevCounts.high || 0);
  const splitTotal = totals.always_on_tokens || 1;
  const certainPct = Math.min((totals.certain_tokens / splitTotal) * 100, 100);
  const candidatePct = Math.min((totals.candidate_tokens / splitTotal) * 100, 100);

  return (
    <div className="dashboard-wrap">
      {/* Header Bar */}
      <header className="header-bar">
        <div className="brand-area">
          <h1>
            contextlint
            <span className="brand-badge">v{meta.version}</span>
            {riskCount > 0 && (
              <button
                className="risk-chip"
                onClick={() => document.getElementById('findings-section')?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' })}
                title="Jump to findings"
              >
                <ShieldAlert size={12} /> {riskCount} need attention
              </button>
            )}
          </h1>
          <div className="project-meta">
            {editingPath ? (
              <form className="path-edit-form" onSubmit={submitPath}>
                <input
                  ref={pathInputRef}
                  className="path-edit-input mono"
                  value={pathDraft}
                  onChange={(e) => setPathDraft(e.target.value)}
                  onBlur={() => setEditingPath(false)}
                  onKeyDown={handlePathKeyDown}
                  placeholder=". (this project)"
                />
                <span className="path-edit-hint">↵ audit · esc cancel</span>
              </form>
            ) : (
              <button
                className="path-edit-trigger mono"
                onClick={() => {
                  setPathDraft(targetPath);
                  setEditingPath(true);
                }}
                title="Click to audit a different directory"
              >
                <span title={meta.project}>{meta.project.length > 46 ? '…' + meta.project.slice(-44) : meta.project}</span>
                <Pencil size={11} />
              </button>
            )}
            <span className="sep">·</span>
            <span>assistants: {meta.assistants_detected.join(', ') || 'none'}</span>
            <span className="sep">·</span>
            <span>tokenizer: {meta.tokenizer} {meta.tokenizer_exact ? '(exact)' : '(heuristic)'}</span>
            {lastRefreshed && (
              <>
                <span className="sep">·</span>
                <span className="toast-badge">
                  <Clock size={12} /> Refreshed {lastRefreshed}
                </span>
              </>
            )}
          </div>
        </div>

        {/* Action Toolbar */}
        <div className="toolbar-actions">
          {/* Scope Selector */}
          <div className="scope-toggle" title="Select audit scope">
            <button
              className={`scope-btn ${!includeGlobal ? 'active' : ''}`}
              onClick={() => setIncludeGlobal(false)}
            >
              Project only
            </button>
            <button
              className={`scope-btn ${includeGlobal ? 'active' : ''}`}
              onClick={() => setIncludeGlobal(true)}
            >
              Full (~/ incl.)
            </button>
          </div>

          {/* MCP Live Probe Toggle */}
          <button
            className={`btn ${mcpProbe ? 'active' : ''}`}
            title="Start live MCP servers to probe real tool schemas"
            onClick={() => setMcpProbe(!mcpProbe)}
          >
            MCP Probe {mcpProbe ? 'On' : 'Off'}
          </button>

          {/* Re-run Audit Button */}
          <button
            className="btn primary"
            disabled={loading}
            onClick={() => fetchReport()}
            title="Re-run audit and refresh dashboard data"
          >
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            {loading ? 'Auditing...' : 'Re-Run Audit'}
          </button>

          {/* Apply Fixes Button */}
          <button
            className="btn"
            onClick={openFixModal}
            title="Review and apply safe automatic fixes"
          >
            <Wrench size={14} />
            Apply Fixes
          </button>

          {/* View CLI Terminal Output */}
          <button
            className="btn btn-icon"
            onClick={handleOpenCliModal}
            title="View raw CLI report"
          >
            <Terminal size={15} />
          </button>

          {/* Theme Toggle */}
          <button
            className="btn btn-icon"
            onClick={toggleTheme}
            title="Toggle Light / Dark mode"
          >
            {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
          </button>
        </div>
      </header>

      {/* Overview — the whole story before any scrolling */}
      <div className="overview">
        <div className="hero-row">
          <div className="hero-number-block">
            <span className="hero-number">{fmt(totals.always_on_tokens)}</span>
            <span className="hero-label">tokens load before you type a word</span>
          </div>
          <div className="hero-share">
            of a <strong>{contextWindow.toLocaleString()}</strong>-token window, this is{' '}
            <strong style={{ color: windowShare >= 15 ? 'var(--crit)' : windowShare >= 5 ? 'var(--unused)' : 'var(--used)' }}>
              {windowShare.toFixed(1)}%
            </strong>
          </div>
        </div>
        <div className="window-bar">
          <div
            className="window-bar-fill"
            style={{
              width: `${Math.min(windowShare, 100)}%`,
              background: windowShare >= 15 ? 'var(--crit)' : windowShare >= 5 ? 'var(--unused)' : 'var(--used)',
            }}
          />
          <div className="window-bar-tick" style={{ left: '5%' }} title="5% warn threshold" />
          <div className="window-bar-tick" style={{ left: '15%' }} title="15% fail threshold" />
        </div>

        <div className="overview-grid">
          <figure className="overview-card diagram-figure">
            <h3>How context gets loaded</h3>
            <div className="overview-card-desc">Every asset splits in two — only one half is always-on.</div>
            <MechanismDiagram alwaysOn={totals.always_on_tokens} onDemand={totals.on_demand_tokens} />
            <figcaption>
              Only the catalog entry — {fmt(totals.always_on_tokens)} tokens — is injected on every request. The body ({fmt(totals.on_demand_tokens)} tokens) loads only when the assistant actually reaches for it.
            </figcaption>
          </figure>

          <div className="overview-card">
            <h3>What's recoverable</h3>
            <div className="overview-card-desc">Two different kinds of savings — never added together.</div>
            <div className="split-bars">
              <div className="split-row">
                <div className="split-top">
                  <span className="split-name" style={{ color: 'var(--used)' }}>Safe to reclaim</span>
                  <span className="split-value" style={{ color: 'var(--used)' }}>{fmt(totals.certain_tokens)} tok</span>
                </div>
                <div className="split-track">
                  <div className="split-fill" style={{ background: 'var(--used)', width: `${certainPct}%` }} />
                </div>
                <div className="split-note">Duplicates and empty assets — removing them can't change behaviour.</div>
              </div>
              <div className="split-row">
                <div className="split-top">
                  <span className="split-name" style={{ color: 'var(--unused)' }}>Worth reviewing</span>
                  <span className="split-value" style={{ color: 'var(--unused)' }}>{fmt(totals.candidate_tokens)} tok</span>
                </div>
                <div className="split-track">
                  <div className="split-fill" style={{ background: 'var(--unused)', width: `${candidatePct}%` }} />
                </div>
                <div className="split-note">Unused skills, an uncalled server — each one is a judgement call.</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Detail strip */}
      <div className="stats-grid">
        <div className="stat-box">
          <div className="k">assets</div>
          <div className="v">{totals.asset_count.toLocaleString()}</div>
          <div className="hint">rules, skills, memory</div>
        </div>
        <div className="stat-box">
          <div className="k">sessions read</div>
          <div className="v">{(meta.usage?.sessions || 0).toLocaleString()}</div>
          <div className="hint">{(meta.usage?.span_days ?? 0).toFixed(0)} days recorded</div>
        </div>
        <div className="stat-box">
          <div className="k">findings</div>
          <div className="v">{data.findings.length.toLocaleString()}</div>
          <div className="hint" style={{ color: riskCount > 0 ? 'var(--crit)' : undefined }}>
            {riskCount} crit/high
          </div>
        </div>
        <div className="stat-box">
          <div className="k">execution time</div>
          <div className="v">{meta.elapsed_seconds ? `${meta.elapsed_seconds.toFixed(1)}s` : '—'}</div>
          <div className="hint">last audit run</div>
        </div>
      </div>

      {/* Section 1: Always-on cost by asset (column chart) */}
      <h2>Always-on cost by asset</h2>
      <div className="card">
        {barChartData ? (
          <svg
            viewBox={`0 0 ${barChartData.width} ${barChartData.height}`}
            width={barChartData.width}
            height={barChartData.height}
            className="bar-chart-svg"
            role="img"
            aria-label="Always-on token cost by asset, ranked highest to lowest"
          >
            {barChartData.gridLines.map((g, i) => (
              <g key={i}>
                <line className="grid" x1={BAR_PAD_L} y1={g.gy} x2={barChartData.width - BAR_PAD_R} y2={g.gy} />
                <text className="axis" x={BAR_PAD_L - 8} y={g.gy + 4} textAnchor="end">
                  {g.val.toLocaleString()}
                </text>
              </g>
            ))}
            <line
              className="axis-baseline"
              x1={BAR_PAD_L}
              y1={BAR_PAD_T + BAR_PLOT_H}
              x2={barChartData.width - BAR_PAD_R}
              y2={BAR_PAD_T + BAR_PLOT_H}
            />
            {barChartData.bars.map((bar, idx) => {
              const labelY = BAR_PAD_T + BAR_PLOT_H + 14;
              const labelX = bar.x + bar.w / 2;
              return (
                <g key={idx} className={`col ${bar.tone}`} onClick={() => setSelectedAsset(bar.asset)}>
                  <title>
                    {`${bar.asset.name}\n${bar.asset.assistant} / ${bar.asset.kind}\n${bar.asset.always_on_tokens.toLocaleString()} always-on tokens\nloading: ${bar.asset.loading}`}
                  </title>
                  <rect x={bar.x.toFixed(1)} y={bar.y.toFixed(1)} width={bar.w} height={bar.h.toFixed(1)} rx={2} />
                  <text
                    className="col-label"
                    x={labelX.toFixed(1)}
                    y={labelY}
                    textAnchor="end"
                    transform={`rotate(-55 ${labelX.toFixed(1)} ${labelY})`}
                  >
                    {bar.label}
                  </text>
                </g>
              );
            })}
          </svg>
        ) : (
          <div className="empty">
            <Inbox size={22} />
            No always-on assets found.
          </div>
        )}
      </div>

      <div className="legend">
        <span><i style={{ background: 'var(--used)' }} />skill, used</span>
        <span><i style={{ background: 'var(--unused)' }} />skill, never invoked</span>
        <span><i style={{ background: 'var(--mcp)' }} />MCP server</span>
        <span><i style={{ background: 'var(--memory)' }} />memory / instructions</span>
      </div>
      <div className="section-desc">
        Bar height is always-on token cost, ranked highest to lowest and square-root scaled so the long tail stays legible next to any one dominant file — axis values are the real numbers. This is what you pay on every request before typing a word, not the size of the file on disk. Click any bar to inspect details.
      </div>

      {/* Asset Quick Inspector when clicked */}
      {selectedAsset && (
        <div className="asset-inspector reveal-in">
          <div>
            <span className="asset-title">{selectedAsset.name}</span>
            <span style={{ color: 'var(--mute)', marginLeft: '8px' }}>
              ({selectedAsset.assistant} / {selectedAsset.kind})
            </span>
          </div>
          <div>
            <strong>{selectedAsset.always_on_tokens.toLocaleString()}</strong> always-on tokens
          </div>
          <div>loading: <code>{selectedAsset.loading}</code></div>
          {selectedAsset.path && (
            <div className="mono" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span>{selectedAsset.path}</span>
              <button
                className="copy-path-btn"
                onClick={() => copyToClipboard(selectedAsset.path!)}
                title="Copy file path"
              >
                {copiedPath === selectedAsset.path ? <Check size={12} color="var(--used)" /> : <Copy size={12} />}
              </button>
            </div>
          )}
          <button
            style={{ background: 'none', border: 'none', cursor: 'pointer', marginLeft: 'auto' }}
            onClick={() => setSelectedAsset(null)}
            aria-label="Close inspector"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Section 2: Cost against real usage (Scatter Plot) */}
      <h2>Cost against real usage</h2>
      <div className="card">
        {scatterData ? (
          <svg
            viewBox={`0 0 ${scatterData.width} ${scatterData.height}`}
            className="scatter-svg"
            role="img"
            aria-label="Always-on cost plotted against real invocation count"
          >
            {/* Grid lines */}
            {scatterData.gridLines.map((g, i) => (
              <g key={i}>
                <line
                  className="grid"
                  x1={scatterData.padL}
                  y1={g.gy.toFixed(1)}
                  x2={scatterData.width - scatterData.padR}
                  y2={g.gy.toFixed(1)}
                />
                <text className="axis" x="6" y={(g.gy + 4).toFixed(1)}>
                  {g.val.toLocaleString()}
                </text>
              </g>
            ))}

            <text className="axis" x={scatterData.padL} y={scatterData.height - 10}>
              never used
            </text>
            <text className="axis" textAnchor="end" x={scatterData.width - scatterData.padR} y={scatterData.height - 10}>
              {scatterData.maxUses} invocations
            </text>
            <text className="axis" x="6" y={scatterData.padT - 4}>
              tokens
            </text>

            {/* Points */}
            {scatterData.points.map((p, idx) => (
              <g
                key={idx}
                className={`pt ${p.tone}`}
                onClick={() => setSelectedAsset(p.asset)}
              >
                <title>{`${p.asset.name}\n${p.asset.always_on_tokens.toLocaleString()} always-on tokens\n${p.count} invocation(s)`}</title>
                <circle cx={p.px.toFixed(1)} cy={p.py.toFixed(1)} r={p.r.toFixed(1)} />
              </g>
            ))}
          </svg>
        ) : (
          <div className="empty">
            <Inbox size={22} />
            No session history available.
            <span className="empty-hint">Cost can't be plotted against real usage without it. Transcripts from ~/.claude/projects or Codex sessions will be reflected here automatically.</span>
          </div>
        )}
      </div>
      <div className="section-desc">
        Anything high and to the left costs you on every request and has never once been invoked. Horizontal axis is square-root scaled.
      </div>

      {/* Section 3: Where It Goes & Real Usage Insights */}
      <div className="columns-two" style={{ marginTop: '36px' }}>
        {/* Where It Goes */}
        <div>
          <h2>Where it goes</h2>
          <div className="card">
            <div style={{ fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--mute)', marginBottom: '8px' }}>
              By Assistant
            </div>
            <div className="breakdown-list" style={{ marginBottom: '18px' }}>
              {Object.entries(totals.by_assistant || {}).map(([assistant, tok]) => {
                const pct = totals.always_on_tokens ? (tok / totals.always_on_tokens) * 100 : 0;
                return (
                  <div key={assistant} className="breakdown-item">
                    <div className="breakdown-labels">
                      <span className="name">{assistant}</span>
                      <span className="tokens">{tok.toLocaleString()} tok ({pct.toFixed(1)}%)</span>
                    </div>
                    <div className="bar-track">
                      <div className="bar-fill" style={{ width: `${pct}%`, background: 'var(--mcp)' }} />
                    </div>
                  </div>
                );
              })}
            </div>

            <div style={{ fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--mute)', marginBottom: '8px' }}>
              By Kind
            </div>
            <div className="breakdown-list">
              {Object.entries(totals.by_kind || {}).map(([kind, tok]) => {
                const pct = totals.always_on_tokens ? (tok / totals.always_on_tokens) * 100 : 0;
                return (
                  <div key={kind} className="breakdown-item">
                    <div className="breakdown-labels">
                      <span className="name">{kind}</span>
                      <span className="tokens">{tok.toLocaleString()} tok ({pct.toFixed(1)}%)</span>
                    </div>
                    <div className="bar-track">
                      <div className="bar-fill" style={{ width: `${pct}%`, background: 'var(--memory)' }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Real Usage Insights */}
        <div>
          <h2>Real usage insights</h2>
          <div className="card">
            {meta.usage?.available ? (
              <>
                <div style={{ fontSize: '13px', marginBottom: '12px' }}>
                  <strong>{meta.usage.sessions}</strong> sessions analyzed over <strong>{meta.usage.span_days.toFixed(0)}</strong> days.
                </div>

                <div style={{ fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--mute)', marginBottom: '6px' }}>
                  Most Invoked Skills
                </div>
                <div className="badge-list" style={{ marginBottom: '18px' }}>
                  {topSkills.map(([skill, stat]) => (
                    <span key={skill} className="usage-badge">
                      {skill} <span className="count">{stat.count}×</span>
                    </span>
                  ))}
                  {topSkills.length === 0 && <span style={{ color: 'var(--mute)', fontSize: '12px' }}>No skills invoked</span>}
                </div>

                <div style={{ fontWeight: 600, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--mute)', marginBottom: '6px' }}>
                  Active MCP Servers
                </div>
                <div className="badge-list">
                  {topMcpServers.map(([server, stat]) => (
                    <span key={server} className="usage-badge">
                      {server} <span className="count">{stat.count}×</span>
                    </span>
                  ))}
                  {topMcpServers.length === 0 && <span style={{ color: 'var(--mute)', fontSize: '12px' }}>No MCP servers logged</span>}
                </div>
              </>
            ) : (
              <div className="empty">
                <Inbox size={22} />
                No session transcripts discovered in active profiles.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Section 4: Skills that reference an MCP server */}
      <h2>Skills that reference an MCP server</h2>
      <div className="card table-wrap">
        <table>
          <thead>
            <tr>
              <th>Skill</th>
              <th>Referenced Servers</th>
              <th className="num">Always-on tokens</th>
            </tr>
          </thead>
          <tbody>
            {(data.dependencies || []).length > 0 ? (
              data.dependencies!.slice(0, 25).map((dep, idx) => (
                <tr key={idx}>
                  <td><strong>{dep.skill}</strong></td>
                  <td>{dep.servers.join(', ')}</td>
                  <td className="num">{dep.tokens.toLocaleString()}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={3} className="empty">
                  No skill references an MCP server by name.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Section 5: Interactive Findings */}
      <h2 id="findings-section">Findings ({data.findings.length})</h2>
      <div className="findings-controls">
        <div className="filters">
          {(['all', 'critical', 'high', 'medium', 'low', 'info'] as const).map((sev) => {
            const count = sev === 'all' ? data.findings.length : sevCounts[sev] || 0;
            return (
              <button
                key={sev}
                aria-pressed={selectedSeverity === sev}
                onClick={() => setSelectedSeverity(sev)}
              >
                {sev} {count}
              </button>
            );
          })}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Search size={14} color="var(--mute)" />
          <input
            type="text"
            className="search-input"
            placeholder="Filter findings or paths..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      <div className="findings-list">
        {filteredFindings.map((f, idx) => {
          const tone = SEV_TONES[f.severity] || 'info';
          // check+title alone collides for real: two byte-identical duplicate
          // skills produce the exact same hygiene finding text, once per copy
          // — which is precisely the case this tool exists to surface. Path
          // disambiguates those; idx is the final tiebreaker for the rest.
          return (
            <div key={`${f.check}-${f.path ?? f.title}-${idx}`} className={`f-card ${tone}`}>
              <div className="top">
                <span className="sev">{f.severity}</span>
                {f.confidence === 'certain' ? (
                  <span className="brand-badge" style={{ background: 'var(--used-subtle)', color: 'var(--used)', border: '1px solid var(--used)' }} title="Deterministic fact: removing this cannot change behavior">
                    Certain
                  </span>
                ) : (
                  <span className="brand-badge" style={{ background: 'var(--line)', color: 'var(--mute)' }} title="Judgment call: requires review before acting">
                    Review
                  </span>
                )}
                <span className="t">{f.title}</span>
                {f.tokens_at_stake > 0 && (
                  <span className="cost">−{f.tokens_at_stake.toLocaleString()} tok</span>
                )}
                {f.fixable && (
                  <span className="brand-badge" style={{ background: 'var(--used-subtle)', color: 'var(--used)' }}>
                    Fixable
                  </span>
                )}
              </div>
              <div className="d">{f.detail}</div>
              {f.remediation && <div className="r">→ {f.remediation}</div>}
              {f.path && (
                <div className="p">
                  <span>{f.path}</span>
                  <button
                    className="copy-path-btn"
                    onClick={() => copyToClipboard(f.path!)}
                    title="Copy path"
                  >
                    {copiedPath === f.path ? <Check size={12} color="var(--used)" /> : <Copy size={12} />}
                  </button>
                </div>
              )}
            </div>
          );
        })}

        {filteredFindings.length === 0 && (
          <div className="empty">
            <Inbox size={22} />
            {selectedSeverity === 'all' ? 'No findings reported.' : `No findings at severity "${selectedSeverity}".`}
          </div>
        )}
      </div>

      {/* Section 6: What this report does not know (Caveats) */}
      <h2>What this report does not know</h2>
      <div className="caveats-card">
        <ul>
          {caveats.map((c, idx) => (
            <li key={idx}>{c}</li>
          ))}
          {caveats.length === 0 && (
            <li>None — every number here was measured directly from config and live servers.</li>
          )}
        </ul>
      </div>

      {/* Footer */}
      <footer>
        <div>
          Generated by contextlint. Every number above is reproducible from this machine's configuration and transcripts; nothing was sent anywhere.
        </div>
      </footer>

      {/* CLI Output Modal */}
      {cliModalOpen && (
        <div className="modal-overlay reveal-in" onClick={() => setCliModalOpen(false)}>
          <div className="modal-box reveal-in-box" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>
                <Terminal size={16} /> CLI Terminal Output
              </h3>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button className="btn" onClick={() => copyToClipboard(cliOutput)}>
                  <Copy size={13} /> Copy
                </button>
                <button className="modal-close" onClick={() => setCliModalOpen(false)} aria-label="Close">
                  <X size={18} />
                </button>
              </div>
            </div>
            <div className="modal-body">
              {cliLoading ? (
                <div style={{ textAlign: 'center', padding: '30px' }}>
                  <RefreshCw className="spin" size={20} style={{ margin: '0 auto 8px' }} />
                  <div>Running CLI audit...</div>
                </div>
              ) : (
                <pre className="terminal-view">{cliOutput}</pre>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Fix Modal: confirm -> running -> dirty | result */}
      {fixModalOpen && (
        <div
          className="modal-overlay reveal-in"
          onClick={() => fixPhase !== 'running' && setFixModalOpen(false)}
        >
          <div
            className="modal-box reveal-in-box"
            style={{ maxWidth: 560 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3>
                <Wrench size={16} /> Apply Fixes
              </h3>
              {fixPhase !== 'running' && (
                <button className="modal-close" onClick={() => setFixModalOpen(false)} aria-label="Close">
                  <X size={18} />
                </button>
              )}
            </div>
            <div className="modal-body">
              {fixPhase === 'confirm' && (
                <div className="fix-confirm">
                  <p>
                    Removes only what's provably safe — byte-identical duplicates and empty assets. Everything
                    that needs judgement stays in the report untouched.
                  </p>
                  <div className="fix-note">
                    Every removal is copied to <code>.contextlint-backups/</code> with a manifest first.
                    Reversible with <code>contextlint restore</code> — nothing is deleted outright.
                  </div>
                  <div className="fix-confirm-actions">
                    <button className="btn" onClick={() => setFixModalOpen(false)}>Cancel</button>
                    <button className="btn primary" onClick={() => runFix(false)}>
                      <Wrench size={13} /> Apply
                    </button>
                  </div>
                </div>
              )}
              {fixPhase === 'running' && (
                <div style={{ textAlign: 'center', padding: '30px' }}>
                  <RefreshCw className="spin" size={20} style={{ margin: '0 auto 8px' }} />
                  <div>Applying fixes...</div>
                </div>
              )}
              {fixPhase === 'dirty' && (
                <div className="dirty-tree-note">
                  <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                    <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
                    <div>
                      contextlint refused: the working tree has uncommitted changes, so <code>git checkout .</code>{' '}
                      wouldn't be a clean undo. Commit or stash first, or force through it — the backup still
                      makes this reversible either way.
                    </div>
                  </div>
                  <div className="fix-confirm-actions">
                    <button className="btn" onClick={() => setFixModalOpen(false)}>Cancel</button>
                    <button className="btn primary" onClick={() => runFix(true)}>
                      Force anyway
                    </button>
                  </div>
                </div>
              )}
              {fixPhase === 'result' && fixResult && (
                <pre className="terminal-view">{fixResult.output}</pre>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
