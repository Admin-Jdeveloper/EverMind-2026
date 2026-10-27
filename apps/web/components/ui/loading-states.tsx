'use client';

import * as React from 'react';
import {
  Loader2,
  AlertCircle,
  RefreshCw,
  CheckCircle2,
  Clock,
  Cpu,
  Layers,
  Database,
  Search,
  FileQuestion,
  LucideIcon
} from 'lucide-react';
import { Button } from '@/components/ui/button';

// -----------------------------------------------------------------------------
// 1. Inline Spinner
// -----------------------------------------------------------------------------
export function InlineSpinner({
  size = 'sm',
  className = '',
  text
}: {
  size?: 'xs' | 'sm' | 'md' | 'lg';
  className?: string;
  text?: string;
}) {
  const sizeMap = {
    xs: 'h-3 w-3',
    sm: 'h-4 w-4',
    md: 'h-5 w-5',
    lg: 'h-6 w-6'
  };

  return (
    <span className={`inline-flex items-center gap-1.5 text-inherit ${className}`}>
      <Loader2 className={`${sizeMap[size]} animate-spin shrink-0`} />
      {text && <span className="text-xs">{text}</span>}
    </span>
  );
}

// -----------------------------------------------------------------------------
// 2. Real Upload Progress Bar
// -----------------------------------------------------------------------------
export function UploadProgressBar({
  progress,
  filename,
  isProcessing = false,
  stageText
}: {
  progress: number;
  filename?: string;
  isProcessing?: boolean;
  stageText?: string;
}) {
  const clampedProgress = Math.min(Math.max(progress, 0), 100);

  return (
    <div className="w-full space-y-2 p-3.5 rounded-xl bg-[var(--surface-elevated)] border border-[var(--border)]">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-[var(--foreground)] truncate max-w-[200px]">
          {filename || 'Uploading file...'}
        </span>
        <span className="font-mono text-[var(--foreground-muted)] font-semibold">
          {isProcessing ? (stageText || 'Processing...') : `${clampedProgress}%`}
        </span>
      </div>

      <div className="w-full h-2 rounded-full bg-[var(--surface)] overflow-hidden relative">
        <div
          className={`h-full transition-all duration-300 ease-out rounded-full ${
            isProcessing
              ? 'bg-[var(--accent-sand)] animate-pulse w-full'
              : 'bg-stone-800 dark:bg-stone-200'
          }`}
          style={{ width: isProcessing ? '100%' : `${clampedProgress}%` }}
        />
      </div>

      <p className="text-[11px] text-[var(--foreground-muted)]">
        {isProcessing
          ? 'File received. Extracting text and generating vector embeddings...'
          : 'Uploading file directly to secure storage...'}
      </p>
    </div>
  );
}

