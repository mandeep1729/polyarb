'use client';

import { useCallback, useRef, useState } from 'react';
import type { Market } from '@/lib/types';
import { useMarkets } from '@/lib/queries/useMarkets';
import { useSearch } from '@/lib/queries/useSearch';
import type { MarketFilters } from '@/lib/api';
import BetCard from './BetCard';
import { BetCardSkeleton } from '@/components/shared/LoadingSkeleton';
import EmptyState from '@/components/shared/EmptyState';
import { cn } from '@/lib/utils/format';
import { Search } from 'lucide-react';

const platformStyles: Record<string, { border: string; accent: string; header: string }> = {
  polymarket: {
    border: 'border-purple-800/40',
    accent: 'text-purple-400',
    header: 'bg-purple-900/20 border-b border-purple-800/30',
  },
  kalshi: {
    border: 'border-blue-800/40',
    accent: 'text-blue-400',
    header: 'bg-blue-900/20 border-b border-blue-800/30',
  },
};

const defaultStyle = {
  border: 'border-gray-800',
  accent: 'text-gray-400',
  header: 'bg-gray-900/50 border-b border-gray-800',
};

interface PlatformColumnProps {
  slug: string;
  label: string;
  searchQuery: string;
  excludeQuery?: string;
  category?: string;
  sort: string;
  endDateMin?: string;
  endDateMax?: string;
  excludeExpired?: boolean;
}

export default function PlatformColumn({
  slug,
  label,
  searchQuery,
  excludeQuery,
  category,
  sort,
  endDateMin,
  endDateMax,
  excludeExpired,
}: PlatformColumnProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const style = platformStyles[slug] ?? defaultStyle;

  const filters: MarketFilters = {
    platform: slug,
    category,
    sort,
    end_date_min: endDateMin,
    end_date_max: endDateMax,
    exclude_expired: excludeExpired,
    limit: 24,
  };

  const marketsQuery = useMarkets(filters);
  const searchResult = useSearch(searchQuery, {
    category,
    platform: slug,
    exclude_expired: excludeExpired,
    end_date_min: endDateMin,
    end_date_max: endDateMax,
    exclude_q: excludeQuery || undefined,
  });

  const isSearching = searchQuery.length >= 2 || (excludeQuery != null && excludeQuery.length > 0);
  const isLoading = isSearching ? searchResult.isLoading : marketsQuery.isLoading;
  const markets: Market[] = isSearching
    ? searchResult.data ?? []
    : marketsQuery.data?.pages.flatMap((p) => p.items) ?? [];
  const totalCount = marketsQuery.data?.pages[0]?.total ?? 0;

  const observerRef = useRef<IntersectionObserver | null>(null);
  const sentinelRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (isSearching) return;
      if (observerRef.current) observerRef.current.disconnect();
      if (!node) return;

      observerRef.current = new IntersectionObserver((entries) => {
        if (
          entries[0].isIntersecting &&
          marketsQuery.hasNextPage &&
          !marketsQuery.isFetchingNextPage
        ) {
          marketsQuery.fetchNextPage();
        }
      });
      observerRef.current.observe(node);
    },
    [isSearching, marketsQuery.hasNextPage, marketsQuery.isFetchingNextPage, marketsQuery.fetchNextPage]
  );

  return (
    <div
      className={cn(
        'flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border',
        style.border
      )}
    >
      {/* Column header */}
      <div className={cn('flex shrink-0 items-center justify-between px-4 py-3', style.header)}>
        <div className="flex items-center gap-2">
          <h2 className={cn('text-sm font-bold', style.accent)}>{label}</h2>
          {!isLoading && (
            <span className="rounded-full bg-gray-800 px-2 py-0.5 text-[11px] text-gray-400">
              {isSearching ? markets.length : totalCount}
            </span>
          )}
        </div>
      </div>

      {/* Scrollable card list */}
      <div className="flex-1 overflow-y-auto overscroll-contain p-3">
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <BetCardSkeleton key={i} />
            ))}
          </div>
        ) : markets.length === 0 ? (
          <EmptyState
            icon={<Search className="h-10 w-10" />}
            title="No markets"
            description="No markets match your filters."
          />
        ) : (
          <div className="space-y-3">
            {markets.map((market) => (
              <BetCard
                key={market.id}
                market={market}
                expanded={expandedId === market.id}
                onToggle={() =>
                  setExpandedId((prev) =>
                    prev === market.id ? null : market.id
                  )
                }
              />
            ))}

            {!isSearching && marketsQuery.hasNextPage && (
              <div ref={sentinelRef} className="flex justify-center py-4">
                {marketsQuery.isFetchingNextPage && (
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-700 border-t-emerald-500" />
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
