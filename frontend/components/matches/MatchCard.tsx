'use client';

import { useState } from 'react';
import type { ArbitrageOpportunity, PriceSnapshot } from '@/lib/types';
import { usePriceHistory } from '@/lib/queries/useMarkets';
import PlatformBadge from '@/components/markets/PlatformBadge';
import OddsDisplay from '@/components/markets/OddsDisplay';
import ArbSpreadBadge from '@/components/arbitrage/ArbSpreadBadge';
import ErrorBoundary from '@/components/shared/ErrorBoundary';
import { cn, formatVolume } from '@/lib/utils/format';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from 'recharts';
import { ChevronDown, ExternalLink } from 'lucide-react';
import { format } from 'date-fns';

const TIME_RANGES = ['24h', '7d', '30d'] as const;

interface MatchCardProps {
  pair: ArbitrageOpportunity;
}

function buildOverlayData(
  historyA: PriceSnapshot[] | undefined,
  historyB: PriceSnapshot[] | undefined
) {
  const allTimestamps = new Set<string>();
  historyA?.forEach((s) => allTimestamps.add(s.timestamp));
  historyB?.forEach((s) => allTimestamps.add(s.timestamp));

  const sorted = Array.from(allTimestamps).sort();
  const mapA = new Map(historyA?.map((s) => [s.timestamp, s]) ?? []);
  const mapB = new Map(historyB?.map((s) => [s.timestamp, s]) ?? []);

  return sorted.map((ts) => {
    const entry: Record<string, number | string> = {
      time: format(new Date(ts), 'MMM d HH:mm'),
    };
    const a = mapA.get(ts);
    const b = mapB.get(ts);
    if (a) entry.platformA = Object.values(a.outcome_prices)[0] ?? 0;
    if (b) entry.platformB = Object.values(b.outcome_prices)[0] ?? 0;
    return entry;
  });
}

