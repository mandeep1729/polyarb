'use client';

import { useQuery, useInfiniteQuery } from '@tanstack/react-query';
import {
  getGroups,
  getGroupDetail,
  getGroupHistory,
  type GroupFilters,
} from '@/lib/api';

export function useGroups(filters: GroupFilters = {}) {
  return useInfiniteQuery({
    queryKey: ['groups', filters],
    queryFn: ({ pageParam }) =>
      getGroups({ ...filters, cursor: pageParam as string | undefined }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    refetchInterval: 30_000,
  });
}

export function useGroupDetail(groupId: number) {
  return useQuery({
    queryKey: ['groupDetail', groupId],
    queryFn: () => getGroupDetail(groupId),
    enabled: !!groupId,
  });
}

export function useGroupHistory(groupId: number, days: number = 30) {
  return useQuery({
    queryKey: ['groupHistory', groupId, days],
    queryFn: () => getGroupHistory(groupId, days),
    enabled: !!groupId,
  });
}
