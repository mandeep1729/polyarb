'use client';

import { useTrending } from '@/lib/queries/useMarkets';
import BetCard from '@/components/markets/BetCard';
import { BetCardSkeleton } from '@/components/shared/LoadingSkeleton';
import { TrendingUp } from 'lucide-react';

interface TrendingSectionProps {
  platform?: string;
}

export default function TrendingSection({ platform }: TrendingSectionProps) {
  const { data: trending, isLoading } = useTrending(8, platform);

  return (
    <section>
      <div className="mb-4 flex items-center gap-2">
        <TrendingUp className="h-5 w-5 text-emerald-500" />
        <h2 className="text-lg font-bold text-gray-100">Trending Markets</h2>
      </div>

      <div className="flex gap-4 overflow-x-auto pb-3 scrollbar-none">
        {isLoading
          ? Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="w-72 shrink-0">
                <BetCardSkeleton />
              </div>
            ))
          : trending?.map((tm) => (
              <div key={tm.market.id} className="w-72 shrink-0">
                <BetCard market={tm.market} />
              </div>
            ))}
      </div>
    </section>
  );
}
