'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useOddsFormat } from '@/lib/contexts/OddsFormatContext';
import { useTheme } from '@/lib/contexts/ThemeContext';
import type { OddsFormat } from '@/lib/types';
import { cn } from '@/lib/utils/format';
import { Sun, Moon, X, Plus, Pencil, Check, ChevronDown, ChevronRight, Search, RefreshCw, Loader2 } from 'lucide-react';
import {
  getSynonyms,
  addSynonymGroup,
  updateSynonymGroup,
  deleteSynonymGroup,
  triggerRegroup,
  getGroupingStatus,
  type SynonymsResponse,
  type GroupingStatus,
} from '@/lib/api';

const ODDS_OPTIONS: { value: OddsFormat; label: string; example: string }[] = [
  { value: 'percentage', label: 'Percentage', example: '65.3%' },
  { value: 'decimal', label: 'Decimal', example: '1.53' },
  { value: 'fractional', label: 'Fractional', example: '13/20' },
];

const REFRESH_OPTIONS = [
  { value: 10, label: '10 seconds' },
  { value: 15, label: '15 seconds' },
  { value: 30, label: '30 seconds' },
  { value: 60, label: '1 minute' },
];

function SynonymSection() {
  const [synonyms, setSynonyms] = useState<SynonymsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newWords, setNewWords] = useState('');
  const [adding, setAdding] = useState(false);
  const [editIndex, setEditIndex] = useState<number | null>(null);
  const [editWords, setEditWords] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [showBuiltin, setShowBuiltin] = useState(false);

  const loadSynonyms = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getSynonyms();
      setSynonyms(data);
      setError(null);
    } catch {
      setError('Failed to load synonyms');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSynonyms();
  }, [loadSynonyms]);

  const handleAdd = async () => {
    const words = newWords.split(',').map((w) => w.trim()).filter(Boolean);
    if (words.length < 2) {
      setError('Enter at least 2 comma-separated words');
      return;
    }
    try {
      setAdding(true);
      setError(null);
      const result = await addSynonymGroup(words);
      setSynonyms((prev) => prev ? { ...prev, custom: result.custom } : prev);
      setNewWords('');
    } catch {
      setError('Failed to add synonym group');
    } finally {
      setAdding(false);
    }
  };

  const handleUpdate = async (index: number) => {
    const words = editWords.split(',').map((w) => w.trim()).filter(Boolean);
    if (words.length < 2) {
      setError('Each group needs at least 2 words');
      return;
    }
    try {
      setError(null);
      const result = await updateSynonymGroup(index, words);
      setSynonyms((prev) => prev ? { ...prev, custom: result.custom } : prev);
      setEditIndex(null);
    } catch {
      setError('Failed to update synonym group');
    }
  };

  const handleDelete = async (index: number) => {
    try {
      setError(null);
      const result = await deleteSynonymGroup(index);
      setSynonyms((prev) => prev ? { ...prev, custom: result.custom } : prev);
    } catch {
      setError('Failed to delete synonym group');
    }
  };

  const filterGroups = (groups: string[][]) => {
    if (!searchQuery) return groups;
    const q = searchQuery.toLowerCase();
    return groups.filter((group) =>
      group.some((word) => word.toLowerCase().includes(q))
    );
  };

  const filteredCustom = useMemo(
    () => (synonyms ? filterGroups(synonyms.custom) : []),
    [synonyms, searchQuery]
  );
  const filteredBuiltin = useMemo(
    () => (synonyms ? filterGroups(synonyms.builtin) : []),
    [synonyms, searchQuery]
  );

  if (loading) {
    return (
      <section className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading synonyms...
        </div>
      </section>
    );
  }

  return (
    <>
      <section className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-1 text-sm font-semibold text-gray-200">
          Word Equivalences
        </h2>
        <p className="mb-4 text-xs text-gray-500">
          Custom synonym groups for cross-platform market matching.
        </p>

        {error && (
          <div className="mb-3 rounded-lg border border-red-800 bg-red-900/20 px-3 py-2 text-xs text-red-400">
            {error}
          </div>
        )}

        {/* Search */}
        <div className="relative mb-4">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Filter synonyms..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-lg border border-gray-800 bg-gray-950 py-2 pl-9 pr-3 text-sm text-gray-200 placeholder-gray-600 focus:border-emerald-600 focus:outline-none"
          />
        </div>

        {/* Add form */}
        <div className="mb-4 flex gap-2">
          <input
            type="text"
            placeholder="crude, wti, west texas intermediate"
            value={newWords}
            onChange={(e) => setNewWords(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
            className="flex-1 rounded-lg border border-gray-800 bg-gray-950 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:border-emerald-600 focus:outline-none"
          />
          <button
            onClick={handleAdd}
            disabled={adding}
            className="flex items-center gap-1.5 rounded-lg border border-emerald-700 bg-emerald-900/30 px-3 py-2 text-sm font-medium text-emerald-400 transition-colors hover:bg-emerald-900/50 disabled:opacity-50"
          >
            {adding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
            Add
          </button>
        </div>

        {/* Custom groups */}
        <div className="space-y-2">
          {filteredCustom.length === 0 && !searchQuery && (
            <p className="text-xs text-gray-600">No custom synonym groups yet.</p>
          )}
          {filteredCustom.length === 0 && searchQuery && (
            <p className="text-xs text-gray-600">No matches found.</p>
          )}
          {filteredCustom.map((group, displayIdx) => {
            const realIndex = synonyms!.custom.indexOf(group);
            const isEditing = editIndex === realIndex;
            return (
              <div
                key={realIndex}
                className="flex items-center gap-2 rounded-lg border border-gray-800 px-3 py-2"
              >
                {isEditing ? (
                  <>
                    <input
                      type="text"
                      value={editWords}
                      onChange={(e) => setEditWords(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleUpdate(realIndex)}
                      className="flex-1 rounded border border-gray-700 bg-gray-950 px-2 py-1 text-sm text-gray-200 focus:border-emerald-600 focus:outline-none"
                      autoFocus
                    />
                    <button
                      onClick={() => handleUpdate(realIndex)}
                      className="rounded p-1 text-emerald-400 hover:bg-gray-800"
                    >
                      <Check className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => setEditIndex(null)}
                      className="rounded p-1 text-gray-500 hover:bg-gray-800"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </>
                ) : (
                  <>
                    <div className="flex flex-1 flex-wrap gap-1.5">
                      {group.map((word) => (
                        <span
                          key={word}
                          className="rounded-md bg-gray-800 px-2 py-0.5 text-xs text-gray-300"
                        >
                          {word}
                        </span>
                      ))}
                    </div>
                    <button
                      onClick={() => {
                        setEditIndex(realIndex);
                        setEditWords(group.join(', '));
                      }}
                      className="rounded p-1 text-gray-500 hover:bg-gray-800 hover:text-gray-300"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => handleDelete(realIndex)}
                      className="rounded p-1 text-gray-500 hover:bg-gray-800 hover:text-red-400"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </>
                )}
              </div>
            );
          })}
        </div>

        {/* Built-in synonyms (collapsed) */}
        <div className="mt-5 border-t border-gray-800 pt-4">
          <button
            onClick={() => setShowBuiltin(!showBuiltin)}
            className="flex items-center gap-1.5 text-xs font-medium text-gray-400 hover:text-gray-300"
          >
            {showBuiltin ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            Built-in Synonyms ({synonyms?.builtin.length ?? 0} groups)
          </button>
          {showBuiltin && (
            <div className="mt-3 space-y-1.5">
              {filteredBuiltin.map((group, i) => (
                <div
                  key={i}
                  className="flex flex-wrap gap-1.5 rounded-lg border border-gray-800/50 bg-gray-950/50 px-3 py-2"
                >
                  {group.map((word) => (
                    <span
                      key={word}
                      className="rounded-md bg-gray-800/60 px-2 py-0.5 text-xs text-gray-500"
                    >
                      {word}
                    </span>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </>
  );
}

function GroupingSection() {
  const [status, setStatus] = useState<GroupingStatus | null>(null);
  const [regroupState, setRegroupState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');

  const loadStatus = useCallback(async () => {
    try {
      const data = await getGroupingStatus();
      setStatus(data);
    } catch {
      // Status not critical
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const handleRegroup = async () => {
    try {
      setRegroupState('loading');
      await triggerRegroup();
      setRegroupState('success');
      // Refresh status after a delay to give grouping time to complete
      setTimeout(() => {
        loadStatus();
        setRegroupState('idle');
      }, 5000);
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'status' in err && (err as { status: number }).status === 409) {
        setRegroupState('error');
        setTimeout(() => setRegroupState('idle'), 3000);
      } else {
        setRegroupState('error');
        setTimeout(() => setRegroupState('idle'), 3000);
      }
    }
  };

  return (
    <section className="rounded-xl border border-gray-800 bg-gray-900 p-5">
      <h2 className="mb-1 text-sm font-semibold text-gray-200">Grouping</h2>
      <p className="mb-4 text-xs text-gray-500">
        Trigger a full cross-platform market regrouping.
      </p>

      <div className="flex items-center gap-4">
        <button
          onClick={handleRegroup}
          disabled={regroupState === 'loading'}
          className={cn(
            'flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition-all',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50',
            regroupState === 'success'
              ? 'border-emerald-600 bg-emerald-900/20 text-emerald-400'
              : regroupState === 'error'
                ? 'border-red-700 bg-red-900/20 text-red-400'
                : 'border-gray-700 text-gray-300 hover:border-gray-600 hover:text-white disabled:opacity-50'
          )}
        >
          {regroupState === 'loading' ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          {regroupState === 'loading'
            ? 'Running...'
            : regroupState === 'success'
              ? 'Started!'
              : regroupState === 'error'
                ? 'Already running'
                : 'Run Full Grouping'}
        </button>
      </div>

      {status && (
        <div className="mt-4 grid grid-cols-3 gap-3">
          <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
            <div className="text-lg font-semibold text-gray-200">
              {status.active_groups.toLocaleString()}
            </div>
            <div className="text-xs text-gray-500">Active Groups</div>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
            <div className="text-lg font-semibold text-gray-200">
              {status.total_markets_grouped.toLocaleString()}
            </div>
            <div className="text-xs text-gray-500">Markets Grouped</div>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
            <div className="text-sm font-medium text-gray-200">
              {status.last_run
                ? new Date(status.last_run).toLocaleString()
                : 'Never'}
            </div>
            <div className="text-xs text-gray-500">Last Run</div>
          </div>
        </div>
      )}
    </section>
  );
}

export default function SettingsPage() {
  const { oddsFormat, setOddsFormat } = useOddsFormat();
  const { theme, setTheme } = useTheme();
  const [refreshInterval, setRefreshInterval] = useState(15);

  useEffect(() => {
    const stored = localStorage.getItem('refreshInterval');
    if (stored) setRefreshInterval(parseInt(stored, 10));
  }, []);

  const handleRefreshChange = (val: number) => {
    setRefreshInterval(val);
    localStorage.setItem('refreshInterval', val.toString());
  };

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <h1 className="mb-1 text-2xl font-bold text-white">Settings</h1>
        <p className="text-sm text-gray-500">
          Customize your Polyarb experience.
        </p>
      </div>

      {/* Odds Format */}
      <section className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-1 text-sm font-semibold text-gray-200">
          Odds Format
        </h2>
        <p className="mb-4 text-xs text-gray-500">
          Choose how probabilities are displayed across the app.
        </p>
        <div className="space-y-2">
          {ODDS_OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className={cn(
                'flex cursor-pointer items-center justify-between rounded-lg border px-4 py-3 transition-all',
                oddsFormat === opt.value
                  ? 'border-emerald-600 bg-emerald-900/20'
                  : 'border-gray-800 hover:border-gray-700'
              )}
            >
              <div className="flex items-center gap-3">
                <input
                  type="radio"
                  name="oddsFormat"
                  value={opt.value}
                  checked={oddsFormat === opt.value}
                  onChange={() => setOddsFormat(opt.value)}
                  className="h-4 w-4 accent-emerald-500"
                />
                <div>
                  <div className="text-sm font-medium text-gray-200">
                    {opt.label}
                  </div>
                </div>
              </div>
              <span className="rounded-md bg-gray-800 px-2.5 py-1 text-xs font-mono text-gray-300">
                {opt.example}
              </span>
            </label>
          ))}
        </div>
      </section>

      {/* Refresh Interval */}
      <section className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-1 text-sm font-semibold text-gray-200">
          Refresh Interval
        </h2>
        <p className="mb-4 text-xs text-gray-500">
          How often data is automatically refreshed.
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {REFRESH_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => handleRefreshChange(opt.value)}
              className={cn(
                'rounded-lg border px-3 py-2 text-sm font-medium transition-all',
                refreshInterval === opt.value
                  ? 'border-emerald-600 bg-emerald-900/20 text-emerald-400'
                  : 'border-gray-800 text-gray-400 hover:border-gray-700 hover:text-gray-200',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50'
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </section>

      {/* Theme */}
      <section className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-1 text-sm font-semibold text-gray-200">Theme</h2>
        <p className="mb-4 text-xs text-gray-500">
          Toggle between dark and light mode.
        </p>
        <div className="flex gap-2">
          <button
            onClick={() => setTheme('dark')}
            className={cn(
              'flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition-all',
              theme === 'dark'
                ? 'border-emerald-600 bg-emerald-900/20 text-emerald-400'
                : 'border-gray-800 text-gray-400 hover:border-gray-700 hover:text-gray-200',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50'
            )}
          >
            <Moon className="h-4 w-4" /> Dark
          </button>
          <button
            onClick={() => setTheme('light')}
            className={cn(
              'flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition-all',
              theme === 'light'
                ? 'border-emerald-600 bg-emerald-900/20 text-emerald-400'
                : 'border-gray-800 text-gray-400 hover:border-gray-700 hover:text-gray-200',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50'
            )}
          >
            <Sun className="h-4 w-4" /> Light
          </button>
        </div>
      </section>

      {/* Word Equivalences */}
      <SynonymSection />

      {/* Grouping */}
      <GroupingSection />

      {/* About */}
      <section className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-1 text-sm font-semibold text-gray-200">About</h2>
        <p className="text-xs leading-relaxed text-gray-500">
          Polyarb aggregates prediction markets from Polymarket and Kalshi,
          detecting arbitrage opportunities in real-time. Data refreshes
          automatically and prices are sourced directly from each platform.
        </p>
        <div className="mt-3 text-xs text-gray-600">Version 0.1.0</div>
      </section>
    </div>
  );
}
