'use client';

import type { Market } from '@/lib/types';
import BetCard from './BetCard';
import EmptyState from '@/components/shared/EmptyState';
import { Search } from 'lucide-react';

interface BetCardGridProps {
  markets: Market[];
}

export default function BetCardGrid({ markets }: BetCardGridProps) {
  if (markets.length === 0) {
    return (
      <EmptyState
        icon={<Search className="h-12 w-12" />}
        title="No markets found"
        description="Try adjusting your filters or search query."
      />
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {markets.map((market) => (
        <BetCard key={market.id} market={market} />
      ))}
    </div>
  );
}
