'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft,
  ArrowRight,
  Eye,
  EyeOff,
  Sparkles,
  AlertCircle,
  Loader2,
  Check
} from 'lucide-react';
import { signIn } from 'next-auth/react';

function RegisterForm() {
  const router = useRouter();

  const [name, setName] = React.useState('');
  const [email, setEmail] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [showPassword, setShowPassword] = React.useState(false);
  const [agreeTerms, setAgreeTerms] = React.useState(false);
  const [isLoading, setIsLoading] = React.useState(false);
  const [error, setError] = React.useState('');
  const [successMessage, setSuccessMessage] = React.useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isLoading) return;

    setError('');
    setSuccessMessage('');

    if (!name.trim()) {
      setError('Please provide your full name.');
      return;
    }

    if (!email.trim()) {
      setError('Please provide a valid email address.');
      return;
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }

    if (!agreeTerms) {
      setError('Please agree to the terms and privacy policy to continue.');
      return;
    }

    setIsLoading(true);

    try {
      const res = await fetch('/api/v1/users/register', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({
          name: name.trim(),
          email: email.trim().toLowerCase(),
          password,
        }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        const errorMsg =
          data?.error?.message ||
          data?.error ||
          data?.detail ||
          (res.status === 400
            ? 'An account with this email address already exists. Please sign in or use a different email.'
            : 'Registration could not be completed. Please try again.');
        setError(errorMsg);
        return;
      }

      setSuccessMessage('Account created successfully. Signing you in...');

      // Immediately establish session via NextAuth credentials provider
      const signInRes = await signIn('credentials', {
        email: email.trim().toLowerCase(),
        password,
        redirect: false,
      });

      if (signInRes?.error) {
        // Fallback: Account was created, navigate to login with confirmation
        router.push('/login?registered=true');
        return;
      }

      router.push('/dashboard');
      router.refresh();
    } catch {
      setError('Unable to reach the registration service. Please check your network connection.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="dark min-h-screen w-full grid grid-cols-1 lg:grid-cols-2 bg-[#121210] text-[#F5F5F0] selection:bg-[#2A2A28] selection:text-[#F5F5F0]">
      {/* =========================================================================
          LEFT PANEL — Editorial Brand Section (Matches Login Visual Identity)
          ========================================================================= */}
      <section className="relative hidden lg:flex flex-col justify-between p-10 xl:p-14 bg-[#24231F] text-[#F5F5F0] overflow-hidden select-none border-r border-[#1D1C19]">
        {/* Subtle decorative concentric arc in bottom background */}
        <div
          className="absolute -bottom-24 -left-24 w-[520px] h-[520px] rounded-full border border-white/[0.04] pointer-events-none"
          aria-hidden="true"
        />
        <div
          className="absolute -bottom-40 -left-40 w-[680px] h-[680px] rounded-full border border-white/[0.025] pointer-events-none"
          aria-hidden="true"
        />

        {/* Top Eyebrow */}
        <div className="flex items-center gap-2 relative z-10">
          <Sparkles className="h-3.5 w-3.5 text-[#C4A986]" />
          <span className="text-[11px] font-semibold tracking-widest text-[#B5B0A6] uppercase">
            YOUR KNOWLEDGE WORKSPACE
          </span>
        </div>

        {/* Middle: Editorial Quote & Supporting Text */}
        <div className="relative z-10 max-w-lg my-auto pt-6 pb-2">
          <h1 className="text-3xl xl:text-[40px] font-normal leading-[1.18] tracking-tight text-[#F7F6F2]">
            &ldquo;Your sovereign library for everything you learn, discover, and build.&rdquo;
          </h1>
          <p className="text-xs sm:text-sm text-[#A6A298] leading-relaxed mt-5 max-w-md">
            Bring together articles, PDFs, notes, and transcripts into one grounded intelligence environment.
          </p>

          {/* Layered Research Note Illustration */}
          <div className="relative mt-12 w-full max-w-sm h-64 select-none">
            {/* Back Note (taupe card tilted right with ruled lines) */}
            <div className="absolute top-2 left-10 w-52 h-56 rounded-2xl bg-[#7C776D]/60 border border-[#8E897E]/30 rotate-6 shadow-md p-4 flex flex-col gap-2 translate-x-4">
              <div className="w-12 h-1 bg-white/20 rounded-full mb-1" />
              <div className="w-full h-1 bg-white/10 rounded-full" />
              <div className="w-4/5 h-1 bg-white/10 rounded-full" />
              <div className="w-5/6 h-1 bg-white/10 rounded-full" />
            </div>

            {/* Front Note (clean warm off-white card tilted left) */}
            <div className="absolute top-0 left-0 w-60 rounded-2xl bg-[#FAF9F6] text-[#24231F] p-5 shadow-2xl -rotate-3 border border-[#EAE5DC]/80 space-y-3 z-10">
              <span className="text-[9px] font-bold tracking-widest text-[#8F8B82] uppercase block">
                RESEARCH NOTE
              </span>
              <p className="text-sm font-semibold leading-snug text-[#1F1E1B]">
                Ideas become useful when they connect.
              </p>
              <div className="space-y-1.5 pt-1">
                <div className="w-3/4 h-1 bg-[#EAE5DC] rounded-full" />
                <div className="w-1/2 h-1 bg-[#EAE5DC] rounded-full" />
              </div>
              <span className="text-[10px] text-[#8F8B82] mt-3 block">
                12 sources compiled
              </span>
            </div>

            {/* Floating Connection Found Notification Badge */}
            <div className="absolute bottom-2 right-2 rounded-2xl bg-white text-[#1F1E1B] p-3 shadow-[0_12px_32px_rgba(0,0,0,0.32)] flex items-center gap-3 border border-[#EAE6DF] z-20">
              <div className="w-7 h-7 rounded-xl bg-[#24231F] flex items-center justify-center text-[#EAE6DF] shrink-0">
                <Sparkles className="h-3.5 w-3.5" />
              </div>
              <div className="min-w-0 pr-1">
                <p className="text-xs font-semibold text-[#1F1E1B] leading-none">
                  Connection found
                </p>
                <p className="text-[10px] text-[#7A766F] leading-none mt-1">
                  3 sources share this theme
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom subtle copyright / descriptor */}
        <div className="relative z-10 pt-4 text-[10px] tracking-widest uppercase text-[#5A564E]">
          RESEARCH WORKSPACE &middot; EVERMIND
        </div>
      </section>

      {/* =========================================================================
          RIGHT PANEL — Sign-up Form (Visually Aligned with Login)
          ========================================================================= */}
      <section className="flex flex-col justify-between p-6 sm:p-10 lg:p-14 min-h-screen bg-[#121210] text-[#F5F5F0]">
        {/* Top Header: Back Link on left */}
        <div className="flex items-center justify-between">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-xs text-[#9A968E] hover:text-[#F5F5F0] transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Back to home</span>
          </Link>
        </div>

        {/* Centered Sign-Up Box */}
        <div className="w-full max-w-[390px] mx-auto my-auto py-8 space-y-6">
          {/* Eyebrow & Headings */}
          <div>
            <span className="text-[11px] font-bold tracking-widest text-[#9C978D] uppercase block">
              GET STARTED
            </span>
            <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight text-[#F5F5F0] mt-1.5">
              Create your account
            </h2>
            <p className="text-xs sm:text-sm text-[#9E9A91] mt-1">
              Start building your sovereign research library.
            </p>
          </div>

          {/* Status Banners */}
          {error && (
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/25 text-xs text-rose-400 flex items-center gap-2">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {successMessage && (
            <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/25 text-xs text-emerald-400 flex items-center gap-2">
              <Check className="h-4 w-4 shrink-0" />
              <span>{successMessage}</span>
            </div>
          )}

          {/* Registration Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Full Name */}
            <div>
              <label
                htmlFor="name"
                className="block text-xs font-medium text-[#E8E6E1] mb-1.5"
              >
                Full name
              </label>
              <input
                id="name"
                type="text"
                required
                autoComplete="name"
                placeholder="Alex Morgan"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={isLoading}
                className="w-full h-11 px-3.5 rounded-xl border border-[rgba(255,255,255,0.14)] bg-[#1C1C1A] text-xs sm:text-sm text-[#F5F5F0] placeholder-[#A49F96] focus:outline-hidden focus:border-[#F5F5F0] transition-colors shadow-2xs disabled:opacity-60"
              />
            </div>

            {/* Email Address */}
            <div>
              <label
                htmlFor="email"
                className="block text-xs font-medium text-[#E8E6E1] mb-1.5"
              >
                Email address
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                placeholder="alex@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isLoading}
                className="w-full h-11 px-3.5 rounded-xl border border-[rgba(255,255,255,0.14)] bg-[#1C1C1A] text-xs sm:text-sm text-[#F5F5F0] placeholder-[#A49F96] focus:outline-hidden focus:border-[#F5F5F0] transition-colors shadow-2xs disabled:opacity-60"
              />
            </div>

            {/* Password with Eye show/hide toggle */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label
                  htmlFor="password"
                  className="block text-xs font-medium text-[#E8E6E1]"
                >
                  Password
                </label>
                <span className="text-[10px] text-[#8C877E]">
                  Min. 8 characters
                </span>
              </div>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  required
                  autoComplete="new-password"
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isLoading}
                  className="w-full h-11 pl-3.5 pr-10 rounded-xl border border-[rgba(255,255,255,0.14)] bg-[#1C1C1A] text-xs sm:text-sm text-[#F5F5F0] placeholder-[#A49F96] focus:outline-hidden focus:border-[#F5F5F0] transition-colors shadow-2xs font-mono disabled:opacity-60"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#8C877E] hover:text-[#F5F5F0] transition-colors p-1"
                  title={showPassword ? 'Hide password' : 'Show password'}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
            </div>

            {/* Terms and Privacy Policy Checkbox */}
            <div className="pt-1">
              <label className="flex items-start gap-2.5 text-xs text-[#A6A299] cursor-pointer select-none">
                <input
                  type="checkbox"
                  required
                  checked={agreeTerms}
                  onChange={(e) => setAgreeTerms(e.target.checked)}
                  disabled={isLoading}
                  className="mt-0.5 h-3.5 w-3.5 rounded border-[#383734] bg-[#1C1C1A] text-white accent-white focus:ring-0 cursor-pointer shrink-0 disabled:opacity-60"
                />
                <span className="leading-snug">
                  I agree to the{' '}
                  <Link
                    href="/terms"
                    className="text-[#F5F5F0] underline underline-offset-2 hover:text-white"
                  >
                    Terms of Service
                  </Link>{' '}
                  and{' '}
                  <Link
                    href="/privacy"
                    className="text-[#F5F5F0] underline underline-offset-2 hover:text-white"
                  >
                    Privacy Policy
                  </Link>
                  .
                </span>
              </label>
            </div>

            {/* Primary Submit Button */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full h-11 mt-2 rounded-xl bg-[#F5F5F0] hover:bg-[#FFFFFF] text-[#141412] text-xs sm:text-sm font-medium transition-all shadow-xs flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin shrink-0" />
                  <span>Creating account...</span>
                </>
              ) : (
                <>
                  <span>Create account</span>
                  <ArrowRight className="h-4 w-4 ml-0.5" />
                </>
              )}
            </button>
          </form>

          {/* Already have an account link */}
          <p className="text-center text-xs text-[#9E9A91] pt-2">
            Already have an account?{' '}
            <Link
              href="/login"
              className="text-[#F5F5F0] font-medium hover:underline underline-offset-2 transition-colors"
            >
              Sign in
            </Link>
          </p>
        </div>

        {/* Bottom Footer Row with Copyright, Links, and Help Button */}
        <div className="flex items-center justify-between pt-6 border-t border-[rgba(255,255,255,0.06)] text-[11px] text-[#7A766E]">
          <span>&copy; {new Date().getFullYear()} Evermind</span>

          <div className="flex items-center gap-4">
            <Link
              href="/privacy"
              className="hover:text-[#F5F5F0] transition-colors"
            >
              Privacy
            </Link>
            <Link
              href="/terms"
              className="hover:text-[#F5F5F0] transition-colors"
            >
              Terms
            </Link>
            <button
              type="button"
              onClick={() => alert('Evermind Knowledge Workspace\n\nFor support or questions, reach out to support@evermind.io')}
              className="w-6 h-6 rounded-full bg-[#333330] text-[#F5F5F0] flex items-center justify-center font-semibold text-[11px] transition-transform hover:scale-105 cursor-pointer shadow-2xs"
              title="Help & Support"
              aria-label="Help & Support"
            >
              ?
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <React.Suspense fallback={<div className="dark min-h-screen bg-[#121210]" />}>
      <RegisterForm />
    </React.Suspense>
  );
}
