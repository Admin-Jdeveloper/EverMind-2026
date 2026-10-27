'use client';

import * as React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Copy, Check } from 'lucide-react';

interface FormattedMarkdownProps {
  content: string;
  className?: string;
}

/**
 * Pre-processes markdown to strip delimiter artifacts, reasoning tags,
 * convert raw HTML line breaks (<br>, <br/>, </br>) outside code blocks to Markdown newlines,
 * and remove orphaned malformed closing tags (e.g. stray '/>').
 */
function cleanMarkdownContent(raw: string): string {
  if (!raw) return '';

  let cleaned = raw;

  // 1. Strip <think>...</think> reasoning tags
  cleaned = cleaned.replace(/<think>[\s\S]*?<\/think>/gi, '');

  // 2. Strip delimiter sequences like ///*** or //*** or ***///
  cleaned = cleaned.replace(/\/{2,}\*{2,}/g, '');
  cleaned = cleaned.replace(/\*{2,}\/{2,}/g, '');
  cleaned = cleaned.replace(/^\/{3,}\s*$/gm, '');

  // 3. Process outside fenced code blocks to preserve legitimate JSX/HTML code samples
  const codeBlockPattern = /(```[\s\S]*?```)/g;
  const parts = cleaned.split(codeBlockPattern);

  for (let i = 0; i < parts.length; i++) {
    // Even indices are text outside code blocks
    if (i % 2 === 0) {
      let part = parts[i];

      // Convert raw <br>, <br/>, <br />, </br> into standard markdown double space + newline
      part = part.replace(/<\/?br\s*\/?>/gi, '  \n');

      // Remove stray isolated '/>' tags that aren't inside an HTML tag
      part = part.replace(/(?<!<[^>]{1,50})\/>/g, '');

      // Normalize multiple consecutive break lines
      part = part.replace(/\n{3,}/g, '\n\n');

      parts[i] = part;
    }
  }

  return parts.join('').trim();
}

function CodeBlock({ children, className }: { children: React.ReactNode; className?: string }) {
  const [copied, setCopied] = React.useState(false);
  const textContent = String(children).replace(/\n$/, '');

  const handleCopy = () => {
    navigator.clipboard.writeText(textContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const match = /language-(\w+)/.exec(className || '');
  const language = match ? match[1] : '';

  return (
    <div className="relative group my-3 rounded-xl overflow-hidden border border-[var(--border)] bg-[var(--surface-elevated)] font-mono text-xs shadow-xs max-w-full min-w-0">
      <div className="flex items-center justify-between px-3.5 py-1.5 bg-[var(--surface)] border-b border-[var(--border)] text-[11px] text-[var(--foreground-muted)]">
        <span className="font-semibold uppercase tracking-wider">{language || 'code'}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-[var(--foreground-muted)] hover:text-[var(--foreground)] transition-colors py-0.5 px-2 rounded-md bg-[var(--surface-hover)] cursor-pointer"
          title="Copy code"
          type="button"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3 text-emerald-500" />
              <span className="text-emerald-500 font-sans text-[11px]">Copied</span>
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" />
              <span className="font-sans text-[11px]">Copy</span>
            </>
          )}
        </button>
      </div>
      <div className="p-3 sm:p-4 overflow-x-auto text-[var(--foreground)] leading-relaxed max-w-full">
        <code className="block whitespace-pre font-mono text-[11px] sm:text-xs">{textContent}</code>
      </div>
    </div>
  );
}

