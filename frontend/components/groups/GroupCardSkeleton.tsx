import Skeleton from '@/components/shared/LoadingSkeleton';

export default function GroupCardSkeleton() {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
      <div className="mb-2 flex items-center gap-2">
        <Skeleton className="h-5 w-16 rounded-full" />
        <Skeleton className="h-4 w-20" />
      </div>
      <Skeleton className="mb-1 h-5 w-full" />
      <Skeleton className="mb-3 h-5 w-3/4" />
      <div className="flex gap-4">
        <div>
          <Skeleton className="mb-1 h-3 w-16" />
          <Skeleton className="h-6 w-14" />
        </div>
        <div>
          <Skeleton className="mb-1 h-3 w-12" />
          <Skeleton className="h-6 w-16 rounded-full" />
        </div>
      </div>
      <div className="mt-3 flex gap-3">
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-3 w-16" />
      </div>
    </div>
  );
}

export function GroupCardGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <GroupCardSkeleton key={i} />
      ))}
    </div>
  );
}
