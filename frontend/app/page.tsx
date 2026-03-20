'use client';

import { Suspense, useState, useCallback, useRef } from 'react';
import { useGroups } from '@/lib/queries/useGroups';
import { useMarkets } from '@/lib/queries/useMarkets';
import { useArbitrage } from '@/lib/queries/useArbitrage';
import StatsBar from '@/components/dashboard/StatsBar';
import GroupCard from '@/components/groups/GroupCard';
import { GroupCardGridSkeleton } from '@/components/groups/GroupCardSkeleton';
import CategoryFilter from '@/components/markets/CategoryFilter';
import EmptyState from '@/components/shared/EmptyState';
import ErrorBoundary from '@/components/shared/ErrorBoundary';
import { Layers } from 'lucide-react';
import { useQueryState } from 'nuqs';

export default function Home() {
  return (
    <Suspense fallback={<GroupCardGridSkeleton count={6} />}>
      <HomeContent />
    </Suspense>
  );
}

function HomeContent() {
  const [category] = useQueryState('category');
  const [sortBy, setSortBy] = useState('liquidity');

  const { data: marketsData } = useMarkets({ limit: 1 });
  const { data: arbData } = useArbitrage({ limit: 100 });

  const {
    data: groupsData,
    isLoading,
    hasNextPage,
    fetchNextPage,
    isFetchingNextPage,
  } = useGroups({
    category: category ?? undefined,
    sort_by: sortBy,
    limit: 24,
  });

  const totalMarkets = marketsData?.pages[0]?.total ?? 0;
  const arbOpps = arbData?.pages.flatMap((p) => p.items) ?? [];
  const avgSpread =
    arbOpps.length > 0
      ? arbOpps.reduce((sum, o) => sum + (o.odds_delta ?? 0), 0) / arbOpps.length
      : 0;

  const groups = groupsData?.pages.flatMap((p) => p.items) ?? [];
  const totalGroups = groupsData?.pages[0]?.total ?? 0;

  // Infinite scroll
  const observerRef = useRef<IntersectionObserver | null>(null);
  const loadMoreRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (observerRef.current) observerRef.current.disconnect();
      if (!node) return;
      observerRef.current = new IntersectionObserver((entries) => {
        if (entries[0]?.isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage();
        }
      });
      observerRef.current.observe(node);
    },
    [hasNextPage, isFetchingNextPage, fetchNextPage]
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="mb-1 text-2xl font-bold text-white">Groups</h1>
        <p className="text-sm text-gray-500">
          Markets clustered by topic. Consensus pricing and cross-platform arbitrage at a glance.
        </p>
      </div>

      <ErrorBoundary>
        <StatsBar
          totalMarkets={totalMarkets}
          activePlatforms={2}
          arbOpportunities={arbOpps.length}
          avgSpread={avgSpread}
        />
      </ErrorBoundary>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <CategoryFilter />
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50"
        >
          <option value="liquidity">Liquidity</option>
          <option value="disagreement">Highest Spread</option>
          <option value="volume">Volume</option>
          <option value="consensus">Consensus</option>
          <option value="created_at">Newest</option>
        </select>
        <span className="text-xs text-gray-500">
          {totalGroups.toLocaleString()} groups
        </span>
      </div>

      {/* Group Cards */}
      <ErrorBoundary>
        {isLoading ? (
          <GroupCardGridSkeleton count={6} />
        ) : groups.length === 0 ? (
          <EmptyState
            icon={<Layers className="h-12 w-12" />}
            title="Markets are being grouped"
            description="Check back in a few minutes. Groups are created from market data automatically."
          />
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {groups.map((group) => (
                <GroupCard key={group.id} group={group} />
              ))}
            </div>

            {/* Infinite scroll trigger */}
            {hasNextPage && (
              <div ref={loadMoreRef} className="flex justify-center py-4">
                {isFetchingNextPage && <GroupCardGridSkeleton count={3} />}
              </div>
            )}
          </>
        )}
      </ErrorBoundary>
    </div>
  );
}
