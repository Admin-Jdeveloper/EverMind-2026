'use client';

import * as React from 'react';
import { Trash2, X, ShieldAlert, Loader2, FileText, MessageSquare, Folder, Database } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface DeleteConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => Promise<void> | void;
  title?: string;
  eyebrow?: string;
  itemName?: string;
  itemType?: 'workspace' | 'content' | 'chat' | 'collection' | 'memory' | string;
  itemMeta?: string;
  itemIcon?: React.ReactNode;
  consequenceText?: string;
  warningText?: string;
  isDeleting?: boolean;
  errorMessage?: string | null;
  confirmLabel?: string;
  cancelLabel?: string;
}

export function DeleteConfirmationModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  eyebrow = 'PERMANENT ACTION',
  itemName,
  itemType = 'content',
  itemMeta,
  itemIcon,
  consequenceText,
  warningText = 'This action cannot be undone.',
  isDeleting = false,
  errorMessage = null,
  confirmLabel = 'Delete permanently',
  cancelLabel,
}: DeleteConfirmationModalProps) {
  const cancelButtonRef = React.useRef<HTMLButtonElement>(null);
  const confirmButtonRef = React.useRef<HTMLButtonElement>(null);

  // Focus management & Escape key handling
  React.useEffect(() => {
    if (!isOpen) return;

    const timer = setTimeout(() => {
      cancelButtonRef.current?.focus();
    }, 50);

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (!isDeleting) {
          e.preventDefault();
          onClose();
        }
      }
    };

    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      clearTimeout(timer);
      document.body.style.overflow = 'unset';
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, isDeleting, onClose]);

  if (!isOpen) return null;

  // Default dynamic labels & descriptions tailored to the reference screenshot
  const resolvedHeading =
    title ||
    (itemType === 'workspace'
      ? 'Delete this workspace?'
      : itemType === 'chat'
      ? 'Delete this conversation?'
      : itemType === 'collection'
      ? 'Delete this collection?'
      : 'Delete this content?');

  const resolvedDescription =
    consequenceText ||
    (itemType === 'workspace'
      ? 'Everything in your personal workspace will be permanently removed.'
      : itemType === 'chat'
      ? 'This conversation and its saved messages will be permanently deleted.'
      : itemType === 'collection'
      ? 'This collection and its associations will be permanently removed.'
      : 'This item will be permanently removed along with its indexed embeddings and chunks.');

  const resolvedCancelLabel =
    cancelLabel || (itemType === 'workspace' ? 'Keep workspace' : 'Cancel');

  // Fallback item icon based on type
  const renderItemIcon = () => {
    if (itemIcon) return itemIcon;
    if (itemType === 'chat') {
      return <MessageSquare className="h-4 w-4" />;
    }
    if (itemType === 'collection') {
      return <Folder className="h-4 w-4" />;
    }
    if (itemType === 'workspace') {
      return <Database className="h-4 w-4" />;
    }
    return <FileText className="h-4 w-4" />;
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs animate-in fade-in duration-200"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="delete-dialog-title"
      aria-describedby="delete-dialog-description"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0"
        onClick={() => {
          if (!isDeleting) onClose();
        }}
        aria-hidden="true"
      />

      {/* Modal Surface — exact reproduction of the design reference */}
      <div
        className={cn(
          'relative w-full max-w-[440px] rounded-[28px] border border-[#EAE6DF] dark:border-[rgba(255,255,255,0.12)] bg-[#FFFFFF] dark:bg-[#1C1C1A] text-[var(--foreground)] p-6 sm:p-7 shadow-[0_20px_50px_rgba(0,0,0,0.15)] z-10 animate-in zoom-in-95 duration-150 select-none'
        )}
      >
        {/* Top Bar: Pale red square with trash icon on left, close icon on right */}
        <div className="flex items-center justify-between">
          <div className="w-11 h-11 rounded-2xl bg-[#F7EBEB] dark:bg-[#382020] flex items-center justify-center text-[#9C413D] dark:text-[#E06A66] shrink-0">
            <Trash2 className="h-5 w-5 stroke-[1.8]" />
          </div>

          <button
            type="button"
            onClick={onClose}
            disabled={isDeleting}
            className="p-1.5 rounded-full text-[#8C8880] hover:text-[#1F1E1B] dark:hover:text-white transition-colors cursor-pointer disabled:opacity-40"
            title="Close dialog"
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Uppercase red eyebrow */}
        <div className="text-[11px] font-bold tracking-widest text-[#9C413D] dark:text-[#E06A66] uppercase mt-4 mb-1">
          {eyebrow}
        </div>

        {/* Clear Heading */}
        <h2
          id="delete-dialog-title"
          className="text-xl sm:text-[22px] font-semibold text-[#1F1E1B] dark:text-[#F5F5F0] tracking-tight leading-snug"
        >
          {resolvedHeading}
        </h2>

        {/* Supporting description */}
        <p
          id="delete-dialog-description"
          className="text-xs sm:text-sm text-[#6F6C66] dark:text-[#A6A29A] leading-relaxed mt-1"
        >
          {resolvedDescription}
        </p>

        {/* Contextual item card with icon, dynamic name, and metadata */}
        <div className="rounded-2xl bg-[#F6F4EF] dark:bg-[#232321] border border-[#ECE6DC] dark:border-[rgba(255,255,255,0.08)] p-3.5 sm:p-4 flex items-center gap-3.5 my-4">
          <div className="w-10 h-10 rounded-xl bg-[#EAE5DC] dark:bg-[#2D2D2A] flex items-center justify-center text-[#5C5952] dark:text-[#D4D0C7] shrink-0">
            {renderItemIcon()}
          </div>
          <div className="min-w-0 flex-1">
            <h4 className="text-xs sm:text-sm font-semibold text-[#1F1E1B] dark:text-[#F5F5F0] truncate">
              {itemName || (itemType === 'workspace' ? 'Personal workspace' : `Selected ${itemType}`)}
            </h4>
            {itemMeta && (
              <p className="text-[11px] sm:text-xs text-[#7B7770] dark:text-[#9A968E] mt-0.5 truncate">
                {itemMeta}
              </p>
            )}
          </div>
        </div>

        {/* Warning row with shield icon */}
        <div className="flex items-center gap-2 text-xs font-normal text-[#9C413D] dark:text-[#E06A66] my-3.5">
          <ShieldAlert className="h-4 w-4 shrink-0 text-[#9C413D] dark:text-[#E06A66]" />
          <span>{warningText}</span>
        </div>

        {/* Error notification banner if delete fails (keeps modal open, allows safe retry) */}
        {errorMessage && (
          <div className="rounded-xl bg-rose-500/10 border border-rose-500/20 p-3 my-2 text-xs text-rose-500 flex items-center gap-2">
            <span className="font-medium">{errorMessage}</span>
          </div>
        )}

        {/* Full-width thin divider */}
        <div className="border-t border-[#ECE7DE] dark:border-[rgba(255,255,255,0.08)] -mx-6 sm:-mx-7 my-4" />

        {/* Action Buttons: Keep workspace / Cancel and Delete permanently */}
        <div className="flex items-center justify-end gap-3">
          <button
            ref={cancelButtonRef}
            type="button"
            onClick={onClose}
            disabled={isDeleting}
            className="px-5 py-2.5 rounded-xl border border-[#DED9D0] dark:border-[rgba(255,255,255,0.16)] bg-white dark:bg-[#232321] hover:bg-[#F6F4EF] dark:hover:bg-[#2C2C29] text-xs sm:text-sm font-medium text-[#1F1E1B] dark:text-[#F5F5F0] transition-colors shadow-2xs cursor-pointer disabled:opacity-50"
          >
            {resolvedCancelLabel}
          </button>

          <button
            ref={confirmButtonRef}
            type="button"
            onClick={async () => {
              if (isDeleting) return;
              await onConfirm();
            }}
            disabled={isDeleting}
            className="px-5 py-2.5 rounded-xl bg-[#9C413D] hover:bg-[#883632] text-white text-xs sm:text-sm font-medium transition-colors shadow-xs flex items-center gap-2 cursor-pointer disabled:opacity-50"
          >
            {isDeleting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin shrink-0" />
                <span>Deleting...</span>
              </>
            ) : (
              <>
                <Trash2 className="h-4 w-4 shrink-0" />
                <span>{confirmLabel}</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
