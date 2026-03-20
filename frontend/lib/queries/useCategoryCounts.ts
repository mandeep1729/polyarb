'use client';

import { useQuery } from '@tanstack/react-query';
import { getGroupCategoryCounts, getMarketCategoryCounts, type CategoryCount } from '@/lib/api';

export function useGroupCategoryCounts() {
  return useQuery({
    queryKey: ['groupCategoryCounts'],
    queryFn: getGroupCategoryCounts,
    staleTime: 60_000,
  });
}

export function useMarketCategoryCounts(platform?: string) {
  return useQuery({
    queryKey: ['marketCategoryCounts', platform],
    queryFn: () => getMarketCategoryCounts(platform),
    staleTime: 60_000,
  });
}
