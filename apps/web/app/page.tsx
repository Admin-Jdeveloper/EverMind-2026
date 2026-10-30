'use client';

import * as React from 'react';
import Link from 'next/link';
import {
  Sparkles,
  ArrowRight,
  Sun,
  Moon,
  Laptop,
  FileText,
  HelpCircle,
  Folder,
  Upload,
  Play,
  Menu,
  X,
  FileCode,
  CheckCircle2,
} from 'lucide-react';
import { useSession, signOut } from 'next-auth/react';
import { motion, useReducedMotion } from 'motion/react';
import { useTheme } from '@/components/theme-provider';
import { BrandLogo } from '@/components/ui/brand-logo';
import { getUserInitial } from '@/lib/avatar';

export default function LandingPage() {
  const { theme, setTheme } = useTheme();
  const { data: session, status } = useSession();
  const [mounted, setMounted] = React.useState(false);
  const [showHelpModal, setShowHelpModal] = React.useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = React.useState(false);
  const shouldReduceMotion = useReducedMotion();

  React.useEffect(() => {
    setMounted(true);
  }, []);

  const user = session?.user;
  const displayName = user?.name || (user?.email ? user.email.split('@')[0] : 'User');
  const initial = getUserInitial(user?.name, user?.email, 'U');

  // Smooth scroll handler
  const handleScrollTo = (e: React.MouseEvent<HTMLAnchorElement>, id: string) => {
    e.preventDefault();
    setMobileMenuOpen(false);
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)] flex flex-col antialiased selection:bg-[#D6C2A3]/25 selection:text-[var(--foreground)] font-sans transition-colors duration-300">
      {/* 1. SLIM EDITORIAL NAVIGATION BAR */}
      <header className="sticky top-0 z-50 h-16 border-b border-[var(--border)] bg-[var(--background)]/90 backdrop-blur-md px-4 sm:px-8 lg:px-12 flex items-center justify-between gap-4 transition-colors">
        {/* Left: Brand Logo & Wordmark */}
        <BrandLogo href="/" size="md" title="Evermind" />

        {/* Center: Editorial Navigation Links */}
        <nav className="hidden md:flex items-center gap-8 text-xs font-normal tracking-wide text-[var(--foreground-muted)]">
          <a
            href="#how-it-works"
            onClick={(e) => handleScrollTo(e, 'how-it-works')}
            className="hover:text-[var(--foreground)] transition-colors"
          >
            How it works
          </a>
          <a
            href="#features"
            onClick={(e) => handleScrollTo(e, 'features')}
            className="hover:text-[var(--foreground)] transition-colors"
          >
            Features
          </a>
          <a
            href="#principles"
            onClick={(e) => handleScrollTo(e, 'principles')}
            className="hover:text-[var(--foreground)] transition-colors"
          >
            Principles
          </a>
        </nav>

        {/* Right: Theme Selector Pill & Authentication Actions */}
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          {/* Theme Selector Pill (Light / Dark / System) — Visible on sm+ screens */}
          <div
            className="hidden sm:flex items-center gap-1 p-1 rounded-full bg-[var(--surface-elevated)] border border-[var(--border)] text-[var(--foreground-muted)] shadow-xs"
            role="radiogroup"
            aria-label="Color theme selection"
          >
            <button
              onClick={() => setTheme('light')}
              title="Light mode"
              aria-label="Light mode"
              className={`p-1 sm:p-1.5 rounded-full transition-all ${
                theme === 'light'
                  ? 'bg-[var(--surface-hover)] text-amber-500 shadow-xs'
                  : 'hover:text-[var(--foreground)]'
              }`}
            >
              <Sun className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setTheme('dark')}
              title="Dark mode"
              aria-label="Dark mode"
              className={`p-1 sm:p-1.5 rounded-full transition-all ${
                theme === 'dark'
                  ? 'bg-[var(--surface-hover)] text-[#D6C2A3] shadow-xs'
                  : 'hover:text-[var(--foreground)]'
              }`}
            >
              <Moon className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setTheme('system')}
              title="System preference"
              aria-label="System preference"
              className={`p-1 sm:p-1.5 rounded-full transition-all ${
                theme === 'system'
                  ? 'bg-[var(--surface-hover)] text-[var(--foreground)] shadow-xs'
                  : 'hover:text-[var(--foreground)]'
              }`}
            >
              <Laptop className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Authentication Actions */}
          {mounted && status === 'authenticated' && session?.user ? (
            <div className="flex items-center gap-2 sm:gap-3">
              <div
                className="hidden xs:flex h-7 w-7 rounded-full bg-[#D6C2A3] text-[#10100F] items-center justify-center text-xs font-semibold shrink-0 shadow-xs"
                title={user?.email || displayName}
              >
                {initial}
              </div>
              <span className="text-xs font-medium text-[var(--foreground)] hidden lg:inline truncate max-w-[120px]">
                {displayName}
              </span>
              <Link
                href="/dashboard"
                className="px-3 sm:px-3.5 py-1.5 rounded-full bg-[var(--primary)] hover:opacity-90 text-[var(--primary-foreground)] text-xs font-medium transition-opacity shadow-xs whitespace-nowrap shrink-0"
              >
                Dashboard
              </Link>
              <button
                onClick={() => signOut({ callbackUrl: '/' })}
                title="Sign out"
                className="text-xs text-[var(--foreground-muted)] hover:text-rose-400 transition-colors px-1 py-1 cursor-pointer shrink-0 hidden sm:inline"
              >
                Sign out
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 sm:gap-3">
              <Link
                href="/register"
                className="hidden sm:inline text-xs text-[var(--foreground-muted)] hover:text-[var(--foreground)] transition-colors px-2 py-1.5 shrink-0 font-medium"
              >
                Create account
              </Link>
              <Link
                href="/login"
                className="px-3.5 sm:px-4 py-1.5 rounded-full bg-[var(--primary)] hover:opacity-90 text-[var(--primary-foreground)] text-xs font-medium transition-opacity shadow-xs whitespace-nowrap shrink-0"
              >
                Sign in
              </Link>
            </div>
          )}

          {/* Mobile Navigation Menu Toggle */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden p-1.5 rounded-lg border border-[var(--border)] text-[var(--foreground-muted)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)] transition-colors shrink-0"
            aria-label="Toggle navigation menu"
          >
            {mobileMenuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>
      </header>

      {/* Mobile Navigation Dropdown */}
      {mobileMenuOpen && (
        <div className="md:hidden border-b border-[var(--border)] bg-[var(--surface-base)] px-6 py-4 flex flex-col gap-3 text-xs z-40 animate-in fade-in slide-in-from-top-2 duration-200">
          {/* Mobile Theme Selector Pill */}
          <div className="flex items-center justify-between pb-2 border-b border-[var(--border)]">
            <span className="text-[11px] text-[var(--foreground-muted)] font-mono uppercase tracking-wider">
              Theme
            </span>
            <div
              className="flex items-center gap-1 p-1 rounded-full bg-[var(--surface-elevated)] border border-[var(--border)] text-[var(--foreground-muted)] shadow-xs"
              role="radiogroup"
              aria-label="Color theme selection"
            >
              <button
                onClick={() => setTheme('light')}
                title="Light mode"
                aria-label="Light mode"
                className={`p-1.5 rounded-full transition-all ${
                  theme === 'light'
                    ? 'bg-[var(--surface-hover)] text-amber-500 shadow-xs'
                    : 'hover:text-[var(--foreground)]'
                }`}
              >
                <Sun className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setTheme('dark')}
                title="Dark mode"
                aria-label="Dark mode"
                className={`p-1.5 rounded-full transition-all ${
                  theme === 'dark'
                    ? 'bg-[var(--surface-hover)] text-[#D6C2A3] shadow-xs'
                    : 'hover:text-[var(--foreground)]'
                }`}
              >
                <Moon className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setTheme('system')}
                title="System preference"
                aria-label="System preference"
                className={`p-1.5 rounded-full transition-all ${
                  theme === 'system'
                    ? 'bg-[var(--surface-hover)] text-[var(--foreground)] shadow-xs'
                    : 'hover:text-[var(--foreground)]'
                }`}
              >
                <Laptop className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          <a
            href="#how-it-works"
            onClick={(e) => handleScrollTo(e, 'how-it-works')}
            className="py-1 text-[var(--foreground-muted)] hover:text-[var(--foreground)] transition-colors"
          >
            How it works
          </a>
          <a
            href="#features"
            onClick={(e) => handleScrollTo(e, 'features')}
            className="py-1 text-[var(--foreground-muted)] hover:text-[var(--foreground)] transition-colors"
          >
            Features
          </a>
          <a
            href="#principles"
            onClick={(e) => handleScrollTo(e, 'principles')}
            className="py-1 text-[var(--foreground-muted)] hover:text-[var(--foreground)] transition-colors"
          >
            Principles
          </a>
          <div className="pt-2 border-t border-[var(--border)] flex items-center justify-between">
            {mounted && status === 'authenticated' ? (
              <button
                onClick={() => signOut({ callbackUrl: '/' })}
                className="py-1 text-left text-rose-400 hover:text-rose-300 transition-colors"
              >
                Sign out
              </button>
            ) : (
              <div className="flex items-center gap-4 w-full pt-1">
                <Link
                  href="/login"
                  className="py-1 text-[var(--foreground-muted)] hover:text-[var(--foreground)] transition-colors font-medium"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Sign in
                </Link>
                <Link
                  href="/register"
                  className="py-1 text-[var(--accent-sand)] font-medium hover:underline transition-colors"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Create account
                </Link>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 2. HERO SECTION — CINEMATIC SPATIAL COMPOSITION */}
      <section className="relative overflow-hidden pt-8 pb-16 sm:pt-12 sm:pb-20 lg:pt-20 lg:pb-32 px-4 sm:px-8 lg:px-12">
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-10 items-center">
          {/* Left Column: Editorial Headline, Subtitle, and Actions */}
          <div className="lg:col-span-5 space-y-6 sm:space-y-8 min-w-0">
            {/* Eyebrow */}
            <div className="inline-flex items-center gap-2 text-[11px] font-mono tracking-widest text-[var(--accent-sand)] uppercase">
              <Sparkles className="h-3 w-3 text-[var(--accent-sand)]" />
              <span>YOUR RESEARCH, COMPILED</span>
            </div>

            {/* Headline with Serif Italic Emphasis */}
            <h1 className="text-3xl xs:text-4xl sm:text-6xl lg:text-[62px] font-light tracking-tight text-[var(--foreground)] leading-[1.08]">
              Turn scattered <br />
              sources into <br />
              <span className="font-editorial italic font-normal text-[var(--accent-sand)]">
                clear thinking.
              </span>
            </h1>

            {/* Supporting Copy */}
            <p className="text-xs sm:text-base text-[var(--foreground-muted)] leading-relaxed max-w-lg font-normal">
              Bring PDFs and videos into one considered workspace. Organize what matters, then ask
              questions grounded in your own sources.
            </p>

            {/* Actions */}
            <div className="pt-2 flex flex-wrap items-center gap-3 sm:gap-4">
              <Link
                href="/login"
                className="px-5 sm:px-6 py-2.5 sm:py-3 rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] text-xs sm:text-sm font-medium transition-all shadow-md hover:opacity-90 flex items-center gap-2 group cursor-pointer"
              >
                <span>Start compiling</span>
                <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
              </Link>

              <a
                href="#how-it-works"
                onClick={(e) => handleScrollTo(e, 'how-it-works')}
                className="text-xs sm:text-sm text-[var(--foreground-muted)] hover:text-[var(--foreground)] flex items-center gap-1.5 transition-colors cursor-pointer px-3 py-2 font-medium"
              >
                <span>See how it works</span>
                <ArrowRight className="h-3.5 w-3.5 opacity-60" />
              </a>
            </div>

            {/* Value Proposition & Design Tokens Swatches */}
            <div className="pt-2 sm:pt-4 flex items-center gap-3 text-xs text-[var(--foreground-muted)]">
              <div className="flex items-center gap-1.5">
                <div className="h-3.5 w-3.5 rounded-xs bg-[#9DAA94]" title="Sage" />
                <div className="h-3.5 w-3.5 rounded-xs bg-[#D6C2A3]" title="Champagne Sand" />
              </div>
              <span className="font-normal tracking-wide text-[11px] sm:text-xs">
                Built for focused research, not more noise.
              </span>
            </div>
          </div>

          {/* Right Column: Spatial Scene with Floating Cards & Connectors */}
          <div className="lg:col-span-7 relative flex justify-center lg:justify-end w-full min-w-0">
            <div className="relative w-full max-w-2xl min-h-[420px] sm:min-h-[520px] rounded-3xl border border-[var(--border)] bg-[var(--surface-base)] canvas-grid-bg p-4 sm:p-8 flex items-center justify-center overflow-hidden shadow-2xl">
              {/* Subtle ambient warm radial glow */}
              <div className="absolute inset-0 bg-radial from-[#D6C2A3]/10 via-transparent to-transparent pointer-events-none" />

              {/* Spatial Canvas Container with Perspective */}
              <div className="relative w-full h-full min-h-[380px] sm:min-h-[480px]">
                {/* SVG Connecting Lines (Visible on sm+ screens) */}
                <svg
                  className="hidden sm:block absolute inset-0 w-full h-full pointer-events-none z-0"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  {/* Line 1: From Doc Card to Video Card */}
                  <path
                    d="M 220 130 Q 300 120 360 145"
                    fill="none"
                    stroke="rgba(214, 194, 163, 0.28)"
                    strokeWidth="1.2"
                    strokeDasharray="3 3"
                  />
                  {/* Line 2: From Video Card to Collection Card */}
                  <path
                    d="M 430 200 Q 450 260 410 320"
                    fill="none"
                    stroke="rgba(214, 194, 163, 0.28)"
                    strokeWidth="1.2"
                    strokeDasharray="3 3"
                  />
                  {/* Line 3: From AI Answer Card to Collection Card */}
                  <path
                    d="M 280 340 Q 330 350 350 345"
                    fill="none"
                    stroke="rgba(214, 194, 163, 0.28)"
                    strokeWidth="1.2"
                    strokeDasharray="3 3"
                  />

                  {/* Relationship Node 1 */}
                  <circle cx="220" cy="130" r="3.5" fill="#D6C2A3" />
                  <circle cx="220" cy="130" r="7" fill="none" stroke="rgba(214, 194, 163, 0.25)" />

                  {/* Relationship Node 2 */}
                  <circle cx="360" cy="145" r="3.5" fill="#D6C2A3" />
                  <circle cx="360" cy="145" r="7" fill="none" stroke="rgba(214, 194, 163, 0.25)" />

                  {/* Relationship Node 3 */}
                  <circle cx="410" cy="320" r="3.5" fill="#D6C2A3" />
                  <circle cx="410" cy="320" r="7" fill="none" stroke="rgba(214, 194, 163, 0.25)" />
                </svg>

                {/* Card 1: Document Card (Centered on mobile, tilted top-left on sm+) */}
                <motion.div
                  initial={{ opacity: 0, y: 15 }}
                  animate={
                    shouldReduceMotion
                      ? { opacity: 1, y: 0 }
                      : { opacity: 1, y: [0, -5, 0], rotate: -3 }
                  }
                  transition={{
                    opacity: { duration: 0.6 },
                    y: { repeat: Infinity, duration: 6, ease: 'easeInOut' },
                  }}
                  whileHover={{ scale: 1.02, rotate: -1.5, zIndex: 30 }}
                  className="absolute top-2 left-1/2 -translate-x-1/2 sm:translate-x-0 sm:top-4 sm:left-6 w-[92%] max-w-[270px] sm:w-[270px] rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] p-4 sm:p-5 shadow-2xl z-10 transition-shadow hover:border-[var(--accent-sand)]/50 cursor-pointer select-none"
                >
                  <div className="flex items-center justify-between text-[11px] text-[var(--foreground-muted)] mb-3">
                    <span className="font-mono">01</span>
                    <FileText className="h-3.5 w-3.5 text-[var(--foreground-muted)]" />
                  </div>
                  <p className="text-[10px] font-mono tracking-widest text-[var(--accent-sand)] uppercase mb-1.5 font-medium">
                    CALM TECHNOLOGY
                  </p>
                  <h4 className="text-xs sm:text-sm font-medium text-[var(--foreground)] leading-snug mb-3">
                    Designing systems that respect human attention.
                  </h4>
                  <div className="space-y-1.5 opacity-25 mb-4">
                    <div className="h-1 bg-[var(--foreground)] rounded-full w-full" />
                    <div className="h-1 bg-[var(--foreground)] rounded-full w-4/5" />
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-[var(--foreground-muted)] pt-2 border-t border-[var(--border)] font-mono">
                    <span>36 pages</span>
                    <span className="text-emerald-500/90 flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                      Indexed
                    </span>
                  </div>
                </motion.div>

                {/* Card 2: Saved Video Card (Top Right, visible on sm+) */}
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={
                    shouldReduceMotion
                      ? { opacity: 1, y: 0 }
                      : { opacity: 1, y: [0, 6, 0], rotate: 4 }
                  }
                  transition={{
                    opacity: { duration: 0.6, delay: 0.1 },
                    y: { repeat: Infinity, duration: 7, ease: 'easeInOut', delay: 0.5 },
                  }}
                  whileHover={{ scale: 1.02, rotate: 2, zIndex: 30 }}
                  className="hidden sm:block absolute top-10 right-2 sm:right-6 w-[200px] sm:w-[230px] rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] p-4 shadow-xl z-10 transition-shadow hover:border-[var(--accent-sand)]/50 cursor-pointer select-none"
                >
                  <div className="flex items-center gap-1.5 text-[10px] font-mono tracking-widest text-[var(--accent-sand)] uppercase mb-2">
                    <Play className="h-3 w-3 fill-current" />
                    <span>VIDEO</span>
                  </div>
                  <h4 className="text-xs sm:text-[13px] font-medium text-[var(--foreground)] leading-snug mb-2">
                    Building a second brain
                  </h4>
                  <p className="text-[10px] text-[var(--foreground-muted)] font-mono">
                    18:24 · Transcript ready
                  </p>
                </motion.div>

                {/* Card 3: Collection Card (Bottom Right, visible on sm+) */}
                <motion.div
                  initial={{ opacity: 0, y: 25 }}
                  animate={
                    shouldReduceMotion
                      ? { opacity: 1, y: 0 }
                      : { opacity: 1, y: [0, -4, 0], rotate: -1 }
                  }
                  transition={{
                    opacity: { duration: 0.6, delay: 0.2 },
                    y: { repeat: Infinity, duration: 6.5, ease: 'easeInOut', delay: 1 },
                  }}
                  whileHover={{ scale: 1.02, rotate: 0, zIndex: 30 }}
                  className="hidden sm:block absolute bottom-6 right-2 sm:right-8 w-[210px] sm:w-[240px] rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] p-4 sm:p-5 shadow-2xl z-20 transition-shadow hover:border-[var(--accent-sand)]/50 cursor-pointer select-none"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <div className="p-1.5 rounded-lg bg-[var(--surface-base)] border border-[var(--border)] text-[var(--accent-sand)]">
                      <Folder className="h-3.5 w-3.5" />
                    </div>
                    <div>
                      <p className="text-[9px] font-mono tracking-wider text-[var(--foreground-muted)] uppercase">
                        COLLECTION
                      </p>
                      <h4 className="text-xs sm:text-sm font-medium text-[var(--foreground)]">
                        Knowledge systems
                      </h4>
                    </div>
                  </div>
                  <p className="text-[10px] text-[var(--foreground-muted)] font-mono pl-7">
                    6 connected sources
                  </p>
                </motion.div>

                {/* Card 4: AI Answer Preview Card (Bottom Center / Left) */}
                <motion.div
                  initial={{ opacity: 0, y: 30 }}
                  animate={
                    shouldReduceMotion
                      ? { opacity: 1, y: 0 }
                      : { opacity: 1, y: [0, 5, 0], rotate: 1 }
                  }
                  transition={{
                    opacity: { duration: 0.6, delay: 0.3 },
                    y: { repeat: Infinity, duration: 7.5, ease: 'easeInOut', delay: 1.5 },
                  }}
                  whileHover={{ scale: 1.02, rotate: 0, zIndex: 30 }}
                  className="absolute bottom-4 left-1/2 -translate-x-1/2 sm:translate-x-0 sm:bottom-8 sm:left-8 w-[92%] max-w-[280px] sm:w-[290px] rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] p-4 sm:p-5 shadow-2xl z-20 transition-shadow hover:border-[var(--accent-sand)]/50 cursor-pointer select-none"
                >
                  <div className="flex items-center gap-2 mb-2.5">
                    <div className="h-5 w-5 rounded-md bg-[var(--surface-base)] border border-[var(--border)] flex items-center justify-center text-[var(--accent-sand)]">
                      <Sparkles className="h-3 w-3 text-[var(--accent-sand)]" />
                    </div>
                    <span className="text-[10px] font-mono tracking-wider text-[var(--foreground-muted)] uppercase">
                      EVERMIND
                    </span>
                  </div>
                  <p className="text-xs text-[var(--foreground)] leading-relaxed mb-3 font-normal">
                    Three ideas connect across your research. Here is the evidence...
                  </p>
                  <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-[var(--surface-base)] border border-[var(--border)] text-[10px] font-mono text-[var(--accent-sand)]">
                    <span>3 sources</span>
                  </div>
                </motion.div>

                {/* Tiny Subtle Spatial Caption */}
                <div className="hidden sm:block absolute bottom-2 right-4 text-[9px] font-mono tracking-widest text-[var(--foreground-muted)]/60 uppercase pointer-events-none select-none">
                  A LIVING MAP OF WHAT YOU KNOW
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* SECTION HEADER: A QUIETER WAY TO KNOW MORE */}
      <section className="pt-16 pb-6 px-4 sm:px-8 lg:px-12 border-t border-[var(--border)] bg-[var(--surface-subtle)]/30">
        <div className="max-w-7xl mx-auto text-left space-y-3">
          <p className="text-[11px] font-mono tracking-widest text-[var(--accent-sand)] uppercase">
            A QUIETER WAY TO KNOW MORE
          </p>
          <h2 className="text-2xl sm:text-4xl lg:text-5xl font-light tracking-tight text-[var(--foreground)]">
            From scattered material to connected knowledge.
          </h2>
        </div>
      </section>

      {/* 3. FOUR ALTERNATING EDITORIAL FEATURE SECTIONS */}

      {/* Section 01 — Save what matters (INGEST) */}
      <section
        id="how-it-works"
        className="scroll-mt-20 py-16 sm:py-24 px-4 sm:px-8 lg:px-12 border-t border-[var(--border)] bg-[var(--background)]"
      >
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-16 items-center">
          {/* Left: Text */}
          <div className="lg:col-span-5 space-y-4 min-w-0">
            <span className="text-[11px] font-mono tracking-widest text-[var(--accent-sand)] uppercase font-medium">
              01 / INGEST
            </span>
            <h3 className="text-3xl sm:text-5xl font-light tracking-tight text-[var(--foreground)]">
              Save what matters.
            </h3>
            <p className="text-sm sm:text-base text-[var(--foreground-muted)] leading-relaxed max-w-md font-normal">
              Bring in papers, reports, and videos. Each source unfolds into searchable material while
              its original context stays intact.
            </p>
          </div>

          {/* Right: Visual Spatial Canvas with Upload Dropzone & Indexing PDF Card */}
          <div className="lg:col-span-7 w-full min-w-0">
            <div className="relative w-full min-h-[360px] sm:min-h-[420px] rounded-3xl border border-[var(--border)] bg-[var(--surface-base)] canvas-grid-bg p-4 sm:p-10 flex items-center justify-center overflow-hidden shadow-xl">
              <div className="relative w-full max-w-lg flex flex-col sm:flex-row items-center justify-center gap-4 sm:gap-8 min-w-0">
                {/* Upload Target Box */}
                <div className="w-full max-w-[260px] sm:w-[140px] h-[75px] sm:h-[130px] rounded-2xl border border-dashed border-[var(--border-hover)] bg-[var(--surface-elevated)]/60 flex flex-row sm:flex-col items-center justify-center gap-2.5 text-[var(--foreground-muted)] hover:border-[var(--accent-sand)] transition-colors">
                  <Upload className="h-5 w-5 text-[var(--accent-sand)]" />
                  <span className="text-[11px] font-mono tracking-wide">Drop source</span>
                </div>

                {/* Layered PDF Card with Indexing Progress */}
                <motion.div
                  initial={{ opacity: 0, y: 15 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.6 }}
                  className="w-full max-w-[260px] sm:w-[260px] rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] p-4 sm:p-5 shadow-2xl transform sm:rotate-2 hover:rotate-0 transition-transform select-none"
                >
                  <p className="text-[10px] font-mono tracking-widest text-[var(--accent-sand)] uppercase mb-2 font-medium">
                    PDF
                  </p>
                  <h4 className="text-xs sm:text-sm font-medium text-[var(--foreground)] leading-snug mb-3">
                    The shape of digital knowledge
                  </h4>
                  <div className="space-y-1.5 opacity-20 mb-4 sm:mb-5">
                    <div className="h-1 bg-[var(--foreground)] rounded-full w-full" />
                    <div className="h-1 bg-[var(--foreground)] rounded-full w-5/6" />
                    <div className="h-1 bg-[var(--foreground)] rounded-full w-3/4" />
                  </div>
                  <div className="space-y-1.5 pt-2 border-t border-[var(--border)]">
                    <div className="flex items-center justify-between text-[10px] font-mono text-[var(--foreground-muted)]">
                      <span>Indexing</span>
                      <span className="text-[var(--accent-sand)]">Processing...</span>
                    </div>
                    {/* Restrained Champagne Progress Bar */}
                    <div className="w-full h-1 bg-[var(--surface-base)] rounded-full overflow-hidden">
                      <motion.div
                        className="h-full bg-[var(--accent-sand)] rounded-full"
                        animate={
                          shouldReduceMotion
                            ? { width: '70%' }
                            : { width: ['15%', '85%', '65%'] }
                        }
                        transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
                      />
                    </div>
                  </div>
                </motion.div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Section 02 — Give ideas a place (ORGANIZE) */}
      <section className="py-16 sm:py-24 px-4 sm:px-8 lg:px-12 border-t border-[var(--border)] bg-[var(--surface-subtle)]/20">
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-16 items-center">
          {/* Left: Visual Spatial Canvas with Overlapping Collection Cards */}
          <div className="lg:col-span-7 order-2 lg:order-1 w-full min-w-0">
            <div className="relative w-full min-h-[340px] sm:min-h-[420px] rounded-3xl border border-[var(--border)] bg-[var(--surface-base)] canvas-grid-bg p-4 sm:p-10 flex items-center justify-center overflow-hidden shadow-xl">
              <div className="relative w-full max-w-md h-[200px] sm:h-[220px] flex items-center justify-center min-w-0">
                {/* Back Card 1: AI Research (Visible on sm+ screens) */}
                <div className="hidden sm:block absolute top-2 left-6 sm:left-12 w-[190px] sm:w-[220px] rounded-2xl bg-[var(--surface-elevated)]/80 border border-[var(--border)] p-4 shadow-lg transform -rotate-6 select-none opacity-70">
                  <p className="text-[10px] font-mono tracking-widest text-[var(--foreground-muted)] uppercase">
                    AI RESEARCH
                  </p>
                </div>

                {/* Back Card 2: Product Thinking (Visible on sm+ screens) */}
                <div className="hidden sm:block absolute top-4 right-6 sm:right-12 w-[190px] sm:w-[220px] rounded-2xl bg-[var(--surface-elevated)]/80 border border-[var(--border)] p-4 shadow-lg transform rotate-6 select-none opacity-70">
                  <p className="text-[10px] font-mono tracking-widest text-[var(--accent-sand)] uppercase">
                    PRODUCT THINKING
                  </p>
                </div>

                {/* Front Prominent Collection Card */}
                <motion.div
                  initial={{ opacity: 0, y: 15 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.6 }}
                  whileHover={{ scale: 1.02 }}
                  className="relative z-10 w-full max-w-[260px] sm:w-[280px] rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] p-4 sm:p-6 shadow-2xl select-none hover:border-[var(--accent-sand)]/50 transition-colors"
                >
                  <div className="h-8 w-8 rounded-xl bg-[var(--surface-base)] border border-[var(--border)] flex items-center justify-center text-[var(--accent-sand)] mb-3 sm:mb-4">
                    <Folder className="h-4 w-4" />
                  </div>
                  <h4 className="text-sm sm:text-lg font-medium text-[var(--foreground)] mb-1">
                    Knowledge systems
                  </h4>
                  <p className="text-[11px] sm:text-xs text-[var(--foreground-muted)] font-mono">
                    6 sources · Updated today
                  </p>
                </motion.div>
              </div>
            </div>
          </div>

          {/* Right: Text */}
          <div className="lg:col-span-5 space-y-4 order-1 lg:order-2 min-w-0">
            <span className="text-[11px] font-mono tracking-widest text-[var(--accent-sand)] uppercase font-medium">
              02 / ORGANIZE
            </span>
            <h3 className="text-3xl sm:text-5xl font-light tracking-tight text-[var(--foreground)]">
              Give ideas a place.
            </h3>
            <p className="text-sm sm:text-base text-[var(--foreground-muted)] leading-relaxed max-w-md font-normal">
              Collections turn a loose library into intentional research spaces, keeping every source
              available without losing the larger picture.
            </p>
          </div>
        </div>
      </section>

      {/* Section 03 — Ask across your sources (QUESTION) */}
      <section
        id="features"
        className="scroll-mt-20 py-16 sm:py-24 px-4 sm:px-8 lg:px-12 border-t border-[var(--border)] bg-[var(--background)]"
      >
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-16 items-center">
          {/* Left: Text */}
          <div className="lg:col-span-5 space-y-4 min-w-0">
            <span className="text-[11px] font-mono tracking-widest text-[var(--accent-sand)] uppercase font-medium">
              03 / QUESTION
            </span>
            <h3 className="text-3xl sm:text-5xl font-light tracking-tight text-[var(--foreground)]">
              Ask across your sources.
            </h3>
            <p className="text-sm sm:text-base text-[var(--foreground-muted)] leading-relaxed max-w-md font-normal">
              Move from a question to a structured answer without leaving your research context.
              Conversations remain grounded in what you saved.
            </p>
          </div>

          {/* Right: Visual Spatial Canvas with User Question Bubble & Grounded Answer */}
          <div className="lg:col-span-7 w-full min-w-0">
            <div className="relative w-full min-h-[360px] sm:min-h-[440px] rounded-3xl border border-[var(--border)] bg-[var(--surface-base)] canvas-grid-bg p-4 sm:p-10 flex items-center justify-center overflow-hidden shadow-xl">
              <div className="relative w-full max-w-lg space-y-3 sm:space-y-4 min-w-0">
                {/* User Question Speech Bubble (Top Right) */}
                <motion.div
                  initial={{ opacity: 0, x: 20 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5 }}
                  className="flex justify-end"
                >
                  <div className="rounded-2xl rounded-tr-xs bg-[var(--primary)] text-[var(--primary-foreground)] px-3.5 py-2 sm:px-4 sm:py-2.5 text-xs sm:text-sm font-medium shadow-md max-w-[85%] sm:max-w-xs">
                    What patterns connect these sources?
                  </div>
                </motion.div>

                {/* AI Assistant Grounded Answer Card */}
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.6, delay: 0.15 }}
                  className="rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] p-4 sm:p-6 shadow-2xl space-y-3 sm:space-y-4 select-none"
                >
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-3.5 w-3.5 text-[var(--accent-sand)]" />
                    <span className="text-[10px] font-mono tracking-widest text-[var(--foreground-muted)] uppercase">
                      EVERMIND
                    </span>
                  </div>

                  <h4 className="text-sm sm:text-base font-medium text-[var(--foreground)]">
                    Three patterns appear consistently.
                  </h4>

                  <p className="text-xs sm:text-[13px] text-[var(--foreground-muted)] leading-relaxed">
                    The strongest connection is a shift from information capture toward contextual
                    understanding.
                  </p>

                  {/* Grounded Source Tags */}
                  <div className="flex flex-wrap items-center gap-1.5 sm:gap-2 pt-2 border-t border-[var(--border)]">
                    <span className="px-2 sm:px-2.5 py-0.5 sm:py-1 rounded-md bg-[var(--surface-base)] border border-[var(--border)] text-[9px] sm:text-[10px] font-mono text-[var(--foreground-muted)]">
                      PDF · p.48
                    </span>
                    <span className="px-2 sm:px-2.5 py-0.5 sm:py-1 rounded-md bg-[var(--surface-base)] border border-[var(--border)] text-[9px] sm:text-[10px] font-mono text-[var(--foreground-muted)]">
                      Video · 18:24
                    </span>
                    <span className="px-2 sm:px-2.5 py-0.5 sm:py-1 rounded-md bg-[var(--surface-base)] border border-[var(--border)] text-[9px] sm:text-[10px] font-mono text-[var(--foreground-muted)]">
                      Notes · Synthesis
                    </span>
                  </div>
                </motion.div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Section 04 — Follow every claim (EVIDENCE) */}
      <section className="py-16 sm:py-24 px-4 sm:px-8 lg:px-12 border-t border-[var(--border)] bg-[var(--surface-subtle)]/20">
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-16 items-center">
          {/* Left: Visual Spatial Canvas with Excerpt Card & Citation Connector */}
          <div className="lg:col-span-7 order-2 lg:order-1 w-full min-w-0">
            <div className="relative w-full min-h-[360px] sm:min-h-[440px] rounded-3xl border border-[var(--border)] bg-[var(--surface-base)] canvas-grid-bg p-4 sm:p-10 flex items-center justify-center overflow-hidden shadow-xl">
              <div className="relative w-full max-w-lg min-h-[260px] flex flex-col sm:block items-center justify-center gap-4 min-w-0">
                {/* SVG Connector Line (Visible on sm+) */}
                <svg
                  className="hidden sm:block absolute inset-0 w-full h-full pointer-events-none z-0"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <line
                    x1="220"
                    y1="130"
                    x2="320"
                    y2="170"
                    stroke="var(--border-hover)"
                    strokeWidth="1.2"
                    strokeDasharray="4 4"
                  />
                  <circle cx="220" cy="130" r="3" fill="#D6C2A3" />
                  <circle cx="320" cy="170" r="3" fill="#D6C2A3" />
                </svg>

                {/* Excerpt Card (Responsive width, centered on mobile) */}
                <motion.div
                  initial={{ opacity: 0, y: 15 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.6 }}
                  className="w-full max-w-[280px] sm:w-[280px] sm:absolute sm:top-4 sm:left-4 lg:left-8 rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] p-4 sm:p-5 shadow-2xl transform sm:-rotate-3 select-none z-10"
                >
                  <p className="text-[10px] font-mono tracking-widest text-[var(--accent-sand)] uppercase mb-2 sm:mb-3 font-medium">
                    PAGE 48
                  </p>
                  <p className="font-editorial italic text-xs sm:text-base text-[var(--foreground)] leading-relaxed mb-3 sm:mb-4">
                    “Context turns stored information into usable knowledge.”
                  </p>
                  <p className="text-[10px] text-[var(--foreground-muted)] font-mono">
                    The State of AI Report 2024
                  </p>
                </motion.div>

                {/* Citation Marker Pill */}
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  whileInView={{ opacity: 1, scale: 1 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.6, delay: 0.2 }}
                  className="w-full max-w-[280px] sm:w-auto sm:absolute sm:bottom-6 sm:right-4 lg:right-10 rounded-xl bg-[var(--surface-elevated)] border border-[var(--border)] p-3 sm:p-3.5 shadow-2xl flex items-center gap-3 z-10 hover:border-[var(--accent-sand)]/60 transition-colors cursor-pointer select-none"
                >
                  <div className="h-6 w-6 rounded-md bg-[var(--surface-base)] border border-[var(--border)] flex items-center justify-center text-xs font-mono font-medium text-[var(--accent-sand)] shrink-0">
                    1
                  </div>
                  <div>
                    <h5 className="text-xs font-medium text-[var(--foreground)]">
                      State of AI Report
                    </h5>
                    <p className="text-[10px] text-[var(--foreground-muted)] font-mono">
                      Page 48 · Exact match
                    </p>
                  </div>
                </motion.div>
              </div>
            </div>
          </div>

          {/* Right: Text */}
          <div className="lg:col-span-5 space-y-4 order-1 lg:order-2 min-w-0">
            <span className="text-[11px] font-mono tracking-widest text-[var(--accent-sand)] uppercase font-medium">
              04 / EVIDENCE
            </span>
            <h3 className="text-3xl sm:text-5xl font-light tracking-tight text-[var(--foreground)]">
              Follow every claim.
            </h3>
            <p className="text-sm sm:text-base text-[var(--foreground-muted)] leading-relaxed max-w-md font-normal">
              Citations lead back to the exact page or moment that supports an answer, so insight
              never becomes detached from evidence.
            </p>
          </div>
        </div>
      </section>

      {/* 4. CLOSING CTA — FULL-WIDTH WARM BEIGE SECTION */}
      <section
        id="principles"
        className="scroll-mt-20 w-full bg-[#EAE4DC] dark:bg-[#EAE4DC] text-[#141518] dark:text-[#141518] py-20 sm:py-36 px-4 sm:px-8 lg:px-12 text-center select-none transition-colors border-t border-[var(--border)]"
      >
        <div className="max-w-3xl mx-auto space-y-6 sm:space-y-8 min-w-0">
          <h2 className="text-2xl xs:text-3xl sm:text-5xl lg:text-[52px] font-light tracking-tight leading-[1.14]">
            Knowledge tools should help you think, <br />
            <span className="font-editorial italic font-normal block mt-2 text-[#5F4B34] dark:text-[#5F4B34]">
              not compete for your attention.
            </span>
          </h2>
        </div>
      </section>

      {/* 5. MINIMAL COMPACT FOOTER */}
      <footer className="w-full bg-[var(--background)] border-t border-[var(--border)] py-8 sm:py-10 px-4 sm:px-8 lg:px-12">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 sm:gap-6 text-xs text-[var(--foreground-muted)] text-center sm:text-left">
          <div className="flex items-center gap-2.5 sm:gap-3 flex-wrap justify-center">
            <BrandLogo size="sm" showWordmark={true} />
            <span className="text-[var(--foreground-muted)] hidden xs:inline">•</span>
            <span className="text-[11px] sm:text-xs">Thoughtful tools for curious minds.</span>
          </div>

          <div className="flex items-center flex-wrap justify-center sm:justify-end gap-4 sm:gap-6 font-mono text-[11px]">
            <a
              href="#how-it-works"
              onClick={(e) => handleScrollTo(e, 'how-it-works')}
              className="hover:text-[var(--foreground)] transition-colors"
            >
              How it works
            </a>
            <a
              href="#features"
              onClick={(e) => handleScrollTo(e, 'features')}
              className="hover:text-[var(--foreground)] transition-colors"
            >
              Features
            </a>
            <a
              href="#principles"
              onClick={(e) => handleScrollTo(e, 'principles')}
              className="hover:text-[var(--foreground)] transition-colors"
            >
              Principles
            </a>
            <span>© 2026 Evermind</span>
          </div>
        </div>
      </footer>

      {/* Floating Help Button (?) */}
      <button
        onClick={() => setShowHelpModal(true)}
        aria-label="Help and shortcuts"
        title="Help & Shortcuts"
        className="fixed bottom-5 right-5 z-40 h-8 w-8 rounded-full bg-[var(--surface-elevated)] hover:bg-[var(--surface-hover)] border border-[var(--border)] text-[var(--foreground-muted)] hover:text-[var(--foreground)] flex items-center justify-center text-xs font-semibold shadow-lg transition-all cursor-pointer"
      >
        ?
      </button>

      {/* Help Modal */}
      {showHelpModal && (
        <div
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150"
          onClick={() => setShowHelpModal(false)}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-[var(--border)] bg-[var(--surface-elevated)] text-[var(--foreground)] p-6 shadow-2xl space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-3 border-b border-[var(--border)]">
              <h3 className="text-base font-semibold text-[var(--foreground)] flex items-center gap-2">
                <HelpCircle className="h-4 w-4 text-[#D6C2A3]" />
                Evermind
              </h3>
              <button
                onClick={() => setShowHelpModal(false)}
                className="text-[var(--foreground-muted)] hover:text-[var(--foreground)] text-xs p-1"
              >
                ✕
              </button>
            </div>
            <div className="space-y-3 text-xs text-[var(--foreground-muted)]">
              <p>
                <strong className="text-[var(--foreground)]">Evermind:</strong> Grounded personal
                content library and verified AI assistant.
              </p>
              <div className="space-y-2 pt-2">
                <div className="flex justify-between py-1 border-b border-[var(--border)] font-mono text-[11px]">
                  <span>Sign In</span>
                  <span className="text-[var(--foreground-muted)]">/login</span>
                </div>
                <div className="flex justify-between py-1 border-b border-[var(--border)] font-mono text-[11px]">
                  <span>Dashboard</span>
                  <span className="text-[var(--foreground-muted)]">/dashboard</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
