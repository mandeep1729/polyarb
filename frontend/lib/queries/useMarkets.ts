'use client';

import { useQuery, useInfiniteQuery } from '@tanstack/react-query';
import { getMarkets, getMarket, getPriceHistory, getTrending, type MarketFilters } from '@/lib/api';

export function useMarkets(filters: MarketFilters = {}) {
  return useInfiniteQuery({
    queryKey: ['markets', filters],
    queryFn: ({ pageParam }) =>
      getMarkets({ ...filters, cursor: pageParam as string | undefined }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    refetchInterval: 15_000,
  });
}

export function useMarket(idOrSlug: string | number) {
  return useQuery({
    queryKey: ['market', idOrSlug],
    queryFn: () => getMarket(idOrSlug),
    enabled: !!idOrSlug,
  });
}

export function usePriceHistory(marketId: number, interval: string = '7d') {
  return useQuery({
    queryKey: ['priceHistory', marketId, interval],
    queryFn: () => getPriceHistory(marketId, interval),
    enabled: !!marketId,
  });
}

export function useTrending(limit: number = 10, platform?: string) {
  return useQuery({
    queryKey: ['trending', limit, platform],
    queryFn: () => getTrending(limit, platform),
    refetchInterval: 30_000,
  });
}
