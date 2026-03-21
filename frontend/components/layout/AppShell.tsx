'use client';

import { useState } from 'react';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import TopBar from './TopBar';
import Sidebar from './Sidebar';
import {
  Layers,
  BarChart3,
  GitCompareArrows,
  Link2,
  Settings,
} from 'lucide-react';
import { cn } from '@/lib/utils/format';

const MOBILE_NAV = [
  { href: '/', label: 'Groups', icon: Layers },
  { href: '/markets', label: 'Markets', icon: BarChart3 },
  { href: '/arbitrage', label: 'Arb', icon: GitCompareArrows },
  { href: '/matches', label: 'Matches', icon: Link2 },
  { href: '/settings', label: 'Settings', icon: Settings },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <TopBar />
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((c) => !c)}
      />

      {/* Main content */}
      <main
        className={cn(
          'min-h-[calc(100vh-3.5rem)] pt-14 pb-20 transition-all duration-200 md:pb-0',
          sidebarCollapsed ? 'md:pl-16' : 'md:pl-52'
        )}
      >
        {pathname === '/markets' ? (
          children
        ) : (
          <div className="mx-auto max-w-7xl px-4 py-6">{children}</div>
        )}
      </main>

      {/* Mobile bottom nav */}
      <nav className="fixed bottom-0 left-0 right-0 z-40 flex border-t border-gray-800 bg-gray-950/95 backdrop-blur-sm md:hidden">
        {MOBILE_NAV.map((item) => {
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
                'flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] font-medium transition-colors',
                isActive
                  ? 'text-emerald-400'
                  : 'text-gray-500 hover:text-gray-300'
              )}
            >
              <Icon className="h-5 w-5" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
