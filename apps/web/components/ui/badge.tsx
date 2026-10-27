import * as React from 'react';
import { cn } from '@/lib/utils';

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'primary' | 'sand' | 'secondary' | 'cyan' | 'success' | 'warning' | 'danger' | 'outline';
}

export function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  const variants = {
    default: 'bg-[var(--surface-hover)] text-[var(--foreground-muted)] border-[var(--border)]',
    secondary: 'bg-[var(--surface)] text-[var(--foreground-muted)] border-[var(--border)]',
    primary: 'bg-stone-800 text-stone-200 dark:bg-stone-200 dark:text-stone-900 border-stone-700/50',
    sand: 'bg-[#d4c3b3]/15 text-[#d4c3b3] dark:text-[#e5d7c9] border-[#d4c3b3]/30',
    cyan: 'bg-sky-500/15 text-sky-400 dark:text-sky-300 border-sky-500/30',
    success: 'bg-emerald-500/15 text-emerald-500 dark:text-emerald-400 border-emerald-500/30',
    warning: 'bg-amber-500/15 text-amber-500 dark:text-amber-400 border-amber-500/30',
    danger: 'bg-rose-500/15 text-rose-500 dark:text-rose-400 border-rose-500/30',
    outline: 'bg-transparent text-[var(--foreground-muted)] border-[var(--border)]',
  };

  return (
    <div
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border transition-colors',
        variants[variant],
        className
      )}
      {...props}
    />
  );
}
