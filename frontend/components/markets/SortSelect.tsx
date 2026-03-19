'use client';

import { useQueryState } from 'nuqs';
import { cn } from '@/lib/utils/format';
import { ArrowUpDown } from 'lucide-react';

const SORT_OPTIONS = [
  { value: 'volume_24h', label: 'Volume (24h)' },
  { value: 'ending_soon', label: 'Ending Soon' },
  { value: 'newest', label: 'Newest' },
  { value: 'price_change', label: 'Price Change' },
];

interface SortSelectProps {
  className?: string;
}

export default function SortSelect({ className }: SortSelectProps) {
  const [sort, setSort] = useQueryState('sort', {
    defaultValue: 'volume_24h',
    shallow: false,
  });

  return (
    <div className={cn('relative inline-flex items-center', className)}>
      <ArrowUpDown className="pointer-events-none absolute left-3 h-3.5 w-3.5 text-gray-500" />
      <select
        value={sort ?? 'volume_24h'}
        onChange={(e) => setSort(e.target.value)}
        className="appearance-none rounded-lg border border-gray-800 bg-gray-900 py-2 pl-9 pr-8 text-sm text-gray-200 transition-colors focus:border-gray-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50"
      >
        {SORT_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
