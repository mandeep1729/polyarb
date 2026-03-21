'use client';

import { Suspense, useState, useMemo, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';
import { useQueryState } from 'nuqs';
import SearchInput from '@/components/markets/SearchInput';
import CategoryFilter from '@/components/markets/CategoryFilter';
import ExpiryFilter, { type DateRange } from '@/components/markets/ExpiryFilter';
import SortSelect from '@/components/markets/SortSelect';
import PlatformColumn from '@/components/markets/PlatformColumn';
import TagCloud from '@/components/groups/TagCloud';
import ErrorBoundary from '@/components/shared/ErrorBoundary';
import { useMarketCategoryCounts } from '@/lib/queries/useCategoryCounts';
import { useGroupTags } from '@/lib/queries/useGroupTags';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils/format';

const PLATFORMS = [
  { slug: 'polymarket', label: 'Polymarket' },
  { slug: 'kalshi', label: 'Kalshi' },
];

function MarketsContent() {
  const searchParams = useSearchParams();
  const initialQ = searchParams.get('q') ?? '';
  const [searchInput, setSearchInput] = useState('');
  const [searchTerms, setSearchTerms] = useState<string[]>(
    initialQ ? [initialQ] : []
  );
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
  const [category] = useQueryState('category', { defaultValue: 'All' });
  const [sort] = useQueryState('sort', { defaultValue: 'volume_24h' });
  const [dateRange, setDateRange] = useState<DateRange>({ min: '', max: '' });
  const [showExpired, setShowExpired] = useState(false);

  const resolvedCategory = category === 'All' ? undefined : category ?? undefined;
  const resolvedSort = sort ?? 'volume_24h';

  const addSearchTerm = useCallback((term: string) => {
    const trimmed = term.trim();
    if (trimmed.length < 2) return;
    setSearchTerms((prev) =>
      prev.includes(trimmed) ? prev : [...prev, trimmed]
    );
    setSearchInput('');
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
  const { data: tags } = useGroupTags(50);

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
          <SearchInput
            value={searchInput}
            onChange={setSearchInput}
            onSubmit={addSearchTerm}
            placeholder="Type and press Enter to add filter..."
            className="sm:max-w-sm"
          />
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
