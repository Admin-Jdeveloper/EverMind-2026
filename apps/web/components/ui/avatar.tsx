'use client';

import * as React from 'react';
import { getUserInitial } from '@/lib/avatar';

export interface UserAvatarProps extends React.HTMLAttributes<HTMLDivElement> {
  name?: string | null;
  email?: string | null;
  image?: string | null;
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
  fallback?: string;
}

const sizeClasses: Record<NonNullable<UserAvatarProps['size']>, string> = {
  xs: 'h-6 w-6 text-[10px]',
  sm: 'h-7 w-7 text-xs',
  md: 'h-8 w-8 text-xs',
  lg: 'h-10 w-10 text-sm',
  xl: 'h-12 w-12 text-base',
};

export function UserAvatar({
  name,
  email,
  image,
  size = 'md',
  fallback = 'U',
  className = '',
  ...props
}: UserAvatarProps) {
  const [imageError, setImageError] = React.useState(false);
  const initial = getUserInitial(name, email, fallback);
  const sizeClass = sizeClasses[size] || sizeClasses.md;
  const label = name?.trim() || email?.trim() || 'User avatar';

  if (image && !imageError) {
    return (
      <div
        className={`relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-[var(--border)] bg-[var(--surface-elevated)] select-none shadow-2xs ${sizeClass} ${className}`}
        role="img"
        aria-label={label}
        {...props}
      >
        <img
          src={image}
          alt={label}
          className="h-full w-full object-cover rounded-full"
          onError={() => setImageError(true)}
        />
      </div>
    );
  }

  return (
    <div
      className={`inline-flex shrink-0 items-center justify-center rounded-full bg-[#2A2925] text-[#F5F2EB] dark:bg-[#EAE4DC] dark:text-[#171614] border border-[var(--border)] font-semibold font-mono tracking-tight select-none shadow-2xs ${sizeClass} ${className}`}
      role="img"
      aria-label={label}
      {...props}
    >
      <span>{initial}</span>
    </div>
  );
}
