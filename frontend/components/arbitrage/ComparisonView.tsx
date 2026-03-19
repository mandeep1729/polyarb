'use client';

import type { ArbitrageOpportunity } from '@/lib/types';
import PlatformBadge from '@/components/markets/PlatformBadge';
import OddsDisplay from '@/components/markets/OddsDisplay';
import ArbSpreadBadge from './ArbSpreadBadge';
import VolumeBar from '@/components/markets/VolumeBar';
import LiquidityIndicator from '@/components/markets/LiquidityIndicator';
import ExpiryCountdown from '@/components/markets/ExpiryCountdown';
import { ExternalLink, ArrowLeftRight } from 'lucide-react';
import type { Market } from '@/lib/types';

function MarketSide({ market, label }: { market: Market; label: string }) {
  return (
    <div className="flex-1 rounded-xl border border-gray-800 bg-gray-900 p-5">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-gray-500">
          {label}
        </span>
        <PlatformBadge platform={market.platform_name} />
      </div>

      <h3 className="mb-4 text-sm font-semibold text-gray-100">
        {market.question}
      </h3>

      <div className="mb-4 space-y-2">
        {Object.entries(market.outcomes).map(([outcome, _]) => (
          <div
            key={outcome}
            className="flex items-center justify-between rounded-lg bg-gray-800/60 px-3 py-2"
          >
            <span className="text-sm text-gray-300">{outcome}</span>
            <OddsDisplay
              probability={market.outcome_prices[outcome] ?? 0}
              size="md"
            />
          </div>
        ))}
      </div>

      <div className="space-y-2">
        <VolumeBar volume={market.volume_24h} />
        <div className="flex items-center justify-between">
          <LiquidityIndicator liquidity={market.liquidity} />
          <ExpiryCountdown endDate={market.end_date} />
        </div>
      </div>

      {market.deep_link_url && (
        <a
          href={market.deep_link_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-gray-800 px-3 py-1.5 text-xs font-medium text-gray-300 transition-colors hover:bg-gray-700 hover:text-white"
        >
          Trade on {market.platform_name}
          <ExternalLink className="h-3 w-3" />
        </a>
      )}
    </div>
  );
}

interface ComparisonViewProps {
  opportunity: ArbitrageOpportunity;
}

export default function ComparisonView({ opportunity }: ComparisonViewProps) {
  const { market_a, market_b, odds_delta, similarity_score, match_method } =
    opportunity;

  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
      <MarketSide market={market_a} label="Platform A" />

      {/* Center spread indicator */}
      <div className="flex shrink-0 flex-col items-center justify-center gap-2 py-4 lg:py-8">
        <ArrowLeftRight className="h-5 w-5 text-gray-600" />
        {odds_delta != null && <ArbSpreadBadge spread={odds_delta} />}
        <div className="text-center">
          <div className="text-xs text-gray-500">Similarity</div>
          <div className="text-sm font-semibold text-gray-300">
            {(similarity_score * 100).toFixed(0)}%
          </div>
        </div>
        <span className="rounded-md bg-gray-800 px-2 py-0.5 text-[10px] font-medium text-gray-500">
          {match_method}
        </span>
      </div>

      <MarketSide market={market_b} label="Platform B" />
    </div>
  );
}
