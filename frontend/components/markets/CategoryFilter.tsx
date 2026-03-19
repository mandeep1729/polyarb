'use client';

import { useQueryState } from 'nuqs';
import { cn } from '@/lib/utils/format';

const CATEGORIES = [
  'All',
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

interface CategoryFilterProps {
  className?: string;
}

export default function CategoryFilter({ className }: CategoryFilterProps) {
  const [category, setCategory] = useQueryState('category', {
    defaultValue: 'All',
    shallow: false,
  });

  return (
    <div
      className={cn(
        'flex gap-2 overflow-x-auto pb-2 scrollbar-none',
        className
      )}
    >
      {CATEGORIES.map((cat) => {
        const isActive = category === cat || (cat === 'All' && !category);
        const colorClass =
          isActive && cat !== 'All'
            ? categoryColors[cat] ?? 'bg-gray-800 text-gray-200 border-gray-700'
            : '';

        return (
          <button
            key={cat}
            onClick={() => setCategory(cat === 'All' ? null : cat)}
            className={cn(
              'shrink-0 rounded-full border px-4 py-1.5 text-xs font-medium transition-all',
              isActive
                ? cat === 'All'
                  ? 'border-emerald-600 bg-emerald-900/40 text-emerald-300'
                  : colorClass
                : 'border-gray-800 bg-gray-900 text-gray-400 hover:border-gray-700 hover:text-gray-300',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50'
            )}
          >
            {cat}
          </button>
        );
      })}
    </div>
  );
}
