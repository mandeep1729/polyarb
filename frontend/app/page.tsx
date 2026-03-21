'use client';

import { Suspense, useState, useCallback, useRef, useMemo } from 'react';
import { useGroups } from '@/lib/queries/useGroups';
import { useGroupSearch } from '@/lib/queries/useGroupSearch';
import { useGroupCategoryCounts } from '@/lib/queries/useCategoryCounts';
import { useGroupTags } from '@/lib/queries/useGroupTags';
import { useMarkets } from '@/lib/queries/useMarkets';
import { useArbitrage } from '@/lib/queries/useArbitrage';
import StatsBar from '@/components/dashboard/StatsBar';
import GroupCard from '@/components/groups/GroupCard';
import { TagCloud } from '@/components/groups/TagCloud';
import { GroupCardGridSkeleton } from '@/components/groups/GroupCardSkeleton';
import CategoryFilter from '@/components/markets/CategoryFilter';
import ExpiryFilter, { type DateRange } from '@/components/markets/ExpiryFilter';
import SearchInput from '@/components/markets/SearchInput';
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
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
  const [dateRange, setDateRange] = useState<DateRange>({ min: '', max: '' });
  const [showExpired, setShowExpired] = useState(false);

  const toggleTag = useCallback((term: string) => {
    setSelectedTags((prev) => {
      const next = new Set(prev);
      if (next.has(term)) next.delete(term);
      else next.add(term);
      return next;
    });
  }, []);

  // Combine text search + selected tags into one query
  const combinedQuery = useMemo(() => {
    const parts = [...selectedTags];
    if (searchQuery.length >= 2) parts.push(searchQuery);
    return parts.join(' ');
  }, [searchQuery, selectedTags]);

  const { data: marketsData } = useMarkets({ limit: 1 });
  const { data: arbData } = useArbitrage({ limit: 100 });

  const isSearching = combinedQuery.length >= 2;

  const {
    data: groupsData,
    isLoading: groupsLoading,
    hasNextPage,
    fetchNextPage,
    isFetchingNextPage,
  } = useGroups({
    category: category ?? undefined,
    sort_by: sortBy,
    end_date_min: dateRange.min || undefined,
    end_date_max: dateRange.max || undefined,
    exclude_expired: !showExpired,
    limit: 24,
  });

  const {
    data: searchData,
    isLoading: searchLoading,
  } = useGroupSearch(combinedQuery, {
    category: category ?? undefined,
    sort_by: sortBy,
    end_date_min: dateRange.min || undefined,
    end_date_max: dateRange.max || undefined,
    exclude_expired: !showExpired,
    limit: 24,
  });

  const { data: categoryCounts } = useGroupCategoryCounts();
  const { data: tags } = useGroupTags(50);

  // Build counts record for CategoryFilter: display_name → count
  const countsRecord = useMemo(() => {
    if (!categoryCounts) return undefined;
    const rec: Record<string, number> = {};
    for (const c of categoryCounts) {
      rec[c.display_name] = c.count;
    }
    return rec;
  }, [categoryCounts]);

  const totalMarkets = marketsData?.pages[0]?.total ?? 0;
  const arbOpps = arbData?.pages.flatMap((p) => p.items) ?? [];
  const avgSpread =
    arbOpps.length > 0
      ? arbOpps.reduce((sum, o) => sum + (o.odds_delta ?? 0), 0) / arbOpps.length
      : 0;

  const groups = isSearching
    ? searchData?.items ?? []
    : groupsData?.pages.flatMap((p) => p.items) ?? [];
  const totalGroups = isSearching
    ? searchData?.total ?? 0
    : groupsData?.pages[0]?.total ?? 0;
  const isLoading = isSearching ? searchLoading : groupsLoading;

  // Infinite scroll (only for non-search mode)
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

      {/* Search + Filters */}
      <div className="space-y-3">
        <SearchInput
          value={searchQuery}
          onChange={setSearchQuery}
          placeholder="Search groups..."
          className="max-w-sm"
        />
        <div className="flex flex-wrap items-center gap-3">
          <CategoryFilter counts={countsRecord} />
        </div>
        {tags && tags.length > 0 && (
          <TagCloud
            tags={tags}
            activeTags={selectedTags}
            onTagClick={toggleTag}
          />
        )}
        <ExpiryFilter value={dateRange} onChange={setDateRange} showExpired={showExpired} onShowExpiredChange={setShowExpired} />
        <div className="flex flex-wrap items-center gap-3">
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
      </div>

      {/* Group Cards */}
      <ErrorBoundary>
        {isLoading ? (
          <GroupCardGridSkeleton count={6} />
        ) : groups.length === 0 ? (
          <EmptyState
            icon={<Layers className="h-12 w-12" />}
            title={isSearching ? 'No groups found' : 'Markets are being grouped'}
            description={
              isSearching
                ? 'Try a different search term or clear the filters.'
                : 'Check back in a few minutes. Groups are created from market data automatically.'
            }
          />
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {groups.map((group) => (
                <GroupCard key={group.id} group={group} />
              ))}
            </div>

            {/* Infinite scroll trigger (non-search only) */}
            {!isSearching && hasNextPage && (
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
