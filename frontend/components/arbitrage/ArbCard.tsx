'use client';

import Link from 'next/link';
import type { ArbitrageOpportunity } from '@/lib/types';
import PlatformBadge from '@/components/markets/PlatformBadge';
import OddsDisplay from '@/components/markets/OddsDisplay';
import ArbSpreadBadge from './ArbSpreadBadge';
import { cn } from '@/lib/utils/format';
import { formatDistanceToNow } from 'date-fns';

interface ArbCardProps {
  opportunity: ArbitrageOpportunity;
}

export default function ArbCard({ opportunity }: ArbCardProps) {
  const { market_a, market_b, odds_delta, similarity_score, match_method, last_checked_at } =
    opportunity;

  return (
    <Link
      href={`/arbitrage/${opportunity.id}`}
      className="block rounded-xl border border-gray-800 bg-gray-900 p-4 transition-all hover:scale-[1.01] hover:border-gray-700"
    >
      <div className="mb-3 flex items-center justify-between">
        {odds_delta != null && <ArbSpreadBadge spread={odds_delta} />}
        <span className="rounded-md bg-gray-800 px-2 py-0.5 text-[10px] font-medium text-gray-400">
          {match_method}
        </span>
      </div>

      <h3 className="mb-3 line-clamp-2 text-sm font-semibold text-gray-100">
        {market_a.question}
      </h3>

      <div className="mb-3 space-y-2">
        {/* Platform A */}
        <div className="flex items-center justify-between rounded-lg bg-gray-800/50 px-3 py-2">
          <PlatformBadge platform={market_a.platform_name} />
          <OddsDisplay probability={Object.values(market_a.outcome_prices)[0] ?? 0} size="sm" />
        </div>
        {/* Platform B */}
        <div className="flex items-center justify-between rounded-lg bg-gray-800/50 px-3 py-2">
          <PlatformBadge platform={market_b.platform_name} />
          <OddsDisplay probability={Object.values(market_b.outcome_prices)[0] ?? 0} size="sm" />
        </div>
      </div>

      <div className="flex items-center justify-between text-[11px] text-gray-500">
        <span>Similarity: {(similarity_score * 100).toFixed(0)}%</span>
        <span>
          {formatDistanceToNow(new Date(last_checked_at), {
            addSuffix: true,
          })}
        </span>
      </div>
    </Link>
  );
}
