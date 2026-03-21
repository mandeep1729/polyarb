'use client';

import { useState } from 'react';
import type { Market } from '@/lib/types';
import { createManualPair } from '@/lib/api';
import PlatformBadge from './PlatformBadge';
import { cn } from '@/lib/utils/format';
import { X, Link2, Loader2, Check } from 'lucide-react';

interface PairBarProps {
  selections: Market[];
  onRemove: (id: number) => void;
  onClear: () => void;
  onPaired: () => void;
}

export default function PairBar({ selections, onRemove, onClear, onPaired }: PairBarProps) {
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [errorMsg, setErrorMsg] = useState('');

  const canPair = selections.length === 2
    && selections[0].platform_name !== selections[1].platform_name;

  const samePlatform = selections.length === 2
    && selections[0].platform_name === selections[1].platform_name;

  const handlePair = async () => {
    if (!canPair) return;
    setStatus('loading');
    setErrorMsg('');
    try {
      await createManualPair(selections[0].id, selections[1].id);
      setStatus('success');
      setTimeout(() => {
        onPaired();
        setStatus('idle');
      }, 1500);
    } catch (err: unknown) {
      setStatus('error');
      const msg = err instanceof Error ? err.message : 'Failed to create pair';
      setErrorMsg(msg);
      setTimeout(() => setStatus('idle'), 3000);
    }
  };

  if (selections.length === 0) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-gray-800 bg-gray-900/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-3">
        <Link2 className="h-4 w-4 shrink-0 text-amber-400" />
        <span className="shrink-0 text-xs font-medium text-amber-400">
          Pair mode
        </span>

        {/* Selection slots */}
        <div className="flex flex-1 items-center gap-2">
          {selections.map((m) => (
            <div
              key={m.id}
              className="flex items-center gap-2 rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5"
            >
              <PlatformBadge platform={m.platform_name} />
              <span className="max-w-[200px] truncate text-xs text-gray-200">
                {m.question}
              </span>
              <button
                onClick={() => onRemove(m.id)}
                className="text-gray-500 hover:text-gray-300"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
          {selections.length < 2 && (
            <span className="text-xs text-gray-600">
              Select {2 - selections.length} more market{selections.length === 0 ? 's' : ''}
            </span>
          )}
        </div>

        {samePlatform && (
          <span className="text-xs text-red-400">Must be different platforms</span>
        )}

        {errorMsg && (
          <span className="text-xs text-red-400">{errorMsg}</span>
        )}

        <button
          onClick={onClear}
          className="text-xs text-gray-500 hover:text-gray-300"
        >
          Cancel
        </button>

        <button
          onClick={handlePair}
          disabled={!canPair || status === 'loading'}
          className={cn(
            'flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-40',
            status === 'success'
              ? 'bg-emerald-600 text-white'
              : status === 'error'
                ? 'bg-red-600 text-white'
                : 'bg-amber-600 text-white hover:bg-amber-500'
          )}
        >
          {status === 'loading' ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : status === 'success' ? (
            <Check className="h-3.5 w-3.5" />
          ) : (
            <Link2 className="h-3.5 w-3.5" />
          )}
          {status === 'success' ? 'Paired!' : status === 'error' ? 'Failed' : 'Create Pair'}
        </button>
      </div>
    </div>
  );
}
