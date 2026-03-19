'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Sun, Moon } from 'lucide-react';
import { useOddsFormat } from '@/lib/contexts/OddsFormatContext';
import { useTheme } from '@/lib/contexts/ThemeContext';
import type { OddsFormat } from '@/lib/types';
import SearchInput from '@/components/markets/SearchInput';
import RefreshIndicator from '@/components/shared/RefreshIndicator';
import { cn } from '@/lib/utils/format';
import Link from 'next/link';

const FORMAT_OPTIONS: { value: OddsFormat; label: string }[] = [
  { value: 'percentage', label: '%' },
  { value: 'decimal', label: 'D' },
  { value: 'fractional', label: 'F' },
];

export default function TopBar() {
  const router = useRouter();
  const { oddsFormat, setOddsFormat } = useOddsFormat();
  const { theme, toggleTheme } = useTheme();
  const [searchValue, setSearchValue] = useState('');

  const handleSearch = (q: string) => {
    if (q.trim()) {
      router.push(`/markets?q=${encodeURIComponent(q.trim())}`);
    }
  };

  return (
    <header className="fixed left-0 right-0 top-0 z-40 flex h-14 items-center border-b border-gray-800 bg-gray-950/95 px-4 backdrop-blur-sm">
      {/* Logo */}
      <Link
        href="/"
        className="mr-4 flex shrink-0 items-center gap-2 text-lg font-bold text-white"
      >
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-600 text-xs font-black">
          P
        </div>
        <span className="hidden sm:inline">Polyarb</span>
      </Link>

      {/* Search */}
      <div className="mx-4 max-w-md flex-1">
        <SearchInput
          value={searchValue}
          onChange={setSearchValue}
          onSubmit={handleSearch}
          placeholder="Search markets..."
          className="w-full"
        />
      </div>

      <div className="flex items-center gap-2">
        {/* Odds format toggle */}
        <div className="flex overflow-hidden rounded-lg border border-gray-800">
          {FORMAT_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setOddsFormat(opt.value)}
              className={cn(
                'px-2.5 py-1.5 text-xs font-medium transition-colors',
                oddsFormat === opt.value
                  ? 'bg-emerald-600 text-white'
                  : 'bg-gray-900 text-gray-400 hover:text-gray-200',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50'
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          className="rounded-lg p-2 text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50"
        >
          {theme === 'dark' ? (
            <Sun className="h-4 w-4" />
          ) : (
            <Moon className="h-4 w-4" />
          )}
        </button>

        <RefreshIndicator />
      </div>
    </header>
  );
}
