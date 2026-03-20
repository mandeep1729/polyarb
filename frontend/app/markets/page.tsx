'use client';

import { Suspense, useState, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import { useQueryState } from 'nuqs';
import SearchInput from '@/components/markets/SearchInput';
import CategoryFilter from '@/components/markets/CategoryFilter';
import SortSelect from '@/components/markets/SortSelect';
import PlatformColumn from '@/components/markets/PlatformColumn';
import ErrorBoundary from '@/components/shared/ErrorBoundary';
import { useMarketCategoryCounts } from '@/lib/queries/useCategoryCounts';

const PLATFORMS = [
  { slug: 'polymarket', label: 'Polymarket' },
  { slug: 'kalshi', label: 'Kalshi' },
];

function MarketsContent() {
  const searchParams = useSearchParams();
  const initialQ = searchParams.get('q') ?? '';
  const [searchQuery, setSearchQuery] = useState(initialQ);
  const [category] = useQueryState('category', { defaultValue: 'All' });
  const [sort] = useQueryState('sort', { defaultValue: 'volume_24h' });

  const resolvedCategory = category === 'All' ? undefined : category ?? undefined;
  const resolvedSort = sort ?? 'volume_24h';

  const { data: categoryCounts } = useMarketCategoryCounts();

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
      <div className="shrink-0 space-y-4 px-4 pt-6 pb-4">
        <div>
          <h1 className="mb-1 text-2xl font-bold text-white">Markets</h1>
          <p className="text-sm text-gray-500">
            Browse and filter prediction markets across platforms.
          </p>
        </div>

        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <SearchInput
            value={searchQuery}
            onChange={setSearchQuery}
            className="sm:max-w-sm"
          />
          <SortSelect />
        </div>

        <CategoryFilter counts={countsRecord} />
      </div>

      {/* Split columns - fill remaining height */}
      <ErrorBoundary>
        <div className="flex min-h-0 flex-1 gap-4 px-4 pb-4">
          {PLATFORMS.map((p) => (
            <PlatformColumn
              key={p.slug}
              slug={p.slug}
              label={p.label}
              searchQuery={searchQuery}
              category={resolvedCategory}
              sort={resolvedSort}
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
