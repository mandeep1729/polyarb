'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Layers,
  BarChart3,
  GitCompareArrows,
  Settings,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { cn } from '@/lib/utils/format';

const NAV_ITEMS = [
  { href: '/', label: 'Groups', icon: Layers },
  { href: '/markets', label: 'Markets', icon: BarChart3 },
  { href: '/arbitrage', label: 'Arbitrage', icon: GitCompareArrows },
  { href: '/settings', label: 'Settings', icon: Settings },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside
      className={cn(
        'fixed left-0 top-14 z-30 hidden h-[calc(100vh-3.5rem)] border-r border-gray-800 bg-gray-950 transition-all duration-200 md:block',
        collapsed ? 'w-16' : 'w-52'
      )}
    >
      <nav className="flex flex-col gap-1 p-2">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive =
            item.href === '/'
              ? pathname === '/'
              : pathname.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-emerald-900/30 text-emerald-400'
                  : 'text-gray-400 hover:bg-gray-800/50 hover:text-gray-200',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50'
              )}
              title={collapsed ? item.label : undefined}
            >
              <Icon className="h-5 w-5 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      <button
        onClick={onToggle}
        className="absolute -right-3 top-6 flex h-6 w-6 items-center justify-center rounded-full border border-gray-800 bg-gray-900 text-gray-400 transition-colors hover:text-gray-200"
      >
        {collapsed ? (
          <ChevronRight className="h-3 w-3" />
        ) : (
          <ChevronLeft className="h-3 w-3" />
        )}
      </button>
    </aside>
  );
}