export function FormattedMarkdown({ content, className = '' }: FormattedMarkdownProps) {
  const processed = React.useMemo(() => cleanMarkdownContent(content), [content]);

  return (
    <div className={`formatted-markdown text-[var(--foreground)] space-y-2.5 sm:space-y-3 leading-relaxed break-words [overflow-wrap:anywhere] min-w-0 max-w-full ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }]]}
        components={{
          h1: ({ children }) => (
            <h1 className="text-sm sm:text-base md:text-lg font-bold text-[var(--foreground)] mt-3 sm:mt-4 mb-1.5 sm:mb-2 pb-1 border-b border-[var(--border)] tracking-tight break-words">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-xs sm:text-sm md:text-base font-semibold text-[var(--foreground)] mt-3 sm:mt-3.5 mb-1 sm:mb-1.5 tracking-tight flex items-center gap-1.5 break-words">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-xs sm:text-sm font-semibold text-[var(--foreground)] mt-2.5 sm:mt-3 mb-1 break-words">
              {children}
            </h3>
          ),
          p: ({ children }) => (
            <p className="text-xs sm:text-sm leading-relaxed mb-2 last:mb-0 text-[var(--foreground)]/90 break-words [overflow-wrap:anywhere]">
              {children}
            </p>
          ),
          ul: ({ children }) => (
            <ul className="list-disc list-outside ml-3.5 sm:ml-4 space-y-1 my-1.5 sm:my-2 text-xs sm:text-sm text-[var(--foreground)]/90">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-outside ml-3.5 sm:ml-4 space-y-1 my-1.5 sm:my-2 text-xs sm:text-sm text-[var(--foreground)]/90">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="leading-relaxed pl-0.5 sm:pl-1 break-words [overflow-wrap:anywhere]">{children}</li>
          ),
          strong: ({ children }) => (
            <strong className="font-semibold text-[var(--foreground)]">{children}</strong>
          ),
          em: ({ children }) => (
            <em className="italic text-[var(--foreground)]/80">{children}</em>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-[var(--accent-sand)] bg-[var(--surface-subtle)]/70 px-3.5 py-2 my-2.5 text-xs text-[var(--foreground)]/90 rounded-r-xl break-words italic">
              {children}
            </blockquote>
          ),
          code: ({ inline, className, children, ...props }: React.ComponentPropsWithoutRef<'code'> & { inline?: boolean }) => {
            if (inline) {
              return (
                <code
                  className="px-1.5 py-0.5 rounded-md bg-[var(--surface-hover)] text-[var(--accent-sand)] dark:text-[#d4c3b3] font-mono text-[11px] sm:text-xs border border-[var(--border)] break-all"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return <CodeBlock className={className}>{children}</CodeBlock>;
          },
          table: ({ children }) => (
            <div className="my-3 overflow-x-auto max-w-full rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] shadow-2xs [scrollbar-width:thin]">
              <table className="w-full min-w-[320px] text-xs text-left border-collapse">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-[var(--surface-base)] border-b border-[var(--border)] text-[11px] font-semibold text-[var(--foreground)] tracking-wider">
              {children}
            </thead>
          ),
          tbody: ({ children }) => (
            <tbody className="divide-y divide-[var(--border)] bg-[var(--surface-elevated)]">
              {children}
            </tbody>
          ),
          tr: ({ children }) => (
            <tr className="hover:bg-[var(--surface-hover)]/70 transition-colors">{children}</tr>
          ),
          th: ({ children }) => (
            <th className="px-3.5 py-2.5 font-medium text-[var(--foreground)] border-b border-[var(--border)] whitespace-nowrap">{children}</th>
          ),
          td: ({ children }) => (
            <td className="px-3.5 py-2.5 text-[var(--foreground)]/90 leading-relaxed break-words">{children}</td>
          ),
          a: ({ href, children }) => {
            const isSafe = href && (href.startsWith('http://') || href.startsWith('https://') || href.startsWith('#') || href.startsWith('mailto:'));
            if (!isSafe) {
              return <span>{children}</span>;
            }
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sky-500 hover:text-sky-400 dark:text-sky-400 dark:hover:text-sky-300 underline underline-offset-2 transition-colors font-medium break-all"
              >
                {children}
              </a>
            );
          },
          hr: () => <hr className="my-3 border-[var(--border)]" />,
        }}
      >
        {processed}
      </ReactMarkdown>
    </div>
  );
}
