'use client';

import * as React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Home,
  FileText,
  Folder,
  MessageSquare,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
  MoreHorizontal,
  LogOut,
  User
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useSession, signOut } from 'next-auth/react';
import { BrandLogo } from '@/components/ui/brand-logo';
import { getUserInitial } from '@/lib/avatar';

interface SidebarProps {
  isCollapsed: boolean;
  setIsCollapsed: (val: boolean) => void;
  isMobileOpen?: boolean;
  setIsMobileOpen?: (val: boolean) => void;
}

const navItems = [
  { name: 'Dashboard', href: '/dashboard', icon: Home },
  { name: 'Content Library', href: '/library', icon: FileText },
  { name: 'Collections', href: '/collections', icon: Folder },
  { name: 'Chat', href: '/chat', icon: MessageSquare },
  { name: 'Settings', href: '/settings', icon: Settings },
];

export function Sidebar({ isCollapsed, setIsCollapsed, isMobileOpen, setIsMobileOpen }: SidebarProps) {
  const pathname = usePathname();
  const { data: session } = useSession();
  const [isUserMenuOpen, setIsUserMenuOpen] = React.useState(false);
  const userMenuRef = React.useRef<HTMLDivElement>(null);

  const user = session?.user;
  const displayName = user?.name || (user?.email ? user.email.split('@')[0] : 'User');
  const displayEmail = user?.email || 'user@evermind.io';
  const initial = getUserInitial(user?.name, user?.email, 'U');

  React.useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setIsUserMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLinkClick = () => {
    if (setIsMobileOpen) setIsMobileOpen(false);
  };

  return (
    <>
      {/* Mobile Backdrop */}
      {isMobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/70 backdrop-blur-xs lg:hidden"
          onClick={() => setIsMobileOpen && setIsMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={cn(
          'fixed lg:sticky top-0 left-0 z-40 h-screen border-r border-[var(--border)] bg-[var(--surface-base)] flex flex-col justify-between transition-all duration-300 ease-in-out shrink-0 select-none',
          isCollapsed ? 'w-20' : 'w-64',
          isMobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        )}
      >
        {/* Top Header / Brand */}
        <div>
          {isCollapsed ? (
            /* Collapsed Header: Vertical stack with centered brand mark and expand button */
            <div className="py-3.5 px-2 flex flex-col items-center justify-center gap-2.5 border-b border-[var(--border-subtle)]">
              <BrandLogo
                href="/dashboard"
                onClick={handleLinkClick}
                showWordmark={false}
                size="md"
                title="Evermind Dashboard"
              />

              <button
                type="button"
                onClick={() => setIsCollapsed(false)}
                aria-label="Expand sidebar"
                title="Expand sidebar"
                className="hidden lg:flex p-1.5 rounded-md text-[var(--foreground-muted)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)] transition-colors cursor-pointer shrink-0 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--foreground)]"
              >
                <PanelLeftOpen className="h-4 w-4" />
              </button>
            </div>
          ) : (
            /* Expanded Header: Horizontal row with brand mark, title, and collapse button */
            <div className="h-16 flex items-center justify-between px-4 border-b border-[var(--border-subtle)]">
              <BrandLogo
                href="/"
                onClick={handleLinkClick}
                showWordmark={true}
                size="md"
                title="Evermind Dashboard"
              />

              <button
                type="button"
                onClick={() => setIsCollapsed(true)}
                aria-label="Collapse sidebar"
                title="Collapse sidebar"
                className="hidden lg:flex p-1.5 rounded-md text-[var(--foreground-muted)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)] transition-colors cursor-pointer shrink-0 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--foreground)]"
              >
                <PanelLeftClose className="h-4 w-4" />
              </button>
            </div>
          )}

          {/* Navigation Links */}
          <nav className="px-3 py-2 space-y-1" aria-label="Main Navigation">
            {navItems.map((item) => {
              const isActive =
                item.href === '/dashboard'
                  ? pathname === '/dashboard'
                  : pathname === item.href || pathname.startsWith(item.href + '/');
              const Icon = item.icon;

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={handleLinkClick}
                  className={cn(
                    'flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-normal transition-all group relative',
                    isCollapsed && 'justify-center px-0',
                    isActive
                      ? 'bg-[var(--surface-hover)] text-[var(--foreground)] font-medium shadow-2xs'
                      : 'text-[var(--foreground-muted)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)]'
                  )}
                  title={isCollapsed ? item.name : undefined}
                  aria-label={item.name}
                >
                  {/* Left indicator bar for active item */}
                  {isActive && (
                    <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4 bg-[var(--foreground)] rounded-r-full" />
                  )}

                  <Icon
                    className={cn(
                      'h-4 w-4 shrink-0 transition-colors stroke-[1.75]',
                      isActive ? 'text-[var(--foreground)]' : 'text-[var(--foreground-muted)] group-hover:text-[var(--foreground)]'
                    )}
                  />

                  {!isCollapsed && (
                    <span className="truncate">{item.name}</span>
                  )}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Bottom Section: User Profile */}
        <div className="p-3">
          {/* User Profile */}
          <div className="relative" ref={userMenuRef}>
            <button
              onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
              className={cn(
                'w-full flex items-center justify-between p-2 rounded-xl hover:bg-[var(--surface-hover)] transition-colors text-left cursor-pointer group',
                isCollapsed && 'justify-center p-1.5'
              )}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="h-8 w-8 rounded-full bg-[var(--accent-sand)] text-[#141518] flex items-center justify-center text-xs font-semibold shrink-0 overflow-hidden">
                  {user?.image ? (
                    <img src={user.image} alt={displayName} className="h-full w-full object-cover" />
                  ) : (
                    initial
                  )}
                </div>
                {!isCollapsed && (
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-[var(--foreground)] truncate group-hover:opacity-85">
                      {displayName}
                    </p>
                    <p className="text-xs text-[var(--foreground-muted)] truncate">
                      Personal workspace
                    </p>
                  </div>
                )}
              </div>

              {!isCollapsed && (
                <MoreHorizontal className="h-4 w-4 text-[var(--foreground-muted)] group-hover:text-[var(--foreground)] shrink-0" />
              )}
            </button>

            {/* User Dropdown Menu */}
            {isUserMenuOpen && (
              <div className="absolute bottom-full left-0 mb-2 w-56 rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-2 shadow-2xl z-50 animate-in fade-in zoom-in-95 duration-150">
                <div className="px-3 py-2 border-b border-[var(--border)] mb-1">
                  <p className="text-xs font-semibold text-[var(--foreground)]">{displayName}</p>
                  <p className="text-xs text-[var(--foreground-muted)] truncate">{displayEmail}</p>
                </div>
                <Link
                  href="/settings"
                  onClick={() => setIsUserMenuOpen(false)}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-[var(--foreground-muted)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)] transition-colors"
                >
                  <Settings className="h-3.5 w-3.5" />
                  Settings & Preferences
                </Link>
                {session ? (
                  <button
                    onClick={() => {
                      setIsUserMenuOpen(false);
                      signOut({ callbackUrl: '/' });
                    }}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-rose-500 hover:bg-rose-500/10 transition-colors text-left cursor-pointer"
                  >
                    <LogOut className="h-3.5 w-3.5" />
                    Sign Out
                  </button>
                ) : (
                  <Link
                    href="/login"
                    onClick={() => setIsUserMenuOpen(false)}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-[var(--foreground-muted)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)] transition-colors"
                  >
                    <User className="h-3.5 w-3.5" />
                    Sign In
                  </Link>
                )}
              </div>
            )}
          </div>
        </div>
      </aside>
    </>
  );
}
