'use client';

import * as React from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}

export function Modal({ isOpen, onClose, title, description, children, className }: ModalProps) {
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.body.style.overflow = 'unset';
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-2.5 sm:p-4 bg-black/75 backdrop-blur-md animate-in fade-in duration-200"
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? 'modal-title' : undefined}
    >
      <div
        className="fixed inset-0"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className={cn(
          'relative w-full max-w-lg max-h-[92vh] sm:max-h-[88vh] flex flex-col rounded-2xl border border-[var(--border)] bg-[var(--surface-elevated)] text-[var(--foreground)] p-4 sm:p-6 shadow-2xl z-10 animate-in zoom-in-95 duration-150 overflow-hidden min-w-0',
          className
        )}
      >
        <div className="flex items-start justify-between gap-3 pb-3 sm:pb-4 border-b border-[var(--border)] shrink-0 min-w-0">
          <div className="min-w-0 flex-1">
            {title && (
              <h2 id="modal-title" className="text-sm sm:text-base font-semibold text-[var(--foreground)] break-words">
                {title}
              </h2>
            )}
            {description && (
              <p className="mt-0.5 text-xs text-[var(--foreground-muted)] leading-relaxed break-words">
                {description}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="rounded-lg p-1.5 text-[var(--foreground-muted)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)] transition-colors cursor-pointer shrink-0 min-h-[36px] min-w-[36px] flex items-center justify-center"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="mt-3 sm:mt-4 overflow-y-auto overflow-x-hidden flex-1 pr-1 min-w-0">{children}</div>
      </div>
    </div>
  );
}
