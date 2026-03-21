'use client';

import { Suspense, useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { useQueryState } from 'nuqs';
import { useQuery } from '@tanstack/react-query';
import { searchAdminTags, getMarketTags } from '@/lib/api';
import ExpiryFilter, { type DateRange } from '@/components/markets/ExpiryFilter';
import UnifiedMarketList from '@/components/markets/UnifiedMarketList';
import TagBar from '@/components/groups/TagCloud';
import ErrorBoundary from '@/components/shared/ErrorBoundary';
import PairBar from '@/components/markets/PairBar';
import { useMarketCategoryCounts } from '@/lib/queries/useCategoryCounts';
import type { Market } from '@/lib/types';
import { X, Search, Link2 } from 'lucide-react';

// Convert date-only strings to EST timestamps for inclusive range
const startOfDay = (date: string) => `${date}T00:00:00-05:00`;
const endOfDay = (date: string) => `${date}T23:59:59-05:00`;

function useDebounce(value: string, delay: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

// Parse comma-separated query param into string array (empty string → empty array)
const parseList = (v: string): string[] => v ? v.split(',').filter(Boolean) : [];
const serializeList = (v: string[]): string => v.join(',') || '';

function MarketsContent() {
  const [searchInput, setSearchInput] = useState('');
  const [showSuggestions, setShowSuggestions] = useState(false);

  // All filter state persisted in URL query params
  const [qParam, setQParam] = useQueryState('q', { defaultValue: '' });
  const [tagsParam, setTagsParam] = useQueryState('tags', { defaultValue: '' });
  const [xtagsParam, setXtagsParam] = useQueryState('xtags', { defaultValue: '' });
  const [category, setCategory] = useQueryState('category', { defaultValue: '' });
  const [dmin, setDmin] = useQueryState('dmin', { defaultValue: '' });
  const [dmax, setDmax] = useQueryState('dmax', { defaultValue: '' });
  const [expiredParam, setExpiredParam] = useQueryState('expired', { defaultValue: '' });

  // Derived state from URL params
  const searchTerms = useMemo(() => parseList(qParam), [qParam]);
  const includedTags = useMemo(() => new Set(parseList(tagsParam)), [tagsParam]);
  const excludedTags = useMemo(() => new Set(parseList(xtagsParam)), [xtagsParam]);
  const dateRange: DateRange = useMemo(() => ({ min: dmin, max: dmax }), [dmin, dmax]);
  const showExpired = expiredParam === '1';

  // Setters that update URL params
  const setSearchTerms = useCallback((updater: string[] | ((prev: string[]) => string[])) => {
    setQParam((prev) => {
      const current = parseList(prev);
      const next = typeof updater === 'function' ? updater(current) : updater;
      return serializeList(next) || null;
    });
  }, [setQParam]);

  const setIncludedTags = useCallback((updater: Set<string> | ((prev: Set<string>) => Set<string>)) => {
    setTagsParam((prev) => {
      const current = new Set(parseList(prev));
      const next = typeof updater === 'function' ? updater(current) : updater;
      return serializeList([...next]) || null;
    });
  }, [setTagsParam]);

  const setExcludedTags = useCallback((updater: Set<string> | ((prev: Set<string>) => Set<string>)) => {
    setXtagsParam((prev) => {
      const current = new Set(parseList(prev));
      const next = typeof updater === 'function' ? updater(current) : updater;
      return serializeList([...next]) || null;
    });
  }, [setXtagsParam]);

  const setDateRange = useCallback((range: DateRange) => {
    setDmin(range.min || null);
    setDmax(range.max || null);
  }, [setDmin, setDmax]);

  const setShowExpired = useCallback((v: boolean) => {
    setExpiredParam(v ? '1' : null);
  }, [setExpiredParam]);
  const [pairMode, setPairMode] = useState(false);
  const [pairSelections, setPairSelections] = useState<Market[]>([]);

  const pairSelectedIds = useMemo(
    () => new Set(pairSelections.map((m) => m.id)),
    [pairSelections]
  );

  const handlePairSelect = useCallback((market: Market) => {
    setPairSelections((prev) => {
      if (prev.some((m) => m.id === market.id)) {
        return prev.filter((m) => m.id !== market.id);
      }
      if (prev.length >= 2) return prev;
      return [...prev, market];
    });
  }, []);

  const exitPairMode = useCallback(() => {
    setPairMode(false);
    setPairSelections([]);
  }, []);

  const wrapperRef = useRef<HTMLDivElement>(null);
  const debouncedInput = useDebounce(searchInput, 200);

  const resolvedCategory = category || undefined;

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

  // Server-side tag autocomplete
  const { data: suggestions } = useQuery({
    queryKey: ['marketTagSearch', debouncedInput],
    queryFn: () => searchAdminTags(debouncedInput, 8),
    enabled: debouncedInput.length >= 3,
    staleTime: 30_000,
  });

  const addSearchTerm = useCallback((term: string) => {
    const trimmed = term.trim();
    if (trimmed.length < 2) return;
    setSearchTerms((prev) =>
      prev.includes(trimmed) ? prev : [...prev, trimmed]
    );
    setSearchInput('');
    setShowSuggestions(false);
  }, []);

  const removeSearchTerm = useCallback((term: string) => {
    setSearchTerms((prev) => prev.filter((t) => t !== term));
  }, []);

  // Tag include toggle: neutral→included, included→neutral, excluded→included
  const toggleTagInclude = useCallback((term: string) => {
    setExcludedTags((prev) => {
      if (prev.has(term)) {
        const next = new Set(prev);
        next.delete(term);
        return next;
      }
      return prev;
    });
    setIncludedTags((prev) => {
      const next = new Set(prev);
      if (next.has(term)) next.delete(term);
      else next.add(term);
      return next;
    });
  }, []);

  // Tag exclude toggle: neutral→excluded, excluded→neutral, included→excluded
  const toggleTagExclude = useCallback((term: string) => {
    setIncludedTags((prev) => {
      if (prev.has(term)) {
        const next = new Set(prev);
        next.delete(term);
        return next;
      }
      return prev;
    });
    setExcludedTags((prev) => {
      const next = new Set(prev);
      if (next.has(term)) next.delete(term);
      else next.add(term);
      return next;
    });
  }, []);

  // Combine search terms + included tags into one query
  const combinedQuery = useMemo(() => {
    const parts = [...searchTerms, ...includedTags];
    return parts.join(' ');
  }, [searchTerms, includedTags]);

  // Excluded tags as query
  const excludeQuery = useMemo(() => {
    return [...excludedTags].join(' ');
  }, [excludedTags]);

  const { data: categoryCounts } = useMarketCategoryCounts();

  // Dynamic tags: recomputed from filtered markets when filters change
  const tagFilters = useMemo(() => ({
    q: combinedQuery || undefined,
    category: resolvedCategory,
    exclude_expired: !showExpired,
    end_date_min: dateRange.min ? startOfDay(dateRange.min) : undefined,
    end_date_max: dateRange.max ? endOfDay(dateRange.max) : undefined,
    exclude_q: excludeQuery || undefined,
    limit: 100,
  }), [combinedQuery, resolvedCategory, showExpired, dateRange, excludeQuery]);

  const { data: tags } = useQuery({
    queryKey: ['marketTags', tagFilters],
    queryFn: () => getMarketTags(tagFilters),
    staleTime: 30_000,
  });

  const countsRecord = useMemo(() => {
    if (!categoryCounts) return undefined;
    const rec: Record<string, number> = {};
    for (const c of categoryCounts) {
      rec[c.display_name] = c.count;
    }
    return rec;
  }, [categoryCounts]);

  const handleCategoryClick = useCallback((name: string | null) => {
    setCategory(name ?? null);
  }, [setCategory]);

  const hasFilters = searchTerms.length > 0 || includedTags.size > 0 || excludedTags.size > 0;

  const clearAll = useCallback(() => {
    setQParam(null);
    setTagsParam(null);
    setXtagsParam(null);
  }, [setQParam, setTagsParam, setXtagsParam]);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Top controls - fixed height */}
      <div className="shrink-0 space-y-3 px-4 pt-6 pb-4">
        <div>
          <h1 className="mb-1 text-2xl font-bold text-white">Markets</h1>
          <p className="text-sm text-gray-500">
            Browse and filter prediction markets across platforms.
          </p>
        </div>

        {/* Row 2: Search + Show expired toggle */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          {/* Search with autocomplete */}
          <div ref={wrapperRef} className="relative sm:max-w-sm sm:flex-1">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                addSearchTerm(searchInput);
              }}
            >
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
              <input
                type="text"
                value={searchInput}
                onChange={(e) => {
                  setSearchInput(e.target.value);
                  setShowSuggestions(e.target.value.length >= 3);
                }}
                onFocus={() => { if (searchInput.length >= 3) setShowSuggestions(true); }}
                placeholder="Type to search tags, Enter to add filter..."
                className="w-full rounded-lg border border-gray-800 bg-gray-900 py-2 pl-10 pr-9 text-sm text-gray-200 placeholder-gray-500 transition-colors focus:border-gray-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50"
              />
              {searchInput && (
                <button
                  type="button"
                  onClick={() => { setSearchInput(''); setShowSuggestions(false); }}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </form>

            {/* Autocomplete dropdown */}
            {showSuggestions && suggestions && suggestions.length > 0 && (
              <div className="absolute z-20 mt-1 w-full rounded-lg border border-gray-700 bg-gray-900 py-1 shadow-lg">
                {suggestions.map((s) => {
                  const term = String(s.term);
                  const alreadyAdded = searchTerms.includes(term) || includedTags.has(term);
                  return (
                    <button
                      key={term}
                      onClick={() => addSearchTerm(term)}
                      disabled={alreadyAdded}
                      className="flex w-full items-center justify-between px-3 py-1.5 text-left text-sm text-gray-300 hover:bg-gray-800 disabled:opacity-40 disabled:hover:bg-transparent"
                    >
                      <span>{term}</span>
                      <span className="text-xs text-gray-600">
                        {alreadyAdded ? 'added' : Number(s.total).toLocaleString()}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
            {showSuggestions && debouncedInput.length >= 3 && suggestions && suggestions.length === 0 && (
              <div className="absolute z-20 mt-1 w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-xs text-gray-500 shadow-lg">
                No tags matching &quot;{debouncedInput}&quot; — press Enter to search anyway
              </div>
            )}
          </div>

          {/* Right side: pair mode + show expired */}
          <div className="flex items-center gap-3">
          <button
            onClick={() => pairMode ? exitPairMode() : setPairMode(true)}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
              pairMode
                ? 'border-amber-600 bg-amber-900/20 text-amber-400'
                : 'border-gray-700 text-gray-400 hover:border-gray-600 hover:text-gray-200'
            }`}
          >
            <Link2 className="h-3.5 w-3.5" />
            {pairMode ? 'Exit pairing' : 'Pair markets'}
          </button>
          <label className="flex cursor-pointer items-center gap-1.5">
            <div
              role="switch"
              aria-checked={showExpired}
              onClick={() => setShowExpired(!showExpired)}
              className={`relative inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors ${
                showExpired ? 'bg-emerald-600' : 'bg-gray-700'
              }`}
            >
              <span
                className={`inline-block h-3 w-3 rounded-full bg-white transition-transform ${
                  showExpired ? 'translate-x-3.5' : 'translate-x-0.5'
                }`}
              />
            </div>
            <span className="text-xs text-gray-400">Show expired</span>
          </label>
          </div>
        </div>

        {/* Row 3: Active filter chips */}
        {hasFilters && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-gray-500">Filters:</span>
            {searchTerms.map((term) => (
              <span
                key={`s-${term}`}
                className="inline-flex items-center gap-1 rounded-full border border-emerald-700 bg-emerald-900/30 px-2.5 py-0.5 text-xs font-medium text-emerald-400"
              >
                {term}
                <button
                  onClick={() => removeSearchTerm(term)}
                  className="ml-0.5 rounded-full p-0.5 hover:bg-emerald-800/50"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
            {[...includedTags].map((term) => (
              <span
                key={`i-${term}`}
                className="inline-flex items-center gap-1 rounded-full border border-emerald-700 bg-emerald-900/30 px-2.5 py-0.5 text-xs font-medium text-emerald-400"
              >
                {term}
                <button
                  onClick={() => toggleTagInclude(term)}
                  className="ml-0.5 rounded-full p-0.5 hover:bg-emerald-800/50"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
            {[...excludedTags].map((term) => (
              <span
                key={`x-${term}`}
                className="inline-flex items-center gap-1 rounded-full border border-red-700 bg-red-900/30 px-2.5 py-0.5 text-xs font-medium text-red-400 line-through"
              >
                {term}
                <button
                  onClick={() => toggleTagExclude(term)}
                  className="ml-0.5 rounded-full p-0.5 hover:bg-red-800/50 no-underline"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
            <button
              onClick={clearAll}
              className="text-xs text-gray-500 hover:text-gray-300"
            >
              Clear all
            </button>
          </div>
        )}

        {/* Row 4: Unified TagBar (categories + tags) */}
        <TagBar
          categoryCounts={countsRecord}
          activeCategory={resolvedCategory ?? null}
          onCategoryClick={handleCategoryClick}
          tags={tags ?? []}
          includedTags={includedTags}
          excludedTags={excludedTags}
          onTagInclude={toggleTagInclude}
          onTagExclude={toggleTagExclude}
        />

        {/* Row 5: Expiry filter (no show expired toggle — moved to row 2) */}
        <ExpiryFilter value={dateRange} onChange={setDateRange} />
      </div>

      {/* Unified market list grouped by expiry */}
      <ErrorBoundary>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
          <UnifiedMarketList
            searchQuery={combinedQuery}
            excludeQuery={excludeQuery}
            category={resolvedCategory}
            endDateMin={dateRange.min ? startOfDay(dateRange.min) : undefined}
            endDateMax={dateRange.max ? endOfDay(dateRange.max) : undefined}
            excludeExpired={!showExpired}
            pairMode={pairMode}
            selectedIds={pairSelectedIds}
            onSelect={handlePairSelect}
          />
        </div>
      </ErrorBoundary>

      {pairMode && (
        <PairBar
          selections={pairSelections}
          onRemove={(id) => setPairSelections((prev) => prev.filter((m) => m.id !== id))}
          onClear={exitPairMode}
          onPaired={exitPairMode}
        />
      )}
    </div>
  );
}

export default function MarketsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-[calc(100vh-3.5rem)] items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-700 border-t-emerald-500" />
        </div>
      }
    >
      <MarketsContent />
    </Suspense>
  );
}
