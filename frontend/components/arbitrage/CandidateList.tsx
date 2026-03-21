'use client';

import { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getCandidates,
  generateCandidates,
  approveCandidate,
  dismissCandidate,
  type EmbeddingCandidate,
} from '@/lib/api';
import PlatformBadge from '@/components/markets/PlatformBadge';
import OddsDisplay from '@/components/markets/OddsDisplay';
import EmptyState from '@/components/shared/EmptyState';
import { cn } from '@/lib/utils/format';
import {
  Check,
  X,
  RefreshCw,
  Loader2,
  Sparkles,
  ExternalLink,
} from 'lucide-react';
import { format } from 'date-fns';

function CandidateCard({
  candidate,
  onApprove,
  onDismiss,
}: {
  candidate: EmbeddingCandidate;
  onApprove: () => void;
  onDismiss: () => void;
}) {
  const [status, setStatus] = useState<'idle' | 'approving' | 'dismissing' | 'done'>('idle');

  const handleApprove = async () => {
    setStatus('approving');
    try {
      await onApprove();
      setStatus('done');
    } catch {
      setStatus('idle');
    }
  };

  const handleDismiss = async () => {
    setStatus('dismissing');
    try {
      await onDismiss();
      setStatus('done');
    } catch {
      setStatus('idle');
    }
  };

  if (status === 'done') return null;

  const similarity = (candidate.tfidf_score * 100).toFixed(0);
  const priceA = Object.values(candidate.market_a_outcome_prices)[0] ?? 0;
  const priceB = Object.values(candidate.market_b_outcome_prices)[0] ?? 0;
  const spread = Math.abs(priceA - priceB);

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 p-4 transition-all hover:border-gray-700">
      {/* Score + spread header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-emerald-900/40 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-400">
            {similarity}% match
          </span>
          {spread > 0.01 && (
            <span className="rounded-full bg-amber-900/40 px-2.5 py-0.5 text-[11px] font-semibold text-amber-400">
              {(spread * 100).toFixed(1)}% spread
            </span>
          )}
        </div>
        {candidate.market_a_end_date && (
          <span className="text-[11px] text-gray-500">
            Expires {format(new Date(candidate.market_a_end_date), 'MMM d, yyyy')}
          </span>
        )}
      </div>

      {/* Side-by-side markets */}
      <div className="mb-3 grid grid-cols-2 gap-3">
        {/* Market A */}
        <div className="space-y-1.5">
          <PlatformBadge platform={candidate.market_a_platform} />
          <p className="text-xs font-medium leading-snug text-gray-200">
            {candidate.market_a_question}
          </p>
          <div className="flex items-center gap-2">
            {Object.entries(candidate.market_a_outcome_prices).slice(0, 2).map(([k, v]) => (
              <span key={k} className="text-[11px] text-gray-400">
                {k}: <OddsDisplay probability={v} size="sm" />
              </span>
            ))}
          </div>
        </div>

        {/* Market B */}
        <div className="space-y-1.5">
          <PlatformBadge platform={candidate.market_b_platform} />
          <p className="text-xs font-medium leading-snug text-gray-200">
            {candidate.market_b_question}
          </p>
          <div className="flex items-center gap-2">
            {Object.entries(candidate.market_b_outcome_prices).slice(0, 2).map(([k, v]) => (
              <span key={k} className="text-[11px] text-gray-400">
                {k}: <OddsDisplay probability={v} size="sm" />
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-end gap-2">
        <button
          onClick={handleDismiss}
          disabled={status !== 'idle'}
          className="flex items-center gap-1 rounded-lg border border-gray-700 px-3 py-1.5 text-xs text-gray-400 transition-colors hover:border-red-700 hover:text-red-400 disabled:opacity-40"
        >
          {status === 'dismissing' ? <Loader2 className="h-3 w-3 animate-spin" /> : <X className="h-3 w-3" />}
          Dismiss
        </button>
        <button
          onClick={handleApprove}
          disabled={status !== 'idle'}
          className="flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-emerald-500 disabled:opacity-40"
        >
          {status === 'approving' ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
          Approve Pair
        </button>
      </div>
    </div>
  );
}

export default function CandidateList() {
  const queryClient = useQueryClient();
  const [genStatus, setGenStatus] = useState<'idle' | 'generating'>('idle');

  const { data, isLoading } = useQuery({
    queryKey: ['candidates'],
    queryFn: getCandidates,
    refetchInterval: genStatus === 'generating' ? 5000 : false,
  });

  const candidates = data?.candidates ?? [];
  const stale = data?.stale ?? true;

  const handleGenerate = useCallback(async () => {
    setGenStatus('generating');
    try {
      await generateCandidates(0.85);
      // Poll until candidates appear
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['candidates'] });
      }, 5000);
      setTimeout(() => {
        setGenStatus('idle');
        queryClient.invalidateQueries({ queryKey: ['candidates'] });
      }, 90000);
    } catch {
      setGenStatus('idle');
    }
  }, [queryClient]);

  const handleApprove = useCallback(
    async (c: EmbeddingCandidate) => {
      await approveCandidate(c.market_a_id, c.market_b_id, c.tfidf_score);
      queryClient.invalidateQueries({ queryKey: ['candidates'] });
      queryClient.invalidateQueries({ queryKey: ['arbitrage'] });
    },
    [queryClient]
  );

  const handleDismiss = useCallback(
    async (c: EmbeddingCandidate) => {
      await dismissCandidate(c.market_a_id, c.market_b_id);
      queryClient.invalidateQueries({ queryKey: ['candidates'] });
    },
    [queryClient]
  );

  return (
    <div className="space-y-4">
      {/* Header with generate button */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-amber-400" />
          <span className="text-sm font-medium text-gray-300">
            Embedding Candidates
          </span>
          {!isLoading && (
            <span className="rounded-full bg-gray-800 px-2 py-0.5 text-[11px] text-gray-400">
              {candidates.length}
            </span>
          )}
        </div>
        <button
          onClick={handleGenerate}
          disabled={genStatus === 'generating'}
          className={cn(
            'flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors',
            genStatus === 'generating'
              ? 'border-amber-700 bg-amber-900/20 text-amber-400'
              : 'border-gray-700 text-gray-400 hover:border-gray-600 hover:text-gray-200'
          )}
        >
          {genStatus === 'generating' ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
          {genStatus === 'generating' ? 'Generating...' : 'Find Candidates'}
        </button>
      </div>

      {stale && candidates.length === 0 && !isLoading && genStatus === 'idle' && (
        <EmptyState
          icon={<Sparkles className="h-10 w-10" />}
          title="No candidates yet"
          description="Click 'Find Candidates' to search for cross-platform matches using semantic embeddings."
        />
      )}

      {genStatus === 'generating' && candidates.length === 0 && (
        <div className="flex flex-col items-center gap-3 py-8">
          <Loader2 className="h-8 w-8 animate-spin text-amber-400" />
          <p className="text-sm text-gray-500">
            Searching 125k markets for semantic matches... (~60 seconds)
          </p>
        </div>
      )}

      {/* Candidate cards */}
      <div className="space-y-3">
        {candidates.map((c) => (
          <CandidateCard
            key={`${c.market_a_id}-${c.market_b_id}`}
            candidate={c}
            onApprove={() => handleApprove(c)}
            onDismiss={() => handleDismiss(c)}
          />
        ))}
      </div>
    </div>
  );
}
