'use client';

import { useQuery } from '@tanstack/react-query';
import { useDebounce } from './useSearch';
import { searchGroups, type GroupSearchFilters } from '@/lib/api';

export function useGroupSearch(query: string, filters: GroupSearchFilters = {}) {
  const debouncedQuery = useDebounce(query, 300);

  return useQuery({
    queryKey: ['groupSearch', debouncedQuery, filters],
    queryFn: () => searchGroups(debouncedQuery, filters),
    enabled: debouncedQuery.length >= 2,
    staleTime: 30_000,
  });
}
