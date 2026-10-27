import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';
import { Providers } from '@/components/providers';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: 'Evermind — Grounded Personal Content Library & RAG AI',
  description: 'Evermind aggregates permitted documents, notes, bookmarks, and transcripts into a sovereign, searchable repository with verifiable, grounded AI research assistance.',
  applicationName: 'Evermind',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('mc_theme');var d=window.matchMedia('(prefers-color-scheme: dark)').matches;var r=(t==='light')?'light':(t==='dark')?'dark':(d?'dark':'light');document.documentElement.classList.remove('light','dark');document.documentElement.classList.add(r);}catch(e){}})();`,
          }}
        />
      </head>
      <body className="min-h-full flex flex-col selection:bg-amber-500/20 selection:text-amber-200">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
