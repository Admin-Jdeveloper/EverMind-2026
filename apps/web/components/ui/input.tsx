import * as React from 'react';
import { cn } from '@/lib/utils';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  icon?: React.ReactNode;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, label, error, icon, id, ...props }, ref) => {
    return (
      <div className="w-full space-y-1 relative">
        {label && (
          <label htmlFor={id} className="block text-xs font-medium text-[var(--foreground)]">
            {label}
          </label>
        )}
        <div className="relative flex items-center">
          {icon && (
            <div className="absolute left-3.5 text-[var(--foreground-muted)] pointer-events-none flex items-center justify-center">
              {icon}
            </div>
          )}
          <input
            id={id}
            type={type}
            className={cn(
              'flex h-10 w-full rounded-xl bg-[var(--surface-elevated)] border border-[var(--border)] px-3.5 py-2 text-xs sm:text-sm text-[var(--foreground)] placeholder:text-[var(--foreground-muted)] shadow-2xs transition-all duration-200',
              'focus-visible:outline-none focus-visible:border-[var(--accent-sand)] focus-visible:ring-2 focus-visible:ring-[var(--accent-sand)]/20',
              'disabled:cursor-not-allowed disabled:opacity-50',
              icon && 'pl-10',
              error && 'border-rose-500 focus-visible:border-rose-500 focus-visible:ring-rose-500/20',
              className
            )}
            ref={ref}
            {...props}
          />
        </div>
        {error && <p className="mt-1.5 text-xs text-rose-500 font-medium">{error}</p>}
      </div>
    );
  }
);
Input.displayName = 'Input';
