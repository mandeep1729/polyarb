'use client';

import { useMemo } from 'react';
import { cn } from '@/lib/utils/format';
import { Calendar } from 'lucide-react';

export interface DateRange {
  min: string; // YYYY-MM-DD or ''
  max: string; // YYYY-MM-DD or ''
}

function monthLabel(offset: number): string {
  const d = new Date();
  d.setMonth(d.getMonth() + offset);
  return d.toLocaleString('default', { month: 'short', year: 'numeric' });
}

function monthRange(offset: number): DateRange {
  const d = new Date();
  d.setMonth(d.getMonth() + offset);
  const year = d.getFullYear();
  const month = d.getMonth();
  const first = new Date(year, month, 1);
  const last = new Date(year, month + 1, 0);
  return {
    min: fmt(first),
    max: fmt(last),
  };
}

function fmt(d: Date): string {
  return d.toISOString().slice(0, 10);
}

interface ExpiryFilterProps {
  value: DateRange;
  onChange: (value: DateRange) => void;
  className?: string;
}

export default function ExpiryFilter({ value, onChange, className }: ExpiryFilterProps) {
  const months = useMemo(
    () => Array.from({ length: 6 }, (_, i) => ({
      label: monthLabel(i),
      range: monthRange(i),
    })),
    []
  );

  const activeMonth = months.findIndex(
    (m) => m.range.min === value.min && m.range.max === value.max
  );

  const handleMonthClick = (idx: number) => {
    if (idx === activeMonth) {
      onChange({ min: '', max: '' });
    } else {
      onChange(months[idx].range);
    }
  };

  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      <Calendar className="h-3.5 w-3.5 shrink-0 text-gray-500" />
      {months.map((m, i) => (
        <button
          key={m.label}
          onClick={() => handleMonthClick(i)}
          className={cn(
            'rounded-md border px-2.5 py-1 text-xs font-medium transition-colors',
            i === activeMonth
              ? 'border-emerald-600 bg-emerald-900/40 text-emerald-400'
              : 'border-gray-700 bg-gray-900 text-gray-400 hover:border-gray-600 hover:text-gray-300'
          )}
        >
          {m.label}
        </button>
      ))}
      <span className="mx-1 text-gray-600">|</span>
      <input
        type="date"
        value={value.min}
        onChange={(e) => onChange({ ...value, min: e.target.value })}
        className="rounded-md border border-gray-700 bg-gray-900 px-2 py-1 text-xs text-gray-300 focus:border-gray-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50"
      />
      <span className="text-xs text-gray-500">to</span>
      <input
        type="date"
        value={value.max}
        onChange={(e) => onChange({ ...value, max: e.target.value })}
        className="rounded-md border border-gray-700 bg-gray-900 px-2 py-1 text-xs text-gray-300 focus:border-gray-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50"
      />
      {(value.min || value.max) && (
        <button
          onClick={() => onChange({ min: '', max: '' })}
          className="rounded-md px-1.5 py-1 text-xs text-gray-500 hover:text-gray-300"
        >
          Clear
        </button>
      )}
    </div>
  );
}
