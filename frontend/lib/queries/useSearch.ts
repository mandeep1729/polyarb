'use client';

import { useQuery } from '@tanstack/react-query';
import { useState, useEffect } from 'react';
import { searchMarkets, type SearchFilters } from '@/lib/api';

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function useSearch(query: string, filters: SearchFilters = {}) {
  const debouncedQuery = useDebounce(query, 300);

  return useQuery({
    queryKey: ['search', debouncedQuery, filters],
    queryFn: () => searchMarkets(debouncedQuery, filters),
    enabled: debouncedQuery.length >= 2,
    staleTime: 30_000,
  });
}

export { useDebounce };
