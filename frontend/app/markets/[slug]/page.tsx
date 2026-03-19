'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import { useMarket, usePriceHistory } from '@/lib/queries/useMarkets';
import { useArbitrage } from '@/lib/queries/useArbitrage';
import OddsDisplay from '@/components/markets/OddsDisplay';
import PlatformBadge from '@/components/markets/PlatformBadge';
import VolumeBar from '@/components/markets/VolumeBar';
import LiquidityIndicator from '@/components/markets/LiquidityIndicator';
import ExpiryCountdown from '@/components/markets/ExpiryCountdown';
import ArbSpreadBadge from '@/components/arbitrage/ArbSpreadBadge';
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
import { ExternalLink, ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { format } from 'date-fns';

const TIME_RANGES = ['24h', '7d', '30d'] as const;

export default function MarketDetailPage() {
  const params = useParams();
  const slug = params.slug as string;
  const [timeRange, setTimeRange] = useState<string>('7d');

  const { data: market, isLoading: marketLoading } = useMarket(slug);
  const { data: priceHistory } = usePriceHistory(
    market?.id ?? 0,
    timeRange
  );
  const { data: arbData } = useArbitrage({ limit: 50 });

  const relatedArbs =
    arbData?.pages
      .flatMap((p) => p.items)
      .filter(
        (a) => a.market_a.id === market?.id || a.market_b.id === market?.id
      ) ?? [];

  if (marketLoading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-48 animate-pulse rounded bg-gray-800" />
        <div className="h-6 w-full animate-pulse rounded bg-gray-800" />
        <div className="h-64 animate-pulse rounded-xl bg-gray-900" />
      </div>
    );
  }

  if (!market) {
    return (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <h2 className="text-xl font-bold text-gray-200">Market not found</h2>
        <Link
          href="/markets"
          className="text-sm text-emerald-400 hover:underline"
        >
          Back to markets
        </Link>
      </div>
    );
  }

  const chartData = priceHistory?.map((snap) => ({
    time: format(new Date(snap.timestamp), 'MMM d HH:mm'),
    price: Object.values(snap.outcome_prices)[0] ?? 0,
    ...(Object.values(snap.outcome_prices)[1] != null
      ? { price2: Object.values(snap.outcome_prices)[1] }
      : {}),
  }));

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        href="/markets"
        className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-200"
      >
        <ArrowLeft className="h-4 w-4" /> Back to Markets
      </Link>

      {/* Header */}
      <div>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          {market.category && (
            <span className="rounded-full bg-gray-800 px-3 py-0.5 text-xs font-medium text-gray-300">
              {market.category}
            </span>
          )}
          <PlatformBadge platform={market.platform_name} />
          {relatedArbs.length > 0 && relatedArbs[0].odds_delta != null && (
            <ArbSpreadBadge spread={relatedArbs[0].odds_delta} />
          )}
        </div>
        <h1 className="text-xl font-bold text-white sm:text-2xl">
          {market.question}
        </h1>
        {market.description && (
          <p className="mt-2 text-sm leading-relaxed text-gray-400">
            {market.description}
          </p>
        )}
      </div>

      {/* Odds display */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {Object.entries(market.outcomes).map(([outcome, _]) => (
          <div
            key={outcome}
            className="flex items-center justify-between rounded-xl border border-gray-800 bg-gray-900 p-4"
          >
            <span className="font-medium text-gray-200">{outcome}</span>
            <OddsDisplay
              probability={market.outcome_prices[outcome] ?? 0}
              size="lg"
            />
          </div>
        ))}
      </div>

      {/* Price history chart */}
      <ErrorBoundary>
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-300">
              Price History
            </h2>
            <div className="flex overflow-hidden rounded-lg border border-gray-800">
              {TIME_RANGES.map((range) => (
                <button
                  key={range}
                  onClick={() => setTimeRange(range)}
                  className={cn(
                    'px-3 py-1 text-xs font-medium transition-colors',
                    timeRange === range
                      ? 'bg-emerald-600 text-white'
                      : 'bg-gray-900 text-gray-400 hover:text-gray-200',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50'
                  )}
                >
                  {range}
                </button>
              ))}
            </div>
          </div>

          <div className="h-64">
            {chartData && chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient
                      id="priceGradient"
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
                    tick={{ fontSize: 10, fill: '#6b7280' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    domain={[0, 1]}
                    tick={{ fontSize: 10, fill: '#6b7280' }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#111827',
                      border: '1px solid #374151',
                      borderRadius: '8px',
                      fontSize: '12px',
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
                    fill="url(#priceGradient)"
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-gray-600">
                No price history available
              </div>
            )}
          </div>
        </div>
      </ErrorBoundary>

      {/* Details grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <h3 className="mb-2 text-xs font-medium uppercase text-gray-500">
            Volume
          </h3>
          <div className="mb-1 text-lg font-bold text-gray-100">
            {formatVolume(market.volume_24h ?? 0)}{' '}
            <span className="text-xs font-normal text-gray-500">24h</span>
          </div>
          <div className="text-sm text-gray-400">
            {formatVolume(market.volume_total ?? 0)} total
          </div>
        </div>

        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <h3 className="mb-2 text-xs font-medium uppercase text-gray-500">
            Liquidity
          </h3>
          <LiquidityIndicator liquidity={market.liquidity} />
          <div className="mt-1 text-lg font-bold text-gray-100">
            {formatVolume(market.liquidity ?? 0)}
          </div>
        </div>

        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <h3 className="mb-2 text-xs font-medium uppercase text-gray-500">
            Details
          </h3>
          <div className="space-y-1 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Status</span>
              <span className="capitalize text-gray-200">{market.status}</span>
            </div>
            {market.resolution && (
              <div className="flex justify-between">
                <span className="text-gray-500">Resolution</span>
                <span className="text-gray-200">{market.resolution}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Expiry */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="mb-1 text-xs font-medium uppercase text-gray-500">
              Expiry
            </h3>
            <ExpiryCountdown endDate={market.end_date} className="text-sm" />
          </div>
          {market.deep_link_url && (
            <a
              href={market.deep_link_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-500"
            >
              Trade on {market.platform_name}
              <ExternalLink className="h-4 w-4" />
            </a>
          )}
        </div>
      </div>

      {/* Related arb opportunities */}
      {relatedArbs.length > 0 && (
        <div>
          <h2 className="mb-3 text-lg font-bold text-gray-100">
            Arbitrage Opportunities
          </h2>
          <div className="space-y-2">
            {relatedArbs.map((arb) => (
              <Link
                key={arb.id}
                href={`/arbitrage/${arb.id}`}
                className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-900 px-4 py-3 transition-all hover:border-gray-700"
              >
                <div className="flex items-center gap-3">
                  <PlatformBadge
                    platform={
                      arb.market_a.id === market.id
                        ? arb.market_b.platform_name
                        : arb.market_a.platform_name
                    }
                  />
                  <span className="text-sm text-gray-300">
                    {arb.market_a.id === market.id
                      ? arb.market_b.question
                      : arb.market_a.question}
                  </span>
                </div>
                {arb.odds_delta != null && (
                  <ArbSpreadBadge spread={arb.odds_delta} />
                )}
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
