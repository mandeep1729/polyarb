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
import BetCardDetail from './BetCardDetail';
import { ExternalLink, TrendingUp, ChevronDown } from 'lucide-react';

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
  expanded?: boolean;
  onToggle?: () => void;
  selected?: boolean;
  onSelect?: () => void;
}

function CardContent({
  market,
  sparklineData,
  arbSpread,
  expanded,
  expandable,
}: {
  market: Market;
  sparklineData?: PriceSnapshot[];
  arbSpread?: number | null;
  expanded: boolean;
  expandable: boolean;
}) {
  return (
    <>
      {/* Header badges */}
      <div className="mb-2 flex flex-wrap items-center gap-2">
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
        <span className="ml-auto flex items-center gap-1.5">
          <ExpiryCountdown endDate={market.end_date} />
          {expandable && (
            <ChevronDown
              className={cn(
                'h-3.5 w-3.5 text-gray-500 transition-transform duration-200',
                expanded && 'rotate-180'
              )}
            />
          )}
        </span>
      </div>

      {/* Question */}
      <h3
        className={cn(
          'mb-2 text-sm font-semibold leading-snug text-gray-100 group-hover:text-white',
          !expanded && 'line-clamp-2'
        )}
      >
        {market.question}
      </h3>

      {/* Collapsed view: compact stats */}
      {!expanded && (
        <>
          {Object.entries(market.outcomes).length === 2 ? (
            <div className="mb-2 flex items-center justify-between rounded-lg bg-gray-800/60 px-2.5 py-1">
              {Object.entries(market.outcomes).map(([outcome]) => (
                <div key={outcome} className="flex items-center gap-1.5">
                  <span className="text-xs text-gray-300">{outcome}</span>
                  <OddsDisplay
                    probability={market.outcome_prices[outcome] ?? 0}
                    size="sm"
                  />
                </div>
              ))}
            </div>
          ) : (
            <div className="mb-2 space-y-1">
              {Object.entries(market.outcomes).map(([outcome]) => (
                <div
                  key={outcome}
                  className="flex items-center justify-between rounded-lg bg-gray-800/60 px-2.5 py-1"
                >
                  <span className="text-xs text-gray-300">{outcome}</span>
                  <OddsDisplay
                    probability={market.outcome_prices[outcome] ?? 0}
                    size="sm"
                  />
                </div>
              ))}
            </div>
          )}

          <div className="mb-2 flex items-center justify-between">
            <SparklineChart data={sparklineData ?? []} />
            <LiquidityIndicator liquidity={market.liquidity} />
          </div>

          <VolumeBar volume={market.volume_24h} />

          {market.deep_link_url && (
            <div className="mt-2 flex justify-end">
              <span
                onClick={(e) => {
                  e.stopPropagation();
                  e.preventDefault();
                  window.open(market.deep_link_url!, '_blank');
                }}
                className="inline-flex items-center gap-1 text-[11px] text-gray-500 hover:text-gray-300"
              >
                Trade <ExternalLink className="h-3 w-3" />
              </span>
            </div>
          )}
        </>
      )}

      {/* Expanded view: full detail */}
      {expanded && <BetCardDetail market={market} />}
    </>
  );
}

export default function BetCard({
  market,
  sparklineData,
  arbSpread,
  expanded = false,
  onToggle,
  selected = false,
  onSelect,
}: BetCardProps) {
  const cardStyles = cn(
    'group block rounded-xl border bg-gray-900 p-4 transition-all duration-200',
    selected
      ? 'border-amber-500/70 ring-2 ring-amber-500/30'
      : expanded
        ? 'border-emerald-700/50 ring-1 ring-emerald-700/20'
        : 'border-gray-800 hover:scale-[1.01] hover:border-gray-700'
  );

  const content = (
    <CardContent
      market={market}
      sparklineData={sparklineData}
      arbSpread={arbSpread}
      expanded={expanded}
      expandable={!!onToggle && !onSelect}
    />
  );

  // Pair selection mode takes priority
  if (onSelect) {
    return (
      <div
        role="button"
        tabIndex={0}
        onClick={onSelect}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onSelect();
          }
        }}
        className={cn(cardStyles, 'cursor-pointer')}
      >
        {content}
      </div>
    );
  }

  // When onToggle is provided, render as expandable div
  if (onToggle) {
    return (
      <div
        role="button"
        tabIndex={0}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onToggle();
          }
        }}
        className={cn(cardStyles, 'cursor-pointer')}
      >
        {content}
      </div>
    );
  }

  // Default: render as Link to detail page
  return (
    <Link href={`/markets/${market.id}`} className={cardStyles}>
      {content}
    </Link>
  );
}
