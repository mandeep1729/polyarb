'use client';

import { Suspense, useState } from 'react';
import { useQueryState } from 'nuqs';
import { useArbitrage } from '@/lib/queries/useArbitrage';
import ArbTable from '@/components/arbitrage/ArbTable';
import CategoryFilter from '@/components/markets/CategoryFilter';
import ErrorBoundary from '@/components/shared/ErrorBoundary';
import { cn } from '@/lib/utils/format';

const SORT_OPTIONS = [
  { value: 'spread', label: 'Spread' },
  { value: 'similarity', label: 'Similarity' },
  { value: 'volume', label: 'Volume' },
];

function ArbitrageContent() {
  const [category] = useQueryState('category', { defaultValue: 'All' });
  const [sort, setSort] = useQueryState('sort', { defaultValue: 'spread' });
  const [minSpread, setMinSpread] = useState(0);

  const filters = {
    category: category === 'All' ? undefined : category ?? undefined,
    sort: sort ?? 'spread',
    min_spread: minSpread > 0 ? minSpread : undefined,
    limit: 50,
  };

  const { data, isLoading } = useArbitrage(filters);
  const opportunities = data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="mb-1 text-2xl font-bold text-white">
          Arbitrage Opportunities
        </h1>
        <p className="text-sm text-gray-500">
          Cross-platform price discrepancies detected automatically.
        </p>
      </div>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <CategoryFilter />

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-500">Min Spread</label>
            <input
              type="range"
              min={0}
              max={20}
              step={0.5}
              value={minSpread}
              onChange={(e) => setMinSpread(parseFloat(e.target.value))}
              className="w-24 accent-emerald-500"
            />
            <span className="w-10 text-xs font-medium text-gray-400">
              {minSpread}%
            </span>
          </div>

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
        <ArbTable opportunities={opportunities} isLoading={isLoading} />
      </ErrorBoundary>
    </div>
  );
}

export default function ArbitragePage() {
  return (
    <Suspense
      fallback={
        <div className="space-y-4">
          <div className="h-8 w-64 animate-pulse rounded bg-gray-800" />
          <div className="h-64 animate-pulse rounded-xl bg-gray-900" />
        </div>
      }
    >
      <ArbitrageContent />
    </Suspense>
  );
}
