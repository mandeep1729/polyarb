'use client';

import Link from 'next/link';
import { useArbitrage } from '@/lib/queries/useArbitrage';
import ArbSpreadBadge from '@/components/arbitrage/ArbSpreadBadge';
import PlatformBadge from '@/components/markets/PlatformBadge';
import { GitCompareArrows, ArrowRight } from 'lucide-react';

export default function TopArbsPreview() {
  const { data, isLoading } = useArbitrage({ limit: 5, sort: 'spread' });
  const opportunities = data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <section>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <GitCompareArrows className="h-5 w-5 text-purple-500" />
          <h2 className="text-lg font-bold text-gray-100">
            Top Arbitrage Opportunities
          </h2>
        </div>
        <Link
          href="/arbitrage"
          className="inline-flex items-center gap-1 text-sm text-gray-400 transition-colors hover:text-emerald-400"
        >
          View All <ArrowRight className="h-4 w-4" />
        </Link>
      </div>

      <div className="space-y-2">
        {isLoading
          ? Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="h-14 animate-pulse rounded-lg bg-gray-900"
              />
            ))
          : opportunities.map((opp) => (
              <Link
                key={opp.id}
                href={`/arbitrage/${opp.id}`}
                className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-900 px-4 py-3 transition-all hover:border-gray-700 hover:bg-gray-800/50"
              >
                <div className="flex min-w-0 flex-1 items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-gray-200">
                      {opp.market_a.question}
                    </p>
                    <div className="mt-0.5 flex items-center gap-2">
                      <PlatformBadge platform={opp.market_a.platform_name} />
                      <span className="text-[10px] text-gray-600">vs</span>
                      <PlatformBadge platform={opp.market_b.platform_name} />
                    </div>
                  </div>
                </div>
                {opp.odds_delta != null && (
                  <ArbSpreadBadge spread={opp.odds_delta} className="ml-3" />
                )}
              </Link>
            ))}
      </div>
    </section>
  );
}
