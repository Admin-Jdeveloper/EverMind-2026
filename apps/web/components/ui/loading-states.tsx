'use client';

import * as React from 'react';

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
