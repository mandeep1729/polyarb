'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { usePriceHistory } from '@/lib/queries/useMarkets';
import ComparisonView from '@/components/arbitrage/ComparisonView';
import ErrorBoundary from '@/components/shared/ErrorBoundary';
import { cn } from '@/lib/utils/format';
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
import { ArrowLeft, ExternalLink } from 'lucide-react';
import Link from 'next/link';
import { format } from 'date-fns';
import type { ArbitrageOpportunity } from '@/lib/types';

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

const TIME_RANGES = ['24h', '7d', '30d'] as const;

export default function ArbDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [timeRange, setTimeRange] = useState<string>('7d');

  const { data: opportunity, isLoading } = useQuery({
    queryKey: ['arbitrage', id],
    queryFn: async () => {
      const res = await fetch(`${API_URL}/arbitrage/${id}`);
      if (!res.ok) throw new Error('Failed to fetch');
      return res.json() as Promise<ArbitrageOpportunity>;
    },
    enabled: !!id,
  });

  const { data: historyA } = usePriceHistory(
    opportunity?.market_a.id ?? 0,
    timeRange
  );
  const { data: historyB } = usePriceHistory(
    opportunity?.market_b.id ?? 0,
    timeRange
  );

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-48 animate-pulse rounded bg-gray-800" />
        <div className="flex gap-4">
          <div className="h-64 flex-1 animate-pulse rounded-xl bg-gray-900" />
          <div className="h-64 flex-1 animate-pulse rounded-xl bg-gray-900" />
        </div>
      </div>
    );
  }

  if (!opportunity) {
    return (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <h2 className="text-xl font-bold text-gray-200">
          Opportunity not found
        </h2>
        <Link
          href="/arbitrage"
          className="text-sm text-emerald-400 hover:underline"
        >
          Back to arbitrage
        </Link>
      </div>
    );
  }

  // Merge price histories for overlay chart
  const chartData: Record<string, number | string>[] = [];
  const allTimestamps = new Set<string>();
  historyA?.forEach((s) => allTimestamps.add(s.timestamp));
  historyB?.forEach((s) => allTimestamps.add(s.timestamp));

  const sortedTimestamps = Array.from(allTimestamps).sort();
  const mapA = new Map(historyA?.map((s) => [s.timestamp, s]) ?? []);
  const mapB = new Map(historyB?.map((s) => [s.timestamp, s]) ?? []);

  for (const ts of sortedTimestamps) {
    const entry: Record<string, number | string> = {
      time: format(new Date(ts), 'MMM d HH:mm'),
    };
    const a = mapA.get(ts);
    const b = mapB.get(ts);
    if (a) entry.platformA = Object.values(a.outcome_prices)[0] ?? 0;
    if (b) entry.platformB = Object.values(b.outcome_prices)[0] ?? 0;
    chartData.push(entry);
  }

  return (
    <div className="space-y-6">
      <Link
        href="/arbitrage"
        className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-200"
      >
        <ArrowLeft className="h-4 w-4" /> Back to Arbitrage
      </Link>

      <h1 className="text-xl font-bold text-white">Arbitrage Comparison</h1>

      <ErrorBoundary>
        <ComparisonView opportunity={opportunity} />
      </ErrorBoundary>

      {/* Price history overlay */}
      <ErrorBoundary>
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-300">
              Price History Overlay
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
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="gradA" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#a855f7" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="#a855f7" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="gradB" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
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
                    formatter={(value, name) => [
                      `${(Number(value) * 100).toFixed(1)}%`,
                      name === 'platformA'
                        ? opportunity.market_a.platform_name
                        : opportunity.market_b.platform_name,
                    ]}
                  />
                  <Legend
                    formatter={(value: string) =>
                      value === 'platformA'
                        ? opportunity.market_a.platform_name
                        : opportunity.market_b.platform_name
                    }
                  />
                  <Area
                    type="monotone"
                    dataKey="platformA"
                    stroke="#a855f7"
                    fill="url(#gradA)"
                    strokeWidth={2}
                    connectNulls
                  />
                  <Area
                    type="monotone"
                    dataKey="platformB"
                    stroke="#3b82f6"
                    fill="url(#gradB)"
                    strokeWidth={2}
                    connectNulls
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

      {/* Deep links */}
      <div className="flex flex-wrap gap-3">
        {opportunity.market_a.deep_link_url && (
          <a
            href={opportunity.market_a.deep_link_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-purple-500"
          >
            Trade on {opportunity.market_a.platform_name}
            <ExternalLink className="h-4 w-4" />
          </a>
        )}
        {opportunity.market_b.deep_link_url && (
          <a
            href={opportunity.market_b.deep_link_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-500"
          >
            Trade on {opportunity.market_b.platform_name}
            <ExternalLink className="h-4 w-4" />
          </a>
        )}
      </div>
    </div>
  );
}
