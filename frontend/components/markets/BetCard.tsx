'use client';

import Link from 'next/link';
import type { Market, PriceSnapshot } from '@/lib/types';
import { cn } from '@/lib/utils/format';
import PlatformBadge from './PlatformBadge';
import OddsDisplay from './OddsDisplay';
import SparklineChart from './SparklineChart';
import VolumeBar from './VolumeBar';
import LiquidityIndicator from './LiquidityIndicator';
import ExpiryCountdown from './ExpiryCountdown';
import { ExternalLink, TrendingUp } from 'lucide-react';

// DB category → display name
const CATEGORY_DISPLAY: Record<string, string> = {
  politics: 'Politics',
  crypto: 'Crypto',
  sports: 'Sports',
  economics: 'Finance',
  entertainment: 'Entertainment',
  technology: 'Science',
  climate: 'Weather',
};

const categoryColors: Record<string, string> = {
  politics: 'bg-blue-900/50 text-blue-300',
  crypto: 'bg-orange-900/50 text-orange-300',
  sports: 'bg-green-900/50 text-green-300',
  economics: 'bg-emerald-900/50 text-emerald-300',
  entertainment: 'bg-pink-900/50 text-pink-300',
  technology: 'bg-cyan-900/50 text-cyan-300',
  climate: 'bg-sky-900/50 text-sky-300',
};

interface BetCardProps {
  market: Market;
  sparklineData?: PriceSnapshot[];
  arbSpread?: number | null;
}

export default function BetCard({
  market,
  sparklineData,
  arbSpread,
}: BetCardProps) {
  const slug = market.id;

  return (
    <Link
      href={`/markets/${slug}`}
      className="group block rounded-xl border border-gray-800 bg-gray-900 p-4 transition-all duration-200 hover:scale-[1.01] hover:border-gray-700"
    >
      {/* Header badges */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {market.category && (
          <span
            className={cn(
              'rounded-full px-2.5 py-0.5 text-[11px] font-medium',
              categoryColors[market.category] ?? 'bg-gray-800 text-gray-400'
            )}
          >
            {CATEGORY_DISPLAY[market.category] ?? market.category}
          </span>
        )}
        <PlatformBadge platform={market.platform_name} />
        {arbSpread != null && arbSpread > 0 && (
          <span className="inline-flex items-center gap-0.5 rounded-full bg-emerald-900/50 px-2 py-0.5 text-[11px] font-semibold text-emerald-400">
            <TrendingUp className="h-3 w-3" />+
            {arbSpread.toFixed(1)}%
          </span>
        )}
      </div>

      {/* Question */}
      <h3 className="mb-3 line-clamp-2 text-sm font-semibold leading-snug text-gray-100 group-hover:text-white">
        {market.question}
      </h3>

      {/* Outcomes & odds */}
      <div className="mb-3 space-y-1.5">
        {Object.entries(market.outcomes).map(([outcome, _]) => (
          <div
            key={outcome}
            className="flex items-center justify-between rounded-lg bg-gray-800/60 px-3 py-1.5"
          >
            <span className="text-xs text-gray-300">{outcome}</span>
            <OddsDisplay
              probability={market.outcome_prices[outcome] ?? 0}
              size="sm"
            />
          </div>
        ))}
      </div>

      {/* Sparkline + stats */}
      <div className="mb-3 flex items-center justify-between">
        <SparklineChart data={sparklineData ?? []} />
        <div className="flex items-center gap-3">
          <LiquidityIndicator liquidity={market.liquidity} />
          <ExpiryCountdown endDate={market.end_date} />
        </div>
      </div>

      {/* Volume */}
      <VolumeBar volume={market.volume_24h} />

      {/* Deep link */}
      {market.deep_link_url && (
        <div className="mt-2 flex justify-end">
          <span
            onClick={(e) => {
              e.preventDefault();
              window.open(market.deep_link_url!, '_blank');
            }}
            className="inline-flex items-center gap-1 text-[11px] text-gray-500 hover:text-gray-300"
          >
            Trade <ExternalLink className="h-3 w-3" />
          </span>
        </div>
      )}
    </Link>
  );
}
