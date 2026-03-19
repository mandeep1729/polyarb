'use client';

import { useState, useEffect } from 'react';
import { useOddsFormat } from '@/lib/contexts/OddsFormatContext';
import { useTheme } from '@/lib/contexts/ThemeContext';
import type { OddsFormat } from '@/lib/types';
import { cn } from '@/lib/utils/format';
import { Sun, Moon, Monitor } from 'lucide-react';

const ODDS_OPTIONS: { value: OddsFormat; label: string; example: string }[] = [
  { value: 'percentage', label: 'Percentage', example: '65.3%' },
  { value: 'decimal', label: 'Decimal', example: '1.53' },
  { value: 'fractional', label: 'Fractional', example: '13/20' },
];

const REFRESH_OPTIONS = [
  { value: 10, label: '10 seconds' },
  { value: 15, label: '15 seconds' },
  { value: 30, label: '30 seconds' },
  { value: 60, label: '1 minute' },
];

export default function SettingsPage() {
  const { oddsFormat, setOddsFormat } = useOddsFormat();
  const { theme, setTheme } = useTheme();
  const [refreshInterval, setRefreshInterval] = useState(15);

  useEffect(() => {
    const stored = localStorage.getItem('refreshInterval');
    if (stored) setRefreshInterval(parseInt(stored, 10));
  }, []);

  const handleRefreshChange = (val: number) => {
    setRefreshInterval(val);
    localStorage.setItem('refreshInterval', val.toString());
  };

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <h1 className="mb-1 text-2xl font-bold text-white">Settings</h1>
        <p className="text-sm text-gray-500">
          Customize your Polyarb experience.
        </p>
      </div>

      {/* Odds Format */}
      <section className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-1 text-sm font-semibold text-gray-200">
          Odds Format
        </h2>
        <p className="mb-4 text-xs text-gray-500">
          Choose how probabilities are displayed across the app.
        </p>
        <div className="space-y-2">
          {ODDS_OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className={cn(
                'flex cursor-pointer items-center justify-between rounded-lg border px-4 py-3 transition-all',
                oddsFormat === opt.value
                  ? 'border-emerald-600 bg-emerald-900/20'
                  : 'border-gray-800 hover:border-gray-700'
              )}
            >
              <div className="flex items-center gap-3">
                <input
                  type="radio"
                  name="oddsFormat"
                  value={opt.value}
                  checked={oddsFormat === opt.value}
                  onChange={() => setOddsFormat(opt.value)}
                  className="h-4 w-4 accent-emerald-500"
                />
                <div>
                  <div className="text-sm font-medium text-gray-200">
                    {opt.label}
                  </div>
                </div>
              </div>
              <span className="rounded-md bg-gray-800 px-2.5 py-1 text-xs font-mono text-gray-300">
                {opt.example}
              </span>
            </label>
          ))}
        </div>
      </section>

      {/* Refresh Interval */}
      <section className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-1 text-sm font-semibold text-gray-200">
          Refresh Interval
        </h2>
        <p className="mb-4 text-xs text-gray-500">
          How often data is automatically refreshed.
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {REFRESH_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => handleRefreshChange(opt.value)}
              className={cn(
                'rounded-lg border px-3 py-2 text-sm font-medium transition-all',
                refreshInterval === opt.value
                  ? 'border-emerald-600 bg-emerald-900/20 text-emerald-400'
                  : 'border-gray-800 text-gray-400 hover:border-gray-700 hover:text-gray-200',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50'
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </section>

      {/* Theme */}
      <section className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-1 text-sm font-semibold text-gray-200">Theme</h2>
        <p className="mb-4 text-xs text-gray-500">
          Toggle between dark and light mode.
        </p>
        <div className="flex gap-2">
          <button
            onClick={() => setTheme('dark')}
            className={cn(
              'flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition-all',
              theme === 'dark'
                ? 'border-emerald-600 bg-emerald-900/20 text-emerald-400'
                : 'border-gray-800 text-gray-400 hover:border-gray-700 hover:text-gray-200',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50'
            )}
          >
            <Moon className="h-4 w-4" /> Dark
          </button>
          <button
            onClick={() => setTheme('light')}
            className={cn(
              'flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition-all',
              theme === 'light'
                ? 'border-emerald-600 bg-emerald-900/20 text-emerald-400'
                : 'border-gray-800 text-gray-400 hover:border-gray-700 hover:text-gray-200',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50'
            )}
          >
            <Sun className="h-4 w-4" /> Light
          </button>
        </div>
      </section>

      {/* About */}
      <section className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-1 text-sm font-semibold text-gray-200">About</h2>
        <p className="text-xs leading-relaxed text-gray-500">
          Polyarb aggregates prediction markets from Polymarket and Kalshi,
          detecting arbitrage opportunities in real-time. Data refreshes
          automatically and prices are sourced directly from each platform.
        </p>
        <div className="mt-3 text-xs text-gray-600">Version 0.1.0</div>
      </section>
    </div>
  );
}
