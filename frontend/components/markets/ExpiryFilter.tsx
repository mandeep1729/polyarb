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
  showExpired?: boolean;
  onShowExpiredChange?: (value: boolean) => void;
  className?: string;
}

export default function ExpiryFilter({ value, onChange, showExpired, onShowExpiredChange, className }: ExpiryFilterProps) {
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

  const hasRange = value.min || value.max;

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
      <div className={cn(
        'inline-flex items-center rounded-md border bg-gray-900',
        hasRange ? 'border-emerald-700' : 'border-gray-700'
      )}>
        <input
          type="date"
          value={value.min}
          max={value.max || undefined}
          onChange={(e) => onChange({ ...value, min: e.target.value })}
          className="w-[7.5rem] border-none bg-transparent px-2 py-1 text-xs text-gray-300 focus:outline-none"
        />
        <span className="text-xs text-gray-600">–</span>
        <input
          type="date"
          value={value.max}
          min={value.min || undefined}
          onChange={(e) => onChange({ ...value, max: e.target.value })}
          className="w-[7.5rem] border-none bg-transparent px-2 py-1 text-xs text-gray-300 focus:outline-none"
        />
        {hasRange && (
          <button
            onClick={() => onChange({ min: '', max: '' })}
            className="px-1.5 text-xs text-gray-500 hover:text-gray-300"
          >
            ×
          </button>
        )}
      </div>
      {onShowExpiredChange != null && (
        <>
          <span className="mx-1 text-gray-600">|</span>
          <label className="flex cursor-pointer items-center gap-1.5">
            <div
              role="switch"
              aria-checked={showExpired}
              onClick={() => onShowExpiredChange(!showExpired)}
              className={cn(
                'relative inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors',
                showExpired ? 'bg-emerald-600' : 'bg-gray-700'
              )}
            >
              <span
                className={cn(
                  'inline-block h-3 w-3 rounded-full bg-white transition-transform',
                  showExpired ? 'translate-x-3.5' : 'translate-x-0.5'
                )}
              />
            </div>
            <span className="text-xs text-gray-400">Show expired</span>
          </label>
        </>
      )}
    </div>
  );
}
