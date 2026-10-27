import * as React from 'react';
import { cn } from '@/lib/utils';
import { Loader2 } from 'lucide-react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'sand' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg' | 'icon';
  isLoading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', isLoading = false, children, disabled, ...props }, ref) => {
    const baseStyles = 'inline-flex items-center justify-center font-medium rounded-xl transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-stone-400/50 disabled:opacity-40 disabled:pointer-events-none active:scale-[0.98] select-none cursor-pointer';

    const variants = {
      primary: 'bg-stone-900 text-stone-100 dark:bg-stone-100 dark:text-stone-900 hover:bg-stone-800 dark:hover:bg-white shadow-sm border border-stone-700/50 dark:border-stone-200',
      sand: 'bg-[#d4c3b3] text-[#14161f] hover:bg-[#e2d5c7] shadow-sm border border-[#c5b49e]',
      secondary: 'bg-[var(--surface)] hover:bg-[var(--surface-hover)] text-[var(--foreground)] border border-[var(--border)] shadow-xs',
      outline: 'bg-transparent border border-[var(--border)] hover:border-[var(--border-hover)] text-[var(--foreground)] hover:bg-[var(--surface-hover)]',
      ghost: 'bg-transparent hover:bg-[var(--surface-hover)] text-[var(--foreground-muted)] hover:text-[var(--foreground)]',
      danger: 'bg-rose-600/90 hover:bg-rose-700 text-white shadow-sm border border-rose-500/30',
    };

    const sizes = {
      sm: 'text-xs px-3 py-1.5 h-8 gap-1.5',
      md: 'text-xs sm:text-sm px-4 py-2 h-9 sm:h-10 gap-2',
      lg: 'text-sm sm:text-base px-6 py-2.5 h-11 sm:h-12 gap-2.5',
      icon: 'h-9 w-9 p-0',
    };

    return (
      <button
        ref={ref}
        className={cn(baseStyles, variants[variant], sizes[size], className)}
        disabled={disabled || isLoading}
        {...props}
      >
        {isLoading && <Loader2 className="h-4 w-4 animate-spin text-current" />}
        {children}
      </button>
    );
  }
);
Button.displayName = 'Button';
