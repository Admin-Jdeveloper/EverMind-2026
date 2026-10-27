'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  Menu,
  Search,
  Plus,
  User,
  LogOut,
  Settings,
  Sparkles,
  Command,
  Sun,
  Moon,
  Activity,
  CheckCircle2
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useSession, signOut } from 'next-auth/react';
import { useTheme } from '@/components/theme-provider';

interface HeaderProps {
  onOpenMobileNav: () => void;
  onOpenQuickAdd: () => void;
}

export function Header({ onOpenMobileNav, onOpenQuickAdd }: HeaderProps) {
  const router = useRouter();
  const { data: session } = useSession();
  const { theme, toggleTheme } = useTheme();
  const [isUserMenuOpen, setIsUserMenuOpen] = React.useState(false);
  const [healthStatus, setHealthStatus] = React.useState<'online' | 'checking' | 'offline'>('checking');
  const userMenuRef = React.useRef<HTMLDivElement>(null);

  const user = session?.user;
  const displayName = user?.name || (user?.email ? user.email.split('@')[0] : 'Guest');
  const displayEmail = user?.email || 'Not signed in';
  const initials = displayName
    .split(' ')
    .filter(Boolean)
    .map((part: string) => part[0])
    .join('')
    .toUpperCase()
    .slice(0, 2) || displayName.slice(0, 2).toUpperCase() || 'G';

  // Close dropdown on click outside
  React.useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setIsUserMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Check backend health status
  React.useEffect(() => {
    async function checkHealth() {
      try {
        const res = await fetch('/api/health');
        if (res.ok) setHealthStatus('online');
        else setHealthStatus('offline');
      } catch {
        setHealthStatus('offline');
      }
    }
    checkHealth();
  }, []);

  return (
    <header className="sticky top-0 z-30 h-16 w-full border-b border-[var(--border)] bg-[var(--background)]/80 backdrop-blur-xl px-4 lg:px-8 flex items-center justify-between gap-4 transition-colors">
      {/* Left: Mobile hamburger & search trigger */}
      <div className="flex items-center gap-3 flex-1 max-w-md">
        <button
          onClick={onOpenMobileNav}
          aria-label="Open mobile navigation"
          className="lg:hidden p-2 rounded-xl text-[var(--foreground-muted)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)] transition-colors"
        >
          <Menu className="h-5 w-5" />
        </button>

        <Link
          href="/library"
          className="w-full flex items-center justify-between px-3.5 py-2 rounded-xl bg-[var(--surface)] border border-[var(--border)] text-xs sm:text-sm text-[var(--foreground-muted)] hover:border-[var(--border-hover)] hover:text-[var(--foreground)] transition-all shadow-2xs group"
        >
          <span className="flex items-center gap-2.5">
            <Search className="h-4 w-4 text-[var(--foreground-muted)] group-hover:text-[var(--accent-sand)] transition-colors" />
            <span className="hidden sm:inline">Search library, notes, documents...</span>
            <span className="sm:hidden">Search library...</span>
          </span>
          <kbd className="hidden sm:inline-flex items-center gap-1 rounded-md bg-[var(--surface-elevated)] px-1.5 py-0.5 text-xs font-mono text-[var(--foreground-muted)] border border-[var(--border)]">
            <Command className="h-3 w-3" /> K
          </kbd>
        </Link>
      </div>

      {/* Right: Actions, System Health & User Profile */}
      <div className="flex items-center gap-2.5 sm:gap-3">
        {/* Backend health pill */}
        <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[var(--surface)] border border-[var(--border)] text-xs">
          <span
            className={`h-2 w-2 rounded-full ${
              healthStatus === 'online'
                ? 'bg-emerald-500 shadow-xs shadow-emerald-500/50 animate-pulse'
                : healthStatus === 'checking'
                ? 'bg-amber-400 animate-pulse'
                : 'bg-rose-500'
            }`}
          />
          <span className="text-[var(--foreground-muted)] text-[11px] font-medium">
            {healthStatus === 'online' ? 'Engine Ready' : healthStatus === 'checking' ? 'Connecting...' : 'Offline'}
          </span>
        </div>

        {/* Theme Toggle Button */}
        <button
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          className="p-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] text-[var(--foreground-muted)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)] transition-all"
        >
          {theme === 'dark' ? (
            <Sun className="h-4 w-4 text-amber-300" />
          ) : (
            <Moon className="h-4 w-4 text-stone-700" />
          )}
        </button>

        {/* Quick Add Content Button */}
        <Button
          onClick={onOpenQuickAdd}
          variant="primary"
          size="sm"
          className="shadow-xs"
        >
          <Plus className="h-4 w-4" />
          <span className="hidden sm:inline">Add Content</span>
        </Button>

        {/* User Profile Dropdown */}
        <div className="relative" ref={userMenuRef}>
          <button
            onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
            aria-label="User profile menu"
            aria-expanded={isUserMenuOpen}
            className="flex items-center gap-2.5 p-0.5 rounded-full hover:ring-2 hover:ring-[var(--accent-sand)]/40 transition-all cursor-pointer"
          >
            <div className="h-8 w-8 rounded-full bg-gradient-to-tr from-[#1b1f2b] to-[#2c3245] dark:from-stone-800 dark:to-stone-700 border border-[var(--border)] flex items-center justify-center text-xs font-semibold text-white shadow-xs">
              {initials}
            </div>
          </button>

          {/* Flyout menu */}
          {isUserMenuOpen && (
            <div
              className="absolute right-0 mt-2 w-56 rounded-2xl border border-[var(--border)] bg-[var(--surface-elevated)] p-2 shadow-xl z-50 animate-in fade-in zoom-in-95 duration-150"
              role="menu"
            >
              <div className="px-3 py-2 border-b border-[var(--border)] mb-1">
                <p className="text-sm font-semibold text-[var(--foreground)]">{displayName}</p>
                <p className="text-xs text-[var(--foreground-muted)] truncate">{displayEmail}</p>
                <Badge variant="sand" className="mt-1.5 text-xs">
                  Personal Library
                </Badge>
              </div>

              <Link
                href="/settings"
                onClick={() => setIsUserMenuOpen(false)}
                className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs sm:text-sm text-[var(--foreground-muted)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)] transition-colors"
                role="menuitem"
              >
                <Settings className="h-4 w-4" />
                Settings & Preferences
              </Link>

              <Link
                href="/chat"
                onClick={() => setIsUserMenuOpen(false)}
                className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs sm:text-sm text-[var(--foreground-muted)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)] transition-colors"
                role="menuitem"
              >
                <Sparkles className="h-4 w-4 text-sky-400" />
                Grounded Assistant
              </Link>

              <div className="my-1 border-t border-[var(--border)]" />

              {session ? (
                <button
                  onClick={() => {
                    setIsUserMenuOpen(false);
                    signOut({ callbackUrl: '/' });
                  }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs sm:text-sm text-rose-500 hover:bg-rose-500/10 transition-colors cursor-pointer"
                  role="menuitem"
                >
                  <LogOut className="h-4 w-4" />
                  Sign Out
                </button>
              ) : (
                <Link
                  href="/login"
                  onClick={() => setIsUserMenuOpen(false)}
                  className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs sm:text-sm text-[var(--accent-sand)] hover:bg-[var(--surface-hover)] transition-colors"
                  role="menuitem"
                >
                  <User className="h-4 w-4" />
                  Sign In
                </Link>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
