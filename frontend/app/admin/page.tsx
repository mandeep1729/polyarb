'use client';

import { useState, useMemo, useRef, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getAdminStats, type AdminStats } from '@/lib/api';
import { cn } from '@/lib/utils/format';
import { Search, AlertCircle, X } from 'lucide-react';

// --- Health indicator logic ---

type Health = 'green' | 'yellow' | 'red' | 'unknown';

function syncHealth(isoStr: string | null): Health {
  if (!isoStr) return 'unknown';
  const ageMs = Date.now() - new Date(isoStr).getTime();
  const ageMin = ageMs / 60_000;
  if (ageMin < 30) return 'green';
  if (ageMin < 120) return 'yellow';
  return 'red';
}

function pctHealth(value: number, greenAbove: number, yellowAbove: number): Health {
  if (value >= greenAbove) return 'green';
  if (value >= yellowAbove) return 'yellow';
  return 'red';
}

function taskHealth(task: { last_run: string; status: string; interval_seconds: number }): Health {
  if (task.status === 'error') return 'red';
  const ageMs = Date.now() - new Date(task.last_run).getTime();
  const ageSec = ageMs / 1000;
  if (ageSec < task.interval_seconds * 2) return 'green';
  if (ageSec < task.interval_seconds * 5) return 'yellow';
  return 'red';
}

const DOT_COLORS: Record<Health, string> = {
  green: 'bg-emerald-500',
  yellow: 'bg-yellow-500',
  red: 'bg-red-500',
  unknown: 'bg-gray-600',
};

function Dot({ health }: { health: Health }) {
  return <span className={cn('inline-block h-2 w-2 rounded-full', DOT_COLORS[health])} />;
}

// --- Stat card ---

function StatCard({ label, value, health, sub }: { label: string; value: string | number; health?: Health; sub?: string }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
      <div className="flex items-center gap-2">
        {health && <Dot health={health} />}
        <span className="text-lg font-semibold text-gray-100">{value}</span>
      </div>
      <div className="text-xs text-gray-500">{label}</div>
      {sub && <div className="mt-0.5 text-[10px] text-gray-600">{sub}</div>}
    </div>
  );
}

// --- Overview Tab ---

