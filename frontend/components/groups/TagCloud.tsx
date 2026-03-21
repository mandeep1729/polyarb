'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils/format';

const CATEGORIES = [
  'Politics',
  'Crypto',
  'Sports',
  'Finance',
  'Entertainment',
  'Science',
  'Weather',
];

const categoryColors: Record<string, string> = {
  Politics: 'bg-blue-900/50 text-blue-300 border-blue-700/40',
  Crypto: 'bg-orange-900/50 text-orange-300 border-orange-700/40',
  Sports: 'bg-green-900/50 text-green-300 border-green-700/40',
  Finance: 'bg-emerald-900/50 text-emerald-300 border-emerald-700/40',
  Entertainment: 'bg-pink-900/50 text-pink-300 border-pink-700/40',
  Science: 'bg-cyan-900/50 text-cyan-300 border-cyan-700/40',
  Weather: 'bg-sky-900/50 text-sky-300 border-sky-700/40',
};

const INITIAL_COUNT = 20;

/* ---------- Tag rendering shared by both components ---------- */

function TagPills({
  tags,
  expanded,
  includedTags,
  excludedTags,
  onTagInclude,
  onTagExclude,
}: {
  tags: { term: string; count: number }[];
  expanded: boolean;
  includedTags: Set<string>;
  excludedTags?: Set<string>;
  onTagInclude: (term: string) => void;
  onTagExclude?: (term: string) => void;
}) {
  const visible = expanded ? tags : tags.slice(0, INITIAL_COUNT);

  return (
    <>
      {visible.map((tag, i) => {
        const isIncluded = includedTags.has(tag.term);
        const isExcluded = excludedTags?.has(tag.term) ?? false;
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
            onClick={() => onTagInclude(tag.term)}
            onContextMenu={onTagExclude ? (e) => {
              e.preventDefault();
              onTagExclude(tag.term);
            } : undefined}
            className={cn(
              'rounded-full border px-2.5 py-0.5 transition-colors',
              sizeClass,
              isExcluded
                ? 'border-red-500/50 bg-red-900/20 text-red-400 line-through'
                : isIncluded
                  ? 'border-emerald-500 bg-emerald-500/20 text-emerald-400'
                  : cn('border-gray-700 bg-gray-800/60 hover:border-gray-600', colorClass)
            )}
          >
            {tag.term}
          </button>
        );
      })}
    </>
  );
}

/* ---------- TagBar: unified categories + tags (markets page) ---------- */

interface TagBarProps {
  categoryCounts?: Record<string, number>;
  activeCategory: string | null;
  onCategoryClick: (name: string | null) => void;
  tags: { term: string; count: number }[];
  includedTags: Set<string>;
  excludedTags: Set<string>;
  onTagInclude: (term: string) => void;
  onTagExclude: (term: string) => void;
}

export default function TagBar({
  categoryCounts,
  activeCategory,
  onCategoryClick,
  tags,
  includedTags,
  excludedTags,
  onTagInclude,
  onTagExclude,
}: TagBarProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {/* Category pills */}
        {CATEGORIES.map((cat) => {
          const isActive = activeCategory === cat;
          const count = categoryCounts?.[cat];
          return (
            <button
              key={cat}
              onClick={() => onCategoryClick(isActive ? null : cat)}
              className={cn(
                'shrink-0 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors',
                isActive
                  ? categoryColors[cat]
                  : 'border-gray-800 bg-gray-900 text-gray-400 hover:border-gray-700 hover:text-gray-300'
              )}
            >
              {cat}
              {count != null && count > 0 && (
                <span className="ml-1 text-[10px] opacity-70">
                  {count.toLocaleString()}
                </span>
              )}
            </button>
          );
        })}

        {/* Separator */}
        {tags.length > 0 && (
          <span className="mx-0.5 text-gray-700">|</span>
        )}

        {/* Dynamic tags */}
        <TagPills
          tags={tags}
          expanded={expanded}
          includedTags={includedTags}
          excludedTags={excludedTags}
          onTagInclude={onTagInclude}
          onTagExclude={onTagExclude}
        />
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

/* ---------- TagCloud: tags-only (home/groups page, backward compat) ---------- */

interface TagCloudProps {
  tags: { term: string; count: number }[];
  activeTags: Set<string>;
  onTagClick: (term: string) => void;
}

export function TagCloud({ tags, activeTags, onTagClick }: TagCloudProps) {
  const [expanded, setExpanded] = useState(false);

  if (tags.length === 0) return null;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        <TagPills
          tags={tags}
          expanded={expanded}
          includedTags={activeTags}
          onTagInclude={onTagClick}
        />
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
