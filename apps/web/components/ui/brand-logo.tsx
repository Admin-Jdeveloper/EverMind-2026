import React from 'react';
import Link from 'next/link';

interface BrandLogoProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  showWordmark?: boolean;
  href?: string;
  onClick?: () => void;
  title?: string;
}

/**
 * Evermind — Sovereign Brand Logo & Wordmark Component
 * 
 * Renders the signature 3-pill vertical intelligence waveform mark
 * and editorial wordmark. Supports light and dark modes seamlessly.
 */
export function BrandLogo({
  className = '',
  size = 'md',
  showWordmark = true,
  href,
  onClick,
  title = 'Evermind',
}: BrandLogoProps) {
  // Dimensions for the icon container
  const sizeClasses = {
    sm: 'h-6 w-6 rounded-md px-1 gap-[2px]',
    md: 'h-7 w-7 rounded-lg px-1 gap-[2.5px]',
    lg: 'h-9 w-9 rounded-xl px-1.5 gap-[3px]',
  };

  // Dimensions for the 3 waveform pills
  const pillClasses = {
    sm: {
      left: 'w-[2px] h-2.5',
      center: 'w-[2px] h-3.5',
      right: 'w-[2px] h-2',
    },
    md: {
      left: 'w-[2.5px] h-3',
      center: 'w-[2.5px] h-4.5',
      right: 'w-[2.5px] h-2.5',
    },
    lg: {
      left: 'w-[3px] h-4',
      center: 'w-[3px] h-6',
      right: 'w-[3px] h-3.5',
    },
  };

  const textClasses = {
    sm: 'text-xs tracking-tight',
    md: 'text-[15px] tracking-tight',
    lg: 'text-lg tracking-tight',
  };

  const content = (
    <div className={`inline-flex items-center gap-2.5 sm:gap-3 group shrink-0 ${className}`}>
      {/* 3-Pill Intelligence Waveform Mark */}
      <div
        className={`${sizeClasses[size]} border border-[var(--border)] bg-[var(--surface-elevated)] flex items-center justify-center shrink-0 shadow-xs transition-colors group-hover:border-[var(--accent-sand,#D6C2A3)]`}
        aria-hidden="true"
      >
        <span
          className={`${pillClasses[size].left} bg-[var(--foreground)] rounded-full transition-colors group-hover:bg-[var(--accent-sand,#D6C2A3)]`}
        />
        <span
          className={`${pillClasses[size].center} bg-[var(--foreground)] rounded-full transition-colors group-hover:bg-[var(--accent-sand,#D6C2A3)]`}
        />
        <span
          className={`${pillClasses[size].right} bg-[var(--foreground)] rounded-full transition-colors group-hover:bg-[var(--accent-sand,#D6C2A3)]`}
        />
      </div>

      {/* Editorial Wordmark */}
      {showWordmark && (
        <span
          className={`font-medium ${textClasses[size]} text-[var(--foreground)] transition-opacity group-hover:opacity-90 truncate`}
        >
          Evermind
        </span>
      )}
    </div>
  );

  if (href) {
    return (
      <Link
        href={href}
        onClick={onClick}
        title={title}
        aria-label={title}
        className="focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--foreground)] rounded-lg min-w-0 inline-flex items-center"
      >
        {content}
      </Link>
    );
  }

  return content;
}
