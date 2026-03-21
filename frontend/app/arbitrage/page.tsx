'use client';

import { Suspense } from 'react';
import { useQueryState } from 'nuqs';
import { useArbitrage } from '@/lib/queries/useArbitrage';
import ArbTable from '@/components/arbitrage/ArbTable';
import CandidateList from '@/components/arbitrage/CandidateList';
import CategoryFilter from '@/components/markets/CategoryFilter';
import ErrorBoundary from '@/components/shared/ErrorBoundary';
import { cn } from '@/lib/utils/format';

const SORT_OPTIONS = [
  { value: 'spread', label: 'Spread' },
  { value: 'similarity', label: 'Similarity' },
  { value: 'volume', label: 'Volume' },
];

const TABS = [
  { value: 'pairs', label: 'Confirmed Pairs' },
  { value: 'candidates', label: 'Candidates' },
] as const;

function ArbitrageContent() {
  const [category] = useQueryState('category', { defaultValue: 'All' });
  const [sort, setSort] = useQueryState('sort', { defaultValue: 'spread' });
  const [tab, setTab] = useQueryState('tab', { defaultValue: 'pairs' });
  const [minSpread] = useQueryState('spread', { defaultValue: '0' });
  const minSpreadNum = parseFloat(minSpread) || 0;

  const filters = {
    category: category === 'All' ? undefined : category ?? undefined,
    sort: sort ?? 'spread',
    min_spread: minSpreadNum > 0 ? minSpreadNum : undefined,
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
          Cross-platform price discrepancies — confirmed pairs and AI-discovered candidates.
        </p>
      </div>

      {/* Tab switcher */}
      <div className="flex items-center gap-4 border-b border-gray-800">
        {TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => setTab(t.value)}
            className={cn(
              'relative pb-3 text-sm font-medium transition-colors',
              tab === t.value
                ? 'text-white'
                : 'text-gray-500 hover:text-gray-300'
            )}
          >
            {t.label}
            {tab === t.value && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 rounded-full bg-emerald-500" />
            )}
          </button>
        ))}
      </div>

      {tab === 'pairs' && (
        <>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <CategoryFilter />
            <div className="flex items-center gap-3">
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
        </>
      )}

      {tab === 'candidates' && (
        <ErrorBoundary>
          <CandidateList />
        </ErrorBoundary>
      )}
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
