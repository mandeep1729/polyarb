'use client';

import { useGroupDetail, useGroupHistory } from '@/lib/queries/useGroups';
import PlatformBadge from '@/components/markets/PlatformBadge';
import OddsDisplay from '@/components/markets/OddsDisplay';
import Skeleton from '@/components/shared/LoadingSkeleton';
import { formatVolume } from '@/lib/utils/format';
import { ExternalLink, Star } from 'lucide-react';
import Link from 'next/link';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

interface GroupExpandedViewProps {
  groupId: number;
}

export default function GroupExpandedView({ groupId }: GroupExpandedViewProps) {
  const { data: detail, isLoading } = useGroupDetail(groupId);
  const { data: history } = useGroupHistory(groupId, 30);

  if (isLoading) {
    return (
      <div className="space-y-3 pt-4">
        <Skeleton className="h-[120px] w-full rounded-lg" />
        <div className="grid grid-cols-2 gap-3">
          <Skeleton className="h-20 rounded-lg" />
          <Skeleton className="h-20 rounded-lg" />
        </div>
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    );
  }

  if (!detail) return null;

  const { group, members, best_yes_market, best_no_market } = detail;
  const chartData = (history ?? []).map((s) => ({
    time: new Date(s.timestamp).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    }),
    consensus: s.consensus_yes != null ? +(s.consensus_yes * 100).toFixed(1) : null,
  }));

  const topMembers = members.slice(0, 5);

  return (
    <div className="space-y-4 pt-4">
      {/* Consensus Chart */}
      {chartData.length > 1 && (
        <div className="h-[120px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id={`consensus-${groupId}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="time"
                tick={{ fill: '#6b7280', fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: '#6b7280', fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                domain={['dataMin - 5', 'dataMax + 5']}
                tickFormatter={(v) => `${v}%`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1f2937',
                  border: '1px solid #374151',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
                formatter={(value) => [`${value}%`, 'Consensus']}
              />
              <Area
                type="monotone"
                dataKey="consensus"
                stroke="#10b981"
                fill={`url(#consensus-${groupId})`}
                strokeWidth={2}
                connectNulls
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Best Odds Routing */}
      {(best_yes_market || best_no_market) && (
        <div className="grid grid-cols-2 gap-3">
          {best_yes_market && (
            <div className="rounded-lg border-l-2 border-l-emerald-500 bg-gray-800/50 p-3">
              <p className="mb-1 text-[11px] font-medium uppercase tracking-wider text-gray-500">
                Best Yes
              </p>
              <p className="mb-1 text-lg font-bold tabular-nums text-emerald-400">
                {((best_yes_market.outcome_prices?.Yes ?? best_yes_market.yes_ask ?? 0) * 100).toFixed(0)}¢
              </p>
              <PlatformBadge platform={best_yes_market.platform_name} />
              {best_yes_market.deep_link_url && (
                <a
                  href={best_yes_market.deep_link_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-flex items-center gap-1 text-xs text-emerald-500 hover:text-emerald-400"
                >
                  Trade <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
          )}
          {best_no_market && (
            <div className="rounded-lg border-l-2 border-l-red-500 bg-gray-800/50 p-3">
              <p className="mb-1 text-[11px] font-medium uppercase tracking-wider text-gray-500">
                Best No
              </p>
              <p className="mb-1 text-lg font-bold tabular-nums text-red-400">
                {((best_no_market.outcome_prices?.No ?? best_no_market.no_ask ?? 0) * 100).toFixed(0)}¢
              </p>
              <PlatformBadge platform={best_no_market.platform_name} />
              {best_no_market.deep_link_url && (
                <a
                  href={best_no_market.deep_link_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-flex items-center gap-1 text-xs text-red-500 hover:text-red-400"
                >
                  Trade <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
          )}
        </div>
      )}

      {/* Arbitrage opportunity callout */}
      {best_yes_market && best_no_market && (
        <div className="rounded-lg bg-emerald-900/20 px-3 py-2 text-center text-xs text-emerald-400">
          Total: {(
            (best_yes_market.outcome_prices?.Yes ?? best_yes_market.yes_ask ?? 0) +
            (best_no_market.outcome_prices?.No ?? best_no_market.no_ask ?? 0)
          ).toFixed(2) }
          {' '}→{' '}
          {(1 - (
            (best_yes_market.outcome_prices?.Yes ?? best_yes_market.yes_ask ?? 0) +
            (best_no_market.outcome_prices?.No ?? best_no_market.no_ask ?? 0)
          )).toFixed(2)} arb opportunity
        </div>
      )}

      {/* Top Members */}
      <div className="space-y-1">
        {topMembers.map((m) => (
          <Link
            key={m.id}
            href={`/markets/${m.id}`}
            className="flex items-center gap-3 rounded-lg px-2 py-2 text-sm transition-colors hover:bg-gray-800"
          >
            <PlatformBadge platform={m.platform_name} />
            <span className="min-w-0 flex-1 truncate text-gray-300">
              {m.question}
            </span>
            <span className="flex items-center gap-1 tabular-nums text-gray-400">
              {m.id === group.best_yes_market_id && (
                <Star className="h-3 w-3 text-emerald-400" />
              )}
              {m.outcome_prices?.Yes != null
                ? `${(m.outcome_prices.Yes * 100).toFixed(0)}¢`
                : '—'}
            </span>
            <span className="tabular-nums text-gray-500">
              {m.volume_24h != null ? formatVolume(m.volume_24h) : '—'}
            </span>
          </Link>
        ))}
        {members.length > 5 && (
          <p className="px-2 pt-1 text-xs text-gray-500">
            +{members.length - 5} more markets
          </p>
        )}
      </div>
    </div>
  );
}
