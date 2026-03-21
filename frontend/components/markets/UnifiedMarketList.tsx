'use client';

import { useCallback, useRef, useState, useMemo } from 'react';
import type { Market } from '@/lib/types';
import { useMarkets } from '@/lib/queries/useMarkets';
import { useSearch } from '@/lib/queries/useSearch';
import type { MarketFilters } from '@/lib/api';
import BetCard from './BetCard';
import { BetCardSkeleton } from '@/components/shared/LoadingSkeleton';
import EmptyState from '@/components/shared/EmptyState';
import { Search } from 'lucide-react';

interface UnifiedMarketListProps {
  searchQuery: string;
  excludeQuery?: string;
  category?: string;
  endDateMin?: string;
  endDateMax?: string;
  excludeExpired?: boolean;
  pairMode?: boolean;
  selectedIds?: Set<number>;
  onSelect?: (market: Market) => void;
}

/** Group markets by the date portion of end_date, sort groups chronologically, sort within groups by volume desc. */
function groupByExpiry(markets: Market[]): { key: string; label: string; items: Market[] }[] {
  const map = new Map<string, Market[]>();
  for (const m of markets) {
    const key = m.end_date ? m.end_date.slice(0, 10) : 'no-expiry';
    const list = map.get(key);
    if (list) list.push(m);
    else map.set(key, [m]);
  }
  // Sort within each group by volume desc
  for (const list of map.values()) {
    list.sort((a, b) => (b.volume_24h ?? 0) - (a.volume_24h ?? 0));
  }
  // Sort groups chronologically, no-expiry last
  const keys = [...map.keys()].sort((a, b) => {
    if (a === 'no-expiry') return 1;
    if (b === 'no-expiry') return -1;
    return a.localeCompare(b);
  });
  return keys.map((key) => ({
    key,
    label: key === 'no-expiry'
      ? 'No expiry'
      : new Date(key + 'T00:00:00').toLocaleDateString('en-US', {
          weekday: 'short',
          month: 'short',
          day: 'numeric',
          year: 'numeric',
        }),
    items: map.get(key)!,
  }));
}

export default function UnifiedMarketList({
  searchQuery,
  excludeQuery,
  category,
  endDateMin,
  endDateMax,
  excludeExpired,
  pairMode,
  selectedIds,
  onSelect,
}: UnifiedMarketListProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const filters: MarketFilters = {
    category,
    sort: 'volume_24h',
    end_date_min: endDateMin,
    end_date_max: endDateMax,
    exclude_expired: excludeExpired,
    limit: 48,
  };

  const marketsQuery = useMarkets(filters);
  const searchResult = useSearch(searchQuery, {
    category,
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

  const groups = useMemo(() => groupByExpiry(markets), [markets]);

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

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <BetCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (markets.length === 0) {
    return (
      <EmptyState
        icon={<Search className="h-10 w-10" />}
        title="No markets"
        description="No markets match your filters."
      />
    );
  }

  return (
    <div className="space-y-6">
      {groups.map(({ key, label, items }) => (
        <section key={key}>
          <div className="sticky top-0 z-10 mb-3 flex items-center gap-2 bg-gray-950/80 py-2 backdrop-blur-sm">
            <h3 className="text-sm font-semibold text-gray-300">{label}</h3>
            <span className="text-xs text-gray-600">
              {items.length} {items.length === 1 ? 'market' : 'markets'}
            </span>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {items.map((market) => (
              <BetCard
                key={market.id}
                market={market}
                expanded={!pairMode && expandedId === market.id}
                onToggle={pairMode ? undefined : () =>
                  setExpandedId((prev) => (prev === market.id ? null : market.id))
                }
                selected={pairMode && selectedIds?.has(market.id)}
                onSelect={pairMode && onSelect ? () => onSelect(market) : undefined}
              />
            ))}
          </div>
        </section>
      ))}

      {!isSearching && marketsQuery.hasNextPage && (
        <div ref={sentinelRef} className="flex justify-center py-4">
          {marketsQuery.isFetchingNextPage && (
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-700 border-t-emerald-500" />
          )}
        </div>
      )}
    </div>
  );
}
