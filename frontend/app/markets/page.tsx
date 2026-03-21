'use client';

import { Suspense, useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { useQueryState } from 'nuqs';
import { useQuery } from '@tanstack/react-query';
import { searchAdminTags, getMarketTags } from '@/lib/api';
import CategoryFilter from '@/components/markets/CategoryFilter';
import ExpiryFilter, { type DateRange } from '@/components/markets/ExpiryFilter';
import SortSelect from '@/components/markets/SortSelect';
import PlatformColumn from '@/components/markets/PlatformColumn';
import TagCloud from '@/components/groups/TagCloud';
import ErrorBoundary from '@/components/shared/ErrorBoundary';
import { useMarketCategoryCounts } from '@/lib/queries/useCategoryCounts';
import { X, Search } from 'lucide-react';

const PLATFORMS = [
  { slug: 'polymarket', label: 'Polymarket' },
  { slug: 'kalshi', label: 'Kalshi' },
];

function useDebounce(value: string, delay: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

function MarketsContent() {
  const searchParams = useSearchParams();
  const initialQ = searchParams.get('q') ?? '';
  const [searchInput, setSearchInput] = useState('');
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [searchTerms, setSearchTerms] = useState<string[]>(
    initialQ ? [initialQ] : []
  );
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
  const [category] = useQueryState('category', { defaultValue: 'All' });
  const [sort] = useQueryState('sort', { defaultValue: 'volume_24h' });
  const [dateRange, setDateRange] = useState<DateRange>({ min: '', max: '' });
  const [showExpired, setShowExpired] = useState(false);

  const wrapperRef = useRef<HTMLDivElement>(null);
  const debouncedInput = useDebounce(searchInput, 200);

  const resolvedCategory = category === 'All' ? undefined : category ?? undefined;
  const resolvedSort = sort ?? 'volume_24h';

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

  const toggleTag = useCallback((term: string) => {
    setSelectedTags((prev) => {
      const next = new Set(prev);
      if (next.has(term)) next.delete(term);
      else next.add(term);
      return next;
    });
  }, []);

  // Combine search terms + selected tags into one query
  const combinedQuery = useMemo(() => {
    const parts = [...searchTerms, ...selectedTags];
    return parts.join(' ');
  }, [searchTerms, selectedTags]);

  const { data: categoryCounts } = useMarketCategoryCounts();

  // Dynamic tags: recomputed from filtered markets when filters change
  const tagFilters = useMemo(() => ({
    q: combinedQuery || undefined,
    category: resolvedCategory,
    exclude_expired: !showExpired,
    end_date_min: dateRange.min || undefined,
    end_date_max: dateRange.max || undefined,
    limit: 100,
  }), [combinedQuery, resolvedCategory, showExpired, dateRange]);

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
                  const alreadyAdded = searchTerms.includes(term) || selectedTags.has(term);
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
          <SortSelect />
        </div>

        {/* Active search selections */}
        {searchTerms.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-gray-500">Filters:</span>
            {searchTerms.map((term) => (
              <span
                key={term}
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
            <button
              onClick={() => setSearchTerms([])}
              className="text-xs text-gray-500 hover:text-gray-300"
            >
              Clear all
            </button>
          </div>
        )}

        <CategoryFilter counts={countsRecord} />

        {tags && tags.length > 0 && (
          <TagCloud
            tags={tags}
            activeTags={selectedTags}
            onTagClick={toggleTag}
          />
        )}

        <ExpiryFilter value={dateRange} onChange={setDateRange} showExpired={showExpired} onShowExpiredChange={setShowExpired} />
      </div>

      {/* Split columns - fill remaining height */}
      <ErrorBoundary>
        <div className="flex min-h-0 flex-1 gap-4 px-4 pb-4">
          {PLATFORMS.map((p) => (
            <PlatformColumn
              key={p.slug}
              slug={p.slug}
              label={p.label}
              searchQuery={combinedQuery}
              category={resolvedCategory}
              sort={resolvedSort}
              endDateMin={dateRange.min || undefined}
              endDateMax={dateRange.max || undefined}
              excludeExpired={!showExpired}
            />
          ))}
        </div>
      </ErrorBoundary>
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
