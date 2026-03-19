'use client';

import type { ArbitrageOpportunity } from '@/lib/types';
import ArbSpreadBadge from './ArbSpreadBadge';
import ArbCard from './ArbCard';
import PlatformBadge from '@/components/markets/PlatformBadge';
import OddsDisplay from '@/components/markets/OddsDisplay';
import EmptyState from '@/components/shared/EmptyState';
import { ArbTableRowSkeleton } from '@/components/shared/LoadingSkeleton';
import { formatDistanceToNow } from 'date-fns';
import { GitCompareArrows } from 'lucide-react';
import Link from 'next/link';

interface ArbTableProps {
  opportunities: ArbitrageOpportunity[];
  isLoading?: boolean;
}

export default function ArbTable({ opportunities, isLoading }: ArbTableProps) {
  if (!isLoading && opportunities.length === 0) {
    return (
      <EmptyState
        icon={<GitCompareArrows className="h-12 w-12" />}
        title="No arbitrage opportunities"
        description="Check back soon. New opportunities are detected automatically."
      />
    );
  }

  return (
    <>
      {/* Desktop table */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-xs font-medium uppercase tracking-wider text-gray-500">
              <th className="px-4 py-3">Market</th>
              <th className="px-4 py-3">Platform A</th>
              <th className="px-4 py-3">Platform B</th>
              <th className="px-4 py-3">Spread</th>
              <th className="px-4 py-3">Similarity</th>
              <th className="px-4 py-3">Method</th>
              <th className="px-4 py-3">Last Checked</th>
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <ArbTableRowSkeleton key={i} />
                ))
              : opportunities.map((opp) => (
                  <tr
                    key={opp.id}
                    className="border-b border-gray-800/50 transition-colors hover:bg-gray-800/30"
                  >
                    <td className="max-w-xs px-4 py-3">
                      <Link
                        href={`/arbitrage/${opp.id}`}
                        className="line-clamp-1 font-medium text-gray-200 hover:text-white"
                      >
                        {opp.market_a.question}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <PlatformBadge platform={opp.market_a.platform_name} />
                        <OddsDisplay
                          probability={Object.values(opp.market_a.outcome_prices)[0] ?? 0}
                          size="sm"
                        />
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <PlatformBadge platform={opp.market_b.platform_name} />
                        <OddsDisplay
                          probability={Object.values(opp.market_b.outcome_prices)[0] ?? 0}
                          size="sm"
                        />
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {opp.odds_delta != null && (
                        <ArbSpreadBadge spread={opp.odds_delta} />
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-400">
                      {(opp.similarity_score * 100).toFixed(0)}%
                    </td>
                    <td className="px-4 py-3">
                      <span className="rounded-md bg-gray-800 px-2 py-0.5 text-[11px] font-medium text-gray-400">
                        {opp.match_method}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {formatDistanceToNow(new Date(opp.last_checked_at), {
                        addSuffix: true,
                      })}
                    </td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="space-y-3 md:hidden">
        {isLoading
          ? Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="h-40 animate-pulse rounded-xl bg-gray-900"
              />
            ))
          : opportunities.map((opp) => (
              <ArbCard key={opp.id} opportunity={opp} />
            ))}
      </div>
    </>
  );
}