// -----------------------------------------------------------------------------
// 3. Granular Stage Badge for Content Ingestion
// -----------------------------------------------------------------------------
export function StageBadge({
  status,
  className = ''
}: {
  status: string;
  className?: string;
}) {
  const normStatus = (status || 'pending').toLowerCase();

  switch (normStatus) {
    case 'completed':
      return (
        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 ${className}`}>
          <CheckCircle2 className="h-3 w-3" />
          Indexed
        </span>
      );
    case 'extracting':
      return (
        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-500 border border-amber-500/20 animate-pulse ${className}`}>
          <Loader2 className="h-3 w-3 animate-spin" />
          Extracting Text
        </span>
      );
    case 'chunking':
      return (
        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-500/10 text-blue-500 border border-blue-500/20 animate-pulse ${className}`}>
          <Layers className="h-3 w-3" />
          Chunking
        </span>
      );
    case 'embedding':
      return (
        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-500/10 text-purple-400 border border-purple-500/20 animate-pulse ${className}`}>
          <Cpu className="h-3 w-3 animate-spin" />
          Generating Vectors
        </span>
      );
    case 'indexing':
      return (
        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-stone-500/10 text-[var(--foreground)] border border-[var(--border)] animate-pulse ${className}`}>
          <Database className="h-3 w-3" />
          Indexing
        </span>
      );
    case 'processing':
      return (
        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-stone-500/10 text-[var(--foreground)] border border-[var(--border)] animate-pulse ${className}`}>
          <Loader2 className="h-3 w-3 animate-spin" />
          Processing
        </span>
      );
    case 'partial':
      return (
        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-500 border border-amber-500/20 ${className}`}>
          <Clock className="h-3 w-3" />
          Metadata Only
        </span>
      );
    case 'failed':
      return (
        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-500/10 text-rose-500 border border-rose-500/20 ${className}`}>
          <AlertCircle className="h-3 w-3" />
          Failed
        </span>
      );
    case 'pending':
    default:
      return (
        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-[var(--surface-hover)] text-[var(--foreground-muted)] border border-[var(--border)] ${className}`}>
          <Clock className="h-3 w-3" />
          Queued
        </span>
      );
  }
}

// -----------------------------------------------------------------------------
// 4. Skeleton Loaders
// -----------------------------------------------------------------------------
export function SkeletonCard({ count = 1 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="p-5 rounded-2xl bg-[var(--surface)] border border-[var(--border)] space-y-4 animate-pulse"
        >
          <div className="flex items-center justify-between gap-3">
            <div className="h-4 bg-[var(--surface-hover)] rounded w-1/4" />
            <div className="h-4 bg-[var(--surface-hover)] rounded w-16" />
          </div>
          <div className="space-y-2">
            <div className="h-5 bg-[var(--surface-hover)] rounded w-3/4" />
            <div className="h-3.5 bg-[var(--surface-hover)]/70 rounded w-full" />
            <div className="h-3.5 bg-[var(--surface-hover)]/70 rounded w-5/6" />
          </div>
          <div className="flex items-center gap-2 pt-2">
            <div className="h-5 bg-[var(--surface-hover)] rounded-full w-14" />
            <div className="h-5 bg-[var(--surface-hover)] rounded-full w-20" />
          </div>
        </div>
      ))}
    </>
  );
}

export function SkeletonList({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="p-4 rounded-xl bg-[var(--surface)] border border-[var(--border)] flex items-center justify-between gap-4 animate-pulse"
        >
          <div className="flex items-center gap-3 flex-1">
            <div className="h-8 w-8 rounded-lg bg-[var(--surface-hover)] shrink-0" />
            <div className="space-y-1.5 flex-1">
              <div className="h-4 bg-[var(--surface-hover)] rounded w-1/3" />
              <div className="h-3 bg-[var(--surface-hover)]/70 rounded w-1/2" />
            </div>
          </div>
          <div className="h-6 w-20 bg-[var(--surface-hover)] rounded-full shrink-0" />
        </div>
      ))}
    </div>
  );
}

// -----------------------------------------------------------------------------
// 5. Page Loading Container
// -----------------------------------------------------------------------------
export function PageLoading({ text = 'Loading...' }: { text?: string }) {
  return (
    <div className="min-h-[50vh] flex flex-col items-center justify-center space-y-3 text-[var(--foreground-muted)]">
      <Loader2 className="h-8 w-8 animate-spin text-[var(--foreground)]" />
      <p className="text-sm font-medium">{text}</p>
    </div>
  );
}

// -----------------------------------------------------------------------------
// 6. Reusable Empty State
// -----------------------------------------------------------------------------
export function EmptyState({
  icon: Icon = FileQuestion,
  title,
  description,
  actionLabel,
  onAction
}: {
  icon?: LucideIcon;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="p-10 text-center rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface)] max-w-lg mx-auto my-8 space-y-3">
      <div className="inline-flex p-3 rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] text-[var(--foreground)] mb-1">
        <Icon className="h-6 w-6" />
      </div>
      <h3 className="text-sm sm:text-base font-semibold text-[var(--foreground)]">{title}</h3>
      <p className="text-xs text-[var(--foreground-muted)] max-w-sm mx-auto leading-relaxed">
        {description}
      </p>
      {actionLabel && onAction && (
        <div className="pt-2">
          <Button onClick={onAction} variant="primary" size="sm">
            {actionLabel}
          </Button>
        </div>
      )}
    </div>
  );
}

// -----------------------------------------------------------------------------
// 7. Reusable Error Banner with Retry
// -----------------------------------------------------------------------------
export function ErrorBanner({
  message,
  onRetry
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-500 flex items-center justify-between gap-3 text-xs">
      <div className="flex items-center gap-2">
        <AlertCircle className="h-4 w-4 shrink-0" />
        <span>{message}</span>
      </div>
      {onRetry && (
        <Button
          onClick={onRetry}
          variant="secondary"
          size="sm"
          className="h-7 text-xs border-rose-500/30 text-rose-500"
        >
          <RefreshCw className="h-3 w-3 mr-1" />
          Retry
        </Button>
      )}
    </div>
  );
}
