'use client';

import { cn } from '@/lib/utils/format';
import { Clock } from 'lucide-react';

const EXPIRY_OPTIONS = [
  { value: '', label: 'Any expiry' },
  { value: '1', label: 'Today' },
  { value: '7', label: 'This week' },
  { value: '30', label: 'This month' },
  { value: '90', label: '3 months' },
  { value: '365', label: '1 year' },
];

interface ExpiryFilterProps {
  value: string;
  onChange: (value: string) => void;
  className?: string;
}

export default function ExpiryFilter({ value, onChange, className }: ExpiryFilterProps) {
  return (
    <div className={cn('relative inline-flex items-center', className)}>
      <Clock className="pointer-events-none absolute left-3 h-3.5 w-3.5 text-gray-500" />
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="appearance-none rounded-lg border border-gray-800 bg-gray-900 py-2 pl-9 pr-8 text-sm text-gray-200 transition-colors focus:border-gray-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50"
      >
        {EXPIRY_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
