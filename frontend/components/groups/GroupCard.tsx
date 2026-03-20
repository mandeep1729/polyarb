'use client';

import { useState } from 'react';
import type { MarketGroup } from '@/lib/types';
import { cn } from '@/lib/utils/format';
import { formatVolume } from '@/lib/utils/format';
import OddsDisplay from '@/components/markets/OddsDisplay';
import ArbSpreadBadge from '@/components/arbitrage/ArbSpreadBadge';
import { ChevronDown, ChevronUp, Layers, ExternalLink } from 'lucide-react';
import GroupExpandedView from './GroupExpandedView';

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

interface GroupCardProps {
  group: MarketGroup;
}

export default function GroupCard({ group }: GroupCardProps) {
  const [expanded, setExpanded] = useState(false);

  const hasConsensus = group.consensus_yes != null;
  const hasDisagreement =
    group.disagreement_score != null && group.disagreement_score > 0;

  return (
    <div
      className={cn(
        'rounded-xl border border-gray-800 bg-gray-900 transition-all duration-200',
        expanded
          ? 'border-gray-700'
          : 'hover:border-gray-700 hover:scale-[1.005]'
      )}
    >
      {/* Collapsed card — always visible */}
      <button
        type="button"
        className="w-full p-4 text-left"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-label={group.canonical_question}
      >
        {/* Category badge + member count */}
        <div className="mb-2 flex flex-wrap items-center gap-2">
          {group.category && (
            <span
              className={cn(
                'rounded-full px-2.5 py-0.5 text-[11px] font-medium',
                categoryColors[group.category] ?? 'bg-gray-800 text-gray-400'
              )}
            >
              {CATEGORY_DISPLAY[group.category] ?? group.category}
            </span>
          )}
          <span className="inline-flex items-center gap-1 text-[11px] text-gray-500">
            <Layers className="h-3 w-3" />
            {group.member_count} markets
          </span>
          <div className="ml-auto">
            {expanded ? (
              <ChevronUp className="h-4 w-4 text-gray-500" />
            ) : (
              <ChevronDown className="h-4 w-4 text-gray-500" />
            )}
          </div>
        </div>

        {/* Question — primary text */}
        <h3 className="mb-3 line-clamp-2 text-base font-semibold text-gray-100">
          {group.canonical_question}
        </h3>

        {/* Consensus + Disagreement — side by side */}
        <div className="flex flex-wrap items-center gap-4">
          {/* Consensus */}
          <div className="min-w-0">
            <p className="mb-0.5 text-[11px] font-medium uppercase tracking-wider text-gray-500">
              Consensus
            </p>
            {hasConsensus ? (
              <OddsDisplay
                probability={group.consensus_yes!}
                size="md"
              />
            ) : (
              <span className="text-sm text-gray-600">No data</span>
            )}
          </div>

          {/* Disagreement */}
          {hasDisagreement && (
            <div className="min-w-0">
              <p className="mb-0.5 text-[11px] font-medium uppercase tracking-wider text-gray-500">
                Spread
              </p>
              <ArbSpreadBadge
                spread={group.disagreement_score! * 100}
              />
            </div>
          )}
        </div>

        {/* Meta line */}
        <div className="mt-3 flex items-center gap-3 text-xs text-gray-500">
          {group.total_volume != null && group.total_volume > 0 && (
            <span>{formatVolume(group.total_volume)} vol</span>
          )}
          {group.total_liquidity != null && group.total_liquidity > 0 && (
            <span>{formatVolume(group.total_liquidity)} liq</span>
          )}
        </div>
      </button>

      {/* Expanded view — loads detail data */}
      {expanded && (
        <div className="border-t border-gray-800 px-4 pb-4">
          <GroupExpandedView groupId={group.id} />
        </div>
      )}
    </div>
  );
}
