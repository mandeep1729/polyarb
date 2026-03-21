'use client';

import { useState } from 'react';
import Link from 'next/link';
import type { Market } from '@/lib/types';
import { usePriceHistory } from '@/lib/queries/useMarkets';
import OddsDisplay from './OddsDisplay';
import LiquidityIndicator from './LiquidityIndicator';
import ExpiryCountdown from './ExpiryCountdown';
import ErrorBoundary from '@/components/shared/ErrorBoundary';
import { formatVolume, cn } from '@/lib/utils/format';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { ExternalLink, Maximize2 } from 'lucide-react';
import { format } from 'date-fns';

const TIME_RANGES = ['24h', '7d', '30d'] as const;

interface BetCardDetailProps {
  market: Market;
}

export default function BetCardDetail({ market }: BetCardDetailProps) {
  const [timeRange, setTimeRange] = useState<string>('7d');
  const { data: priceHistory } = usePriceHistory(market.id, timeRange);

  const chartData = priceHistory?.map((snap) => ({
    time: format(new Date(snap.timestamp), 'MMM d HH:mm'),
    price: Object.values(snap.outcome_prices)[0] ?? 0,
  }));

  return (
    <div className="space-y-3 border-t border-gray-800 pt-3">
      {/* Description */}
      {market.description && (
        <p className="text-xs leading-relaxed text-gray-400">
          {market.description}
        </p>
      )}

      {/* Outcomes - larger display */}
      <div className="space-y-1.5">
        {Object.entries(market.outcomes).map(([outcome]) => (
          <div
            key={outcome}
            className="flex items-center justify-between rounded-lg bg-gray-800/60 px-3 py-2"
          >
            <span className="text-xs font-medium text-gray-200">{outcome}</span>
            <OddsDisplay
              probability={market.outcome_prices[outcome] ?? 0}
              size="lg"
            />
          </div>
        ))}
      </div>

      {/* Price history chart */}
      <ErrorBoundary>
        <div className="rounded-lg border border-gray-800 bg-gray-950/50 p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[11px] font-medium text-gray-500">
              Price History
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

          <div className="h-36">
            {chartData && chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient
                      id={`priceGrad-${market.id}`}
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop
                        offset="5%"
                        stopColor="#10b981"
                        stopOpacity={0.3}
                      />
                      <stop
                        offset="95%"
                        stopColor="#10b981"
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
                    tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
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
                    formatter={(value) => [
                      `${(Number(value) * 100).toFixed(1)}%`,
                      'Price',
                    ]}
                  />
                  <Area
                    type="monotone"
                    dataKey="price"
                    stroke="#10b981"
                    fill={`url(#priceGrad-${market.id})`}
                    strokeWidth={1.5}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-[11px] text-gray-600">
                No price history available
              </div>
            )}
          </div>
        </div>
      </ErrorBoundary>

      {/* Stats row */}
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-lg border border-gray-800 bg-gray-950/50 p-2.5">
          <div className="mb-1 text-[10px] font-medium uppercase text-gray-500">
            Volume
          </div>
          <div className="text-sm font-bold text-gray-100">
            {formatVolume(market.volume_24h ?? 0)}{' '}
            <span className="text-[10px] font-normal text-gray-500">24h</span>
          </div>
          <div className="text-[11px] text-gray-500">
            {formatVolume(market.volume_total ?? 0)} total
          </div>
        </div>
        <div className="rounded-lg border border-gray-800 bg-gray-950/50 p-2.5">
          <div className="mb-1 text-[10px] font-medium uppercase text-gray-500">
            Liquidity
          </div>
          <LiquidityIndicator liquidity={market.liquidity} />
          <div className="mt-0.5 text-sm font-bold text-gray-100">
            {formatVolume(market.liquidity ?? 0)}
          </div>
        </div>
      </div>

      {/* Expiry + actions */}
      <div className="flex items-center justify-between">
        <ExpiryCountdown endDate={market.end_date} className="text-xs" />
        <div className="flex items-center gap-2">
          <Link
            href={`/markets/${market.id}`}
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1 rounded-md border border-gray-700 px-2.5 py-1 text-[11px] text-gray-400 transition-colors hover:border-gray-600 hover:text-gray-200"
          >
            Full page <Maximize2 className="h-3 w-3" />
          </Link>
          {market.deep_link_url && (
            <a
              href={market.deep_link_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-2.5 py-1 text-[11px] font-semibold text-white transition-colors hover:bg-emerald-500"
            >
              Trade <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
