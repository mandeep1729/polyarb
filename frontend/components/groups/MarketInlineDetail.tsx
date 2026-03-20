'use client';

import { usePriceHistory } from '@/lib/queries/useMarkets';
import OddsDisplay from '@/components/markets/OddsDisplay';
import PlatformBadge from '@/components/markets/PlatformBadge';
import ExpiryCountdown from '@/components/markets/ExpiryCountdown';
import { formatVolume } from '@/lib/utils/format';
import { ExternalLink } from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { format } from 'date-fns';
import type { Market } from '@/lib/types';

interface MarketInlineDetailProps {
  market: Market;
}

/**
 * Compact inline detail view for a market, shown when a member row is
 * clicked within the expanded group card. Displays outcome odds, 7-day
 * price chart, volume/liquidity stats, expiry, and a trade deep link.
 */
export default function MarketInlineDetail({ market }: MarketInlineDetailProps) {
  const { data: priceHistory } = usePriceHistory(market.id, '7d');

  const chartData = priceHistory?.map((snap) => ({
    time: format(new Date(snap.timestamp), 'MMM d'),
    price: Object.values(snap.outcome_prices)[0] ?? 0,
  }));

  return (
    <div className="space-y-3 border-l-2 border-l-gray-700 bg-gray-900/50 p-4">
      {/* Outcome odds */}
      <div className="flex flex-wrap gap-2">
        {Object.entries(market.outcome_prices).map(([outcome, price]) => (
          <div
            key={outcome}
            className="flex items-center gap-2 rounded-lg border border-gray-800 bg-gray-900 px-3 py-1.5"
          >
            <span className="text-xs text-gray-400">{outcome}</span>
            <OddsDisplay probability={price} size="sm" />
          </div>
        ))}
      </div>

      {/* Price history chart */}
      {chartData && chartData.length > 1 && (
        <div className="h-[100px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id={`inline-price-${market.id}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="time"
                tick={{ fill: '#6b7280', fontSize: 9 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                domain={[0, 1]}
                tick={{ fill: '#6b7280', fontSize: 9 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
                width={32}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1f2937',
                  border: '1px solid #374151',
                  borderRadius: '8px',
                  fontSize: '11px',
                }}
                formatter={(value) => [`${(Number(value) * 100).toFixed(1)}%`, 'Price']}
              />
              <Area
                type="monotone"
                dataKey="price"
                stroke="#10b981"
                fill={`url(#inline-price-${market.id})`}
                strokeWidth={1.5}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Stats row */}
      <div className="flex flex-wrap items-center gap-4 text-xs">
        <div>
          <span className="text-gray-500">Volume 24h </span>
          <span className="text-gray-300">{formatVolume(market.volume_24h ?? 0)}</span>
        </div>
        <div>
          <span className="text-gray-500">Liquidity </span>
          <span className="text-gray-300">{formatVolume(market.liquidity ?? 0)}</span>
        </div>
        <ExpiryCountdown endDate={market.end_date} />
        <PlatformBadge platform={market.platform_name} />
      </div>

      {/* Trade link */}
      {market.deep_link_url && (
        <a
          href={market.deep_link_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-emerald-500"
        >
          Trade on {market.platform_name}
          <ExternalLink className="h-3 w-3" />
        </a>
      )}
    </div>
  );
}