export default function MatchCard({ pair }: MatchCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [timeRange, setTimeRange] = useState<string>('7d');

  const { market_a, market_b } = pair;

  const { data: historyA } = usePriceHistory(
    expanded ? market_a.id : 0,
    timeRange
  );
  const { data: historyB } = usePriceHistory(
    expanded ? market_b.id : 0,
    timeRange
  );

  const chartData = expanded ? buildOverlayData(historyA, historyB) : [];
  const gradIdA = `matchGradA-${pair.id}`;
  const gradIdB = `matchGradB-${pair.id}`;

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 transition-colors hover:border-gray-700">
      {/* Header — always visible, clickable to toggle */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start gap-4 p-4 text-left"
      >
        <div className="min-w-0 flex-1">
          <h3 className="mb-2 line-clamp-2 text-sm font-semibold text-gray-100">
            {market_a.question}
          </h3>

          <div className="flex flex-wrap items-center gap-3">
            {/* Platform A */}
            <div className="flex items-center gap-2">
              <PlatformBadge platform={market_a.platform_name} />
              <OddsDisplay
                probability={Object.values(market_a.outcome_prices)[0] ?? 0}
                size="sm"
              />
            </div>

            <span className="text-gray-600">vs</span>

            {/* Platform B */}
            <div className="flex items-center gap-2">
              <PlatformBadge platform={market_b.platform_name} />
              <OddsDisplay
                probability={Object.values(market_b.outcome_prices)[0] ?? 0}
                size="sm"
              />
            </div>

            {pair.odds_delta != null && pair.odds_delta > 0 && (
              <ArbSpreadBadge spread={pair.odds_delta} />
            )}
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-gray-500">
            <span>Similarity: {(pair.similarity_score * 100).toFixed(0)}%</span>
            <span className="rounded-md bg-gray-800 px-2 py-0.5 text-[10px] font-medium text-gray-400">
              {pair.match_method}
            </span>
            {market_a.category && (
              <span className="text-gray-500">{market_a.category}</span>
            )}
          </div>
        </div>

        <ChevronDown
          className={cn(
            'mt-1 h-5 w-5 shrink-0 text-gray-500 transition-transform',
            expanded && 'rotate-180'
          )}
        />
      </button>

      {/* Expanded content — price history overlay */}
      {expanded && (
        <div className="border-t border-gray-800 px-4 pb-4 pt-3">
          {/* Market details side by side */}
          <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <MarketSummary market={market_a} color="purple" />
            <MarketSummary market={market_b} color="blue" />
          </div>

          {/* Price history chart */}
          <ErrorBoundary>
            <div className="rounded-lg border border-gray-800 bg-gray-950/50 p-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[11px] font-medium text-gray-500">
                  Price History Overlay
                </span>
                <div className="flex overflow-hidden rounded border border-gray-800">
                  {TIME_RANGES.map((range) => (
                    <button
                      key={range}
                      onClick={(e) => {
                        e.stopPropagation();
                        setTimeRange(range);
                      }}
                      className={cn(
                        'px-2 py-0.5 text-[10px] font-medium transition-colors',
                        timeRange === range
                          ? 'bg-emerald-600 text-white'
                          : 'bg-gray-900 text-gray-500 hover:text-gray-300'
                      )}
                    >
                      {range}
                    </button>
                  ))}
                </div>
              </div>

              <div className="h-48">
                {chartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                      <defs>
                        <linearGradient
                          id={gradIdA}
                          x1="0"
                          y1="0"
                          x2="0"
                          y2="1"
                        >
                          <stop
                            offset="5%"
                            stopColor="#a855f7"
                            stopOpacity={0.2}
                          />
                          <stop
                            offset="95%"
                            stopColor="#a855f7"
                            stopOpacity={0}
                          />
                        </linearGradient>
                        <linearGradient
                          id={gradIdB}
                          x1="0"
                          y1="0"
                          x2="0"
                          y2="1"
                        >
                          <stop
                            offset="5%"
                            stopColor="#3b82f6"
                            stopOpacity={0.2}
                          />
                          <stop
                            offset="95%"
                            stopColor="#3b82f6"
                            stopOpacity={0}
                          />
                        </linearGradient>
                      </defs>
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="#1f2937"
                        vertical={false}
                      />
                      <XAxis
                        dataKey="time"
                        tick={{ fontSize: 9, fill: '#6b7280' }}
                        axisLine={false}
                        tickLine={false}
                        interval="preserveStartEnd"
                      />
                      <YAxis
                        domain={[0, 1]}
                        tick={{ fontSize: 9, fill: '#6b7280' }}
                        axisLine={false}
                        tickLine={false}
                        tickFormatter={(v: number) =>
                          `${(v * 100).toFixed(0)}%`
                        }
                        width={32}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#111827',
                          border: '1px solid #374151',
                          borderRadius: '8px',
                          fontSize: '11px',
                        }}
                        labelStyle={{ color: '#9ca3af' }}
                        formatter={(value, name) => [
                          `${(Number(value) * 100).toFixed(1)}%`,
                          name === 'platformA'
                            ? market_a.platform_name
                            : market_b.platform_name,
                        ]}
                      />
                      <Legend
                        wrapperStyle={{ fontSize: '11px' }}
                        formatter={(value: string) =>
                          value === 'platformA'
                            ? market_a.platform_name
                            : market_b.platform_name
                        }
                      />
                      <Area
                        type="monotone"
                        dataKey="platformA"
                        stroke="#a855f7"
                        fill={`url(#${gradIdA})`}
                        strokeWidth={1.5}
                        connectNulls
                      />
                      <Area
                        type="monotone"
                        dataKey="platformB"
                        stroke="#3b82f6"
                        fill={`url(#${gradIdB})`}
                        strokeWidth={1.5}
                        connectNulls
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-[11px] text-gray-600">
                    {historyA === undefined
                      ? 'Loading price history...'
                      : 'No price history available'}
                  </div>
                )}
              </div>
            </div>
          </ErrorBoundary>

          {/* Trade links */}
          <div className="mt-3 flex flex-wrap gap-2">
            {market_a.deep_link_url && (
              <a
                href={market_a.deep_link_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-md bg-purple-600 px-2.5 py-1 text-[11px] font-semibold text-white transition-colors hover:bg-purple-500"
              >
                {market_a.platform_name} <ExternalLink className="h-3 w-3" />
              </a>
            )}
            {market_b.deep_link_url && (
              <a
                href={market_b.deep_link_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-md bg-blue-600 px-2.5 py-1 text-[11px] font-semibold text-white transition-colors hover:bg-blue-500"
              >
                {market_b.platform_name} <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function MarketSummary({
  market,
  color,
}: {
  market: ArbitrageOpportunity['market_a'];
  color: 'purple' | 'blue';
}) {
  const borderColor =
    color === 'purple' ? 'border-purple-800/50' : 'border-blue-800/50';

  return (
    <div
      className={cn(
        'rounded-lg border bg-gray-950/50 p-3',
        borderColor
      )}
    >
      <div className="mb-2 flex items-center justify-between">
        <PlatformBadge platform={market.platform_name} />
        <OddsDisplay
          probability={Object.values(market.outcome_prices)[0] ?? 0}
          size="md"
        />
      </div>
      <div className="space-y-1 text-[11px] text-gray-500">
        <div className="flex justify-between">
          <span>Volume 24h</span>
          <span className="text-gray-300">
            {formatVolume(market.volume_24h ?? 0)}
          </span>
        </div>
        <div className="flex justify-between">
          <span>Liquidity</span>
          <span className="text-gray-300">
            {formatVolume(market.liquidity ?? 0)}
          </span>
        </div>
        {market.end_date && (
          <div className="flex justify-between">
            <span>Expires</span>
            <span className="text-gray-300">
              {format(new Date(market.end_date), 'MMM d, yyyy')}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
