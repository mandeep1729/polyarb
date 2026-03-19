'use client';

import { cn } from '@/lib/utils/format';

const PLATFORMS = [
  { slug: 'all', label: 'All Platforms' },
  { slug: 'polymarket', label: 'Polymarket' },
  { slug: 'kalshi', label: 'Kalshi' },
];

const platformColors: Record<string, string> = {
  polymarket: 'border-purple-600 bg-purple-900/40 text-purple-300',
  kalshi: 'border-blue-600 bg-blue-900/40 text-blue-300',
};

interface PlatformFilterProps {
  value?: string;
  onChange: (platform: string | undefined) => void;
  className?: string;
}

export default function PlatformFilter({ value, onChange, className }: PlatformFilterProps) {
  return (
    <div className={cn('flex gap-2', className)}>
      {PLATFORMS.map(({ slug, label }) => {
        const isActive = slug === 'all' ? !value : value === slug;

        return (
          <button
            key={slug}
            onClick={() => onChange(slug === 'all' ? undefined : slug)}
            className={cn(
              'shrink-0 rounded-full border px-4 py-1.5 text-xs font-medium transition-all',
              isActive
                ? slug === 'all'
                  ? 'border-emerald-600 bg-emerald-900/40 text-emerald-300'
                  : platformColors[slug] ?? 'border-gray-700 bg-gray-800 text-gray-200'
                : 'border-gray-800 bg-gray-900 text-gray-400 hover:border-gray-700 hover:text-gray-300',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50'
            )}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
