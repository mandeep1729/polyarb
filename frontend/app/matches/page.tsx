'use client';

import { Suspense } from 'react';
import { useQueryState } from 'nuqs';
import { useArbitrage } from '@/lib/queries/useArbitrage';
import MatchCard from '@/components/matches/MatchCard';
import CategoryFilter from '@/components/markets/CategoryFilter';
import EmptyState from '@/components/shared/EmptyState';
import ErrorBoundary from '@/components/shared/ErrorBoundary';
import { cn } from '@/lib/utils/format';
import { Link2 } from 'lucide-react';

const SORT_OPTIONS = [
  { value: 'similarity', label: 'Similarity' },
  { value: 'spread', label: 'Spread' },
  { value: 'volume', label: 'Volume' },
];

function MatchesContent() {
  const [category] = useQueryState('category', { defaultValue: 'All' });
  const [sort, setSort] = useQueryState('sort', { defaultValue: 'similarity' });
  const [onesidedParam, setOnesidedParam] = useQueryState('onesided', { defaultValue: '0' });
  const showOnesided = onesidedParam === '1';

  const filters = {
    category: category === 'All' ? undefined : category ?? undefined,
    sort: sort ?? 'similarity',
    hide_onesided: !showOnesided,
    limit: 50,
  };

  const { data, isLoading, hasNextPage, fetchNextPage, isFetchingNextPage } =
    useArbitrage(filters);
  const pairs = data?.pages.flatMap((p) => p.items) ?? [];
  const total = data?.pages[0]?.total ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="mb-1 text-2xl font-bold text-white">Market Matches</h1>
        <p className="text-sm text-gray-500">
          Cross-platform market pairs detected via similarity matching.
          {!isLoading && (
            <span className="ml-1 text-gray-400">{total} pairs</span>
          )}
        </p>
      </div>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <CategoryFilter />

        <div className="flex items-center gap-4">
          <label className="flex cursor-pointer items-center gap-1.5">
            <div
              role="switch"
              aria-checked={showOnesided}
              onClick={() => setOnesidedParam(showOnesided ? '0' : '1')}
              className={`relative inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors ${
                showOnesided ? 'bg-emerald-600' : 'bg-gray-700'
              }`}
            >
              <span
                className={`inline-block h-3 w-3 rounded-full bg-white transition-transform ${
                  showOnesided ? 'translate-x-3.5' : 'translate-x-0.5'
                }`}
              />
            </div>
            <span className="text-xs text-gray-400">Show one-sided</span>
          </label>

          <div className="flex overflow-hidden rounded-lg border border-gray-800">
            {SORT_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setSort(opt.value)}
                className={cn(
                  'px-3 py-1.5 text-xs font-medium transition-colors',
                  sort === opt.value
                    ? 'bg-emerald-600 text-white'
                    : 'bg-gray-900 text-gray-400 hover:text-gray-200',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50'
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <ErrorBoundary>
        {!isLoading && pairs.length === 0 ? (
          <EmptyState
            icon={<Link2 className="h-12 w-12" />}
            title="No market matches"
            description="No cross-platform market pairs have been detected yet."
          />
        ) : (
          <div className="space-y-3">
            {isLoading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <div
                    key={i}
                    className="h-28 animate-pulse rounded-xl bg-gray-900"
                  />
                ))
              : pairs.map((pair) => (
                  <MatchCard key={pair.id} pair={pair} />
                ))}

            {hasNextPage && (
              <div className="flex justify-center pt-2">
                <button
                  onClick={() => fetchNextPage()}
                  disabled={isFetchingNextPage}
                  className="rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-300 transition-colors hover:border-gray-600 hover:text-white disabled:opacity-50"
                >
                  {isFetchingNextPage ? 'Loading...' : 'Load more'}
                </button>
              </div>
            )}
          </div>
        )}
      </ErrorBoundary>
    </div>
  );
}

export default function MatchesPage() {
  return (
    <Suspense
      fallback={
        <div className="space-y-4">
          <div className="h-8 w-64 animate-pulse rounded bg-gray-800" />
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="h-28 animate-pulse rounded-xl bg-gray-900"
              />
            ))}
          </div>
        </div>
      }
    >
      <MatchesContent />
    </Suspense>
  );
}