function OverviewTab({ data }: { data: AdminStats }) {
  const totalMarkets = data.platform_stats.reduce((s, p) => s + p.total, 0);

  return (
    <div className="space-y-6">
      {/* Platform Stats */}
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">Platform Stats</h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {data.platform_stats.map((p) => (
            <StatCard
              key={p.slug}
              label={p.name}
              value={p.total.toLocaleString()}
              health={syncHealth(data.sync_health[p.slug])}
              sub={`${p.active.toLocaleString()} active · ${p.expired.toLocaleString()} expired`}
            />
          ))}
          <StatCard label="Total Markets" value={totalMarkets.toLocaleString()} />
        </div>
      </section>

      {/* Sync Health */}
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">Sync Health</h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {data.platform_stats.map((p) => {
            const syncTs = data.sync_health[p.slug];
            const h = syncHealth(syncTs);
            return (
              <StatCard
                key={p.slug}
                label={`${p.name} last sync`}
                value={syncTs ? new Date(syncTs).toLocaleTimeString() : 'Never'}
                health={h}
                sub={syncTs ? new Date(syncTs).toLocaleDateString() : undefined}
              />
            );
          })}
        </div>
      </section>

      {/* Market Freshness */}
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">Market Freshness</h3>
        <div className="grid grid-cols-4 gap-3">
          <StatCard label="Last 1h" value={data.freshness.last_1h.toLocaleString()} health={data.freshness.last_1h > 100 ? 'green' : data.freshness.last_1h > 10 ? 'yellow' : 'red'} />
          <StatCard label="Last 6h" value={data.freshness.last_6h.toLocaleString()} />
          <StatCard label="Last 24h" value={data.freshness.last_24h.toLocaleString()} />
          <StatCard label="Older" value={data.freshness.older.toLocaleString()} />
        </div>
      </section>

      {/* Data Quality */}
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">Data Quality</h3>
        <div className="grid grid-cols-3 gap-3">
          <StatCard label="Has end date" value={`${data.data_quality.pct_end_date}%`} health={pctHealth(data.data_quality.pct_end_date, 80, 50)} />
          <StatCard label="Has price history" value={`${data.data_quality.pct_price_history}%`} health={pctHealth(data.data_quality.pct_price_history, 50, 10)} />
          <StatCard label="Categorized" value={`${data.data_quality.pct_categorized}%`} health={pctHealth(data.data_quality.pct_categorized, 80, 50)} />
        </div>
      </section>

      {/* Price History Coverage */}
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">Price History Coverage</h3>
        <div className="grid grid-cols-4 gap-3">
          <StatCard label="No history" value={data.price_coverage.zero.toLocaleString()} health={data.price_coverage.zero === 0 ? 'green' : 'yellow'} />
          <StatCard label="1–10 snapshots" value={data.price_coverage['1_to_10'].toLocaleString()} />
          <StatCard label="11–100 snapshots" value={data.price_coverage['11_to_100'].toLocaleString()} />
          <StatCard label="100+ snapshots" value={data.price_coverage['100_plus'].toLocaleString()} />
        </div>
      </section>

      {/* Background Tasks */}
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">Background Tasks</h3>
        {Object.keys(data.task_status).length === 0 ? (
          <p className="text-xs text-gray-600">No task runs recorded yet (tasks haven't executed since last restart).</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-800">
            <table className="w-full text-xs">
              <thead className="bg-gray-900 text-gray-500">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Task</th>
                  <th className="px-3 py-2 text-left font-medium">Status</th>
                  <th className="px-3 py-2 text-left font-medium">Last Run</th>
                  <th className="px-3 py-2 text-left font-medium">Duration</th>
                  <th className="px-3 py-2 text-left font-medium">Interval</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {Object.entries(data.task_status).map(([id, t]) => (
                  <tr key={id} className="text-gray-300">
                    <td className="px-3 py-2 font-mono">{id}</td>
                    <td className="px-3 py-2"><Dot health={taskHealth(t)} /> <span className="ml-1">{t.status}</span></td>
                    <td className="px-3 py-2">{new Date(t.last_run).toLocaleString()}</td>
                    <td className="px-3 py-2">{t.duration_seconds}s</td>
                    <td className="px-3 py-2">{Math.round(t.interval_seconds / 60)}m</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Arbitrage Health */}
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">Arbitrage Health</h3>
        {data.arbitrage.total_pairs === 0 ? (
          <p className="text-xs text-gray-600">No arbitrage pairs detected.</p>
        ) : (
          <div className="grid grid-cols-4 gap-3">
            <StatCard label="Total pairs" value={data.arbitrage.total_pairs.toLocaleString()} />
            <StatCard label="Arb pairs (>1%)" value={data.arbitrage.arb_pairs.toLocaleString()} />
            <StatCard label="Avg spread" value={`${(data.arbitrage.avg_spread * 100).toFixed(1)}%`} />
            <StatCard label="Best spread" value={`${(data.arbitrage.best_spread * 100).toFixed(1)}%`} />
          </div>
        )}
      </section>

      {/* Grouping Health */}
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">Grouping Health</h3>
        {data.grouping.total_active === 0 ? (
          <p className="text-xs text-gray-600">No groups formed yet.</p>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            <StatCard label="Active groups" value={data.grouping.total_active.toLocaleString()} />
            <StatCard label="Cross-platform" value={data.grouping.cross_platform.toLocaleString()} health={pctHealth(data.grouping.cross_platform_pct, 10, 5)} sub={`${data.grouping.cross_platform_pct}%`} />
            <StatCard label="Avg members" value={data.grouping.avg_members.toString()} />
            <StatCard label="High disagreement" value={data.grouping.high_disagreement.toLocaleString()} sub="> 5% spread" />
          </div>
        )}
      </section>

      {/* Top 10 Markets by Price History */}
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">Top 10 Markets by Price History</h3>
        {data.top_markets.length === 0 ? (
          <p className="text-xs text-gray-600">No price history — backfill not yet run.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-800">
            <table className="w-full text-xs">
              <thead className="bg-gray-900 text-gray-500">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Market</th>
                  <th className="px-3 py-2 text-left font-medium">Platform</th>
                  <th className="px-3 py-2 text-right font-medium">Snapshots</th>
                  <th className="px-3 py-2 text-left font-medium">Range</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {data.top_markets.map((m) => (
                  <tr key={m.id} className="text-gray-300">
                    <td className="max-w-xs truncate px-3 py-2">{m.question}</td>
                    <td className="px-3 py-2 capitalize">{m.platform}</td>
                    <td className="px-3 py-2 text-right font-mono">{m.snapshot_count}</td>
                    <td className="px-3 py-2 text-gray-500">
                      {m.earliest ? new Date(m.earliest).toLocaleDateString() : '—'}
                      {' → '}
                      {m.latest ? new Date(m.latest).toLocaleDateString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

// --- Tags Tab ---

const DEFAULT_TAG_COUNT = 100;

function TagsTab({ data }: { data: AdminStats }) {
  const [search, setSearch] = useState('');
  const [showSuggestions, setShowSuggestions] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  // Close suggestions on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  // Autocomplete suggestions: show when 3+ chars typed
  const suggestions = useMemo(() => {
    if (search.length < 3) return [];
    const q = search.toLowerCase();
    return data.tags
      .filter((t) => String(t.term).toLowerCase().includes(q))
      .slice(0, 10);
  }, [data.tags, search]);

  // Table data: if searching, show all matches; otherwise top 100
  const tableData = useMemo(() => {
    if (search) {
      const q = search.toLowerCase();
      return data.tags.filter((t) => String(t.term).toLowerCase().includes(q));
    }
    return data.tags.slice(0, DEFAULT_TAG_COUNT);
  }, [data.tags, search]);

  const selectSuggestion = (term: string) => {
    setSearch(term);
    setShowSuggestions(false);
  };

  return (
    <div className="space-y-3">
      {/* Search with autocomplete */}
      <div ref={wrapperRef} className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-500" />
        <input
          ref={inputRef}
          type="text"
          placeholder="Search tags (3+ chars for suggestions)..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setShowSuggestions(e.target.value.length >= 3);
          }}
          onFocus={() => { if (search.length >= 3) setShowSuggestions(true); }}
          className="w-full rounded-lg border border-gray-800 bg-gray-900 py-2 pl-9 pr-8 text-sm text-gray-200 placeholder-gray-600 focus:border-emerald-600 focus:outline-none"
        />
        {search && (
          <button
            onClick={() => { setSearch(''); setShowSuggestions(false); }}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}

        {/* Autocomplete dropdown */}
        {showSuggestions && suggestions.length > 0 && (
          <div className="absolute z-20 mt-1 w-full rounded-lg border border-gray-700 bg-gray-900 py-1 shadow-lg">
            {suggestions.map((s) => (
              <button
                key={String(s.term)}
                onClick={() => selectSuggestion(String(s.term))}
                className="flex w-full items-center justify-between px-3 py-1.5 text-left text-sm text-gray-300 hover:bg-gray-800"
              >
                <span>{String(s.term)}</span>
                <span className="text-xs text-gray-600">{Number(s.total).toLocaleString()}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="w-full text-xs">
          <thead className="bg-gray-900 text-gray-500">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Term</th>
              <th className="px-3 py-2 text-right font-medium">Total</th>
              {data.platform_slugs.map((slug) => (
                <th key={slug} className="px-3 py-2 text-right font-medium capitalize">{slug}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {tableData.map((tag) => (
              <tr key={String(tag.term)} className="text-gray-300">
                <td className="px-3 py-2 font-medium">{String(tag.term)}</td>
                <td className="px-3 py-2 text-right font-mono">{Number(tag.total).toLocaleString()}</td>
                {data.platform_slugs.map((slug) => (
                  <td key={slug} className="px-3 py-2 text-right font-mono text-gray-500">
                    {Number(tag[slug] ?? 0).toLocaleString()}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-gray-600">
        {search
          ? `${tableData.length} matches`
          : `Showing top ${Math.min(DEFAULT_TAG_COUNT, data.tags.length)} of ${data.tags.length} tags`}
      </p>
    </div>
  );
}

// --- Main Page ---

const TABS = ['Overview', 'Tags'] as const;
type Tab = (typeof TABS)[number];

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState<Tab>('Overview');

  const { data, isLoading, error } = useQuery({
    queryKey: ['adminStats'],
    queryFn: getAdminStats,
    refetchInterval: 30_000,
  });

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 pt-6">
      <div>
        <h1 className="mb-1 text-2xl font-bold text-white">Admin Dashboard</h1>
        <p className="text-sm text-gray-500">System health and platform metrics at a glance.</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-800">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              'px-4 py-2 text-sm font-medium transition-colors',
              activeTab === tab
                ? 'border-b-2 border-emerald-500 text-emerald-400'
                : 'text-gray-500 hover:text-gray-300'
            )}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Content */}
      {error ? (
        <div className="flex items-center gap-2 rounded-lg border border-red-800 bg-red-900/20 px-4 py-3 text-sm text-red-400">
          <AlertCircle className="h-4 w-4" />
          Cannot connect to backend. Check that the API is running.
        </div>
      ) : isLoading || !data ? (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-700 border-t-emerald-500" />
        </div>
      ) : (
        <>
          {activeTab === 'Overview' && <OverviewTab data={data} />}
          {activeTab === 'Tags' && <TagsTab data={data} />}
        </>
      )}
    </div>
  );
}
