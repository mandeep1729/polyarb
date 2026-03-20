'use client';

import { useInfiniteQuery } from '@tanstack/react-query';
import { getArbitrage, type ArbitrageFilters } from '@/lib/api';

export function useArbitrage(filters: ArbitrageFilters = {}) {
  return useInfiniteQuery({
    queryKey: ['arbitrage', filters],
    queryFn: ({ pageParam }) =>
      getArbitrage({ ...filters, cursor: pageParam as string | undefined }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    refetchInterval: 15_000,
  });
}
