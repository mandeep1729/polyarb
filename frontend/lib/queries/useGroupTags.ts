'use client';

import { useQuery } from '@tanstack/react-query';
import { getGroupTags } from '@/lib/api';

export function useGroupTags(limit = 50) {
  return useQuery({
    queryKey: ['groupTags', limit],
    queryFn: () => getGroupTags(limit),
    staleTime: 60_000,
  });
}
