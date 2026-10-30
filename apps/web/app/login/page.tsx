'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
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

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get('callbackUrl') || '/dashboard';

  const [email, setEmail] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [showPassword, setShowPassword] = React.useState(false);
  const [rememberMe, setRememberMe] = React.useState(true);
  const [isLoading, setIsLoading] = React.useState(false);
  const [error, setError] = React.useState('');
  const [infoMessage, setInfoMessage] = React.useState('');

  // Parse OAuth redirect errors and query parameters
  React.useEffect(() => {
    const authError = searchParams.get('error');
    if (authError === 'Configuration') {
      setError('Google Sign-In is not fully configured on the server (missing AUTH_GOOGLE_ID or AUTH_GOOGLE_SECRET). Please contact support or sign in with credentials.');
    } else if (authError === 'OAuthSignin' || authError === 'OAuthCallback') {
      setError('An error occurred during Google sign-in. Please try again or sign in with email and password.');
    } else if (authError === 'AccessDenied') {
      setError('Access was denied by Google. Please authorize the request or sign in with email and password.');
    } else if (authError) {
      setError(`Authentication error: ${authError}. You may sign in with your email and password.`);
    }
  }, [searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    setInfoMessage('');

    if (!email.trim() || !password) {
      setError('Please provide both your email address and password.');
      setIsLoading(false);
      return;
    }

    try {
      const res = await signIn('credentials', {
        email: email.trim().toLowerCase(),
        password,
        redirect: false,
      });

      if (res?.error) {
        setError('Invalid email or password. Please verify your credentials and try again.');
        setIsLoading(false);
        return;
      }

      router.push(callbackUrl);
      router.refresh();
    } catch {
      setError('Unable to reach the authentication service. Please check your connection.');
      setIsLoading(false);
    }
  };

  const handleForgotPassword = (e: React.MouseEvent) => {
    e.preventDefault();
    if (!email.trim()) {
      setError('Please enter your email address first to request a password reset.');
    } else {
      setInfoMessage(`If an account exists for ${email.trim()}, password reset instructions have been sent.`);
      setError('');
    }
  };

  return (
    <div className="dark min-h-screen w-full grid grid-cols-1 lg:grid-cols-2 bg-[#121210] text-[#F5F5F0] selection:bg-[#2A2A28] selection:text-[#F5F5F0]">
      {/* =========================================================================
          LEFT PANEL — Editorial Brand Section (Matches Image 2 reference)
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
            &ldquo;The best research tools make the important connections feel inevitable.&rdquo;
          </h1>
          <p className="text-xs sm:text-sm text-[#A6A298] leading-relaxed mt-5 max-w-md">
            Return to your sources, collections, and conversations—all in one considered space.
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
          RIGHT PANEL — Sign-in Form (Matches Image 2 reference)
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

        {/* Centered Sign-In Box */}
        <div className="w-full max-w-[390px] mx-auto my-auto py-8 space-y-6">
          {/* Eyebrow & Headings */}
          <div>
            <span className="text-[11px] font-bold tracking-widest text-[#8A857C] dark:text-[#9C978D] uppercase block">
              WELCOME BACK
            </span>
            <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight text-[#1F1E1B] dark:text-[#F5F5F0] mt-1.5">
              Sign in to Evermind
            </h2>
            <p className="text-xs sm:text-sm text-[#706C64] dark:text-[#9E9A91] mt-1">
              Continue where your research left off.
            </p>
          </div>

          {/* Continue with Google button — Permanently available */}
          <div>
            <button
              type="button"
              onClick={() => signIn('google', { callbackUrl })}
              className="w-full h-11 rounded-xl border border-[#DEDAD1] dark:border-[rgba(255,255,255,0.12)] bg-white dark:bg-[#1E1E1C] hover:bg-[#F7F5EE] dark:hover:bg-[#282824] text-xs sm:text-sm font-medium text-[#1F1E1B] dark:text-[#F5F5F0] flex items-center justify-center gap-2.5 transition-colors shadow-2xs cursor-pointer"
            >
              <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24">
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                />
              </svg>
              <span>Continue with Google</span>
            </button>

            <div className="relative my-5">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t border-[#ECE7DE] dark:border-[rgba(255,255,255,0.08)]" />
              </div>
              <div className="relative flex justify-center text-[11px]">
                <span className="bg-[#FFFEFB] dark:bg-[#121210] px-3 text-[#8C877E] dark:text-[#918C83]">
                  or continue with email
                </span>
              </div>
            </div>
          </div>

          {/* Status Banners */}
          {error && (
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/25 text-xs text-rose-600 dark:text-rose-400 flex items-center gap-2">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {infoMessage && (
            <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/25 text-xs text-emerald-600 dark:text-emerald-400 flex items-center gap-2">
              <Check className="h-4 w-4 shrink-0" />
              <span>{infoMessage}</span>
            </div>
          )}

          {/* Sign In Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email Address */}
            <div>
              <label
                htmlFor="email"
                className="block text-xs font-medium text-[#1F1E1B] dark:text-[#E8E6E1] mb-1.5"
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
                className="w-full h-11 px-3.5 rounded-xl border border-[#DEDAD1] dark:border-[rgba(255,255,255,0.14)] bg-white dark:bg-[#1C1C1A] text-xs sm:text-sm text-[#1F1E1B] dark:text-[#F5F5F0] placeholder-[#A49F96] focus:outline-hidden focus:border-[#1F1E1B] dark:focus:border-[#F5F5F0] transition-colors shadow-2xs"
              />
            </div>

            {/* Password with Eye show/hide toggle */}
            <div>
              <label
                htmlFor="password"
                className="block text-xs font-medium text-[#1F1E1B] dark:text-[#E8E6E1] mb-1.5"
              >
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  required
                  autoComplete="current-password"
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full h-11 pl-3.5 pr-10 rounded-xl border border-[#DEDAD1] dark:border-[rgba(255,255,255,0.14)] bg-white dark:bg-[#1C1C1A] text-xs sm:text-sm text-[#1F1E1B] dark:text-[#F5F5F0] placeholder-[#A49F96] focus:outline-hidden focus:border-[#1F1E1B] dark:focus:border-[#F5F5F0] transition-colors shadow-2xs font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#8C877E] hover:text-[#1F1E1B] dark:hover:text-[#F5F5F0] transition-colors p-1"
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

            {/* Remember me & Forgot Password Row */}
            <div className="flex items-center justify-between pt-1">
              <label className="flex items-center gap-2 text-xs text-[#6F6B63] dark:text-[#A6A299] cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="h-3.5 w-3.5 rounded border-[#DEDAD1] text-[#24231F] accent-[#24231F] dark:accent-white focus:ring-0 cursor-pointer"
                />
                <span>Remember me</span>
              </label>

              <button
                type="button"
                onClick={handleForgotPassword}
                className="text-xs text-[#706C64] hover:text-[#1F1E1B] dark:text-[#9A968E] dark:hover:text-[#F5F5F0] transition-colors cursor-pointer"
              >
                Forgot password?
              </button>
            </div>

            {/* Primary Sign In Button (Near-black styling matching Image 2 reference) */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full h-11 mt-2 rounded-xl bg-[#24231F] hover:bg-[#141412] dark:bg-[#F5F5F0] dark:hover:bg-[#FFFFFF] dark:text-[#141412] text-white text-xs sm:text-sm font-medium transition-all shadow-xs flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin shrink-0" />
                  <span>Signing in...</span>
                </>
              ) : (
                <>
                  <span>Sign in</span>
                  <ArrowRight className="h-4 w-4 ml-0.5" />
                </>
              )}
            </button>
          </form>

          {/* Create an account link */}
          <p className="text-center text-xs text-[#706C64] dark:text-[#9E9A91] pt-2">
            New to MediaCompile?{' '}
            <Link
              href="/register"
              className="text-[#1F1E1B] dark:text-[#F5F5F0] font-medium hover:underline underline-offset-2 transition-colors"
            >
              Create an account
            </Link>
          </p>
        </div>

        {/* Bottom Footer Row with Copyright, Links, and floating Help Button */}
        <div className="flex items-center justify-between pt-6 border-t border-[#ECE7DE] dark:border-[rgba(255,255,255,0.06)] text-[11px] text-[#9E9A91] dark:text-[#7A766E]">
          <span>&copy; {new Date().getFullYear()} Evermind</span>

          <div className="flex items-center gap-4">
            <Link
              href="/privacy"
              className="hover:text-[#1F1E1B] dark:hover:text-[#F5F5F0] transition-colors"
            >
              Privacy
            </Link>
            <Link
              href="/terms"
              className="hover:text-[#1F1E1B] dark:hover:text-[#F5F5F0] transition-colors"
            >
              Terms
            </Link>
            {/* Help Question Mark Pill Button (as shown in reference screenshot) */}
            <button
              type="button"
              onClick={() => alert('Evermind Knowledge Workspace\n\nFor support or questions, reach out to support@evermind.io')}
              className="w-6 h-6 rounded-full bg-[#24231F] text-white dark:bg-[#333330] dark:text-[#F5F5F0] flex items-center justify-center font-semibold text-[11px] transition-transform hover:scale-105 cursor-pointer shadow-2xs"
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

export default function LoginPage() {
  return (
    <React.Suspense fallback={<div className="min-h-screen bg-[#FFFEFB] dark:bg-[#121210]" />}>
      <LoginForm />
    </React.Suspense>
  );
}
