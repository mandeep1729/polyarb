'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils/format';

interface TagCloudProps {
  tags: { term: string; count: number }[];
  activeTags: Set<string>;
  onTagClick: (term: string) => void;
}

const INITIAL_COUNT = 20;

export default function TagCloud({ tags, activeTags, onTagClick }: TagCloudProps) {
  const [expanded, setExpanded] = useState(false);

  if (tags.length === 0) return null;

  const visible = expanded ? tags : tags.slice(0, INITIAL_COUNT);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {visible.map((tag, i) => {
          const isActive = activeTags.has(tag.term);
          const sizeClass =
            i < 5
              ? 'text-sm font-semibold'
              : i < 15
                ? 'text-xs font-medium'
                : 'text-xs font-normal';
          const colorClass =
            i < 5
              ? 'text-gray-200'
              : i < 15
                ? 'text-gray-300'
                : 'text-gray-400';

          return (
            <button
              key={tag.term}
              onClick={() => onTagClick(tag.term)}
              className={cn(
                'rounded-full border px-2.5 py-0.5 transition-colors',
                sizeClass,
                isActive
                  ? 'border-emerald-500 bg-emerald-500/20 text-emerald-400'
                  : cn('border-gray-700 bg-gray-800/60 hover:border-gray-600', colorClass)
              )}
            >
              {tag.term}
            </button>
          );
        })}
      </div>
      {tags.length > INITIAL_COUNT && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-gray-500 hover:text-gray-400"
        >
          {expanded ? 'Show less' : `Show ${tags.length - INITIAL_COUNT} more`}
        </button>
      )}
    </div>
  );
}
