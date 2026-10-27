'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import {
  Sun,
  Moon,
  Laptop,
  Trash2,
  AlertTriangle,
  Check,
  Loader2,
  Database,
  Layers,
  Sparkles
} from 'lucide-react';
import { ShellLayout } from '@/components/shell/shell-layout';
import { DeleteConfirmationModal } from '@/components/ui/delete-confirmation-modal';
import { useTheme } from '@/components/theme-provider';

export default function SettingsPage() {
  const router = useRouter();
  const { theme, setTheme } = useTheme();

  // Delete workspace permanently state
  const [isDeleteModalOpen, setIsDeleteModalOpen] = React.useState(false);
  const [isDeleting, setIsDeleting] = React.useState(false);
  const [deleteError, setDeleteError] = React.useState<string | null>(null);
  const [deleteSuccess, setDeleteSuccess] = React.useState(false);

  const handleDeleteWorkspace = async () => {
    setIsDeleting(true);
    setDeleteError(null);

    try {
      const res = await fetch('/api/v1/users/workspace/', {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || data.detail || 'Failed to delete workspace. Please try again.');
      }

      setDeleteSuccess(true);
      setIsDeleteModalOpen(false);

      // Broadcast workspace purge event across tabs and components
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('mediacompile:workspace-deleted'));
        window.dispatchEvent(new CustomEvent('mediacompile:content-deleted', { detail: { all: true } }));
      }

      // Smoothly navigate back to clean dashboard after 1.2s
      setTimeout(() => {
        router.push('/dashboard');
        router.refresh();
      }, 1200);
    } catch (err: any) {
      setDeleteError(err.message || 'An unexpected error occurred while deleting workspace.');
    } finally {
      setIsDeleting(false);
    }
  };

  const themeOptions = [
    {
      id: 'light',
      title: 'Light mode',
      description: 'Clean parchment and warm alabaster with dark charcoal text for daytime clarity.',
      icon: Sun,
      colorPreview: 'bg-[#faf8f5] text-[#141518] border-[rgba(20,21,24,0.15)]',
    },
    {
      id: 'dark',
      title: 'Dark mode',
      description: 'Deep obsidian near-black palette with subtle warm champagne accents for low-light focus.',
      icon: Moon,
      colorPreview: 'bg-[#10100F] text-[#F5F2EB] border-[#30302D]',
    },
    {
      id: 'system',
      title: 'System preference',
      description: 'Automatically adjust your appearance to match your operating system preferences.',
      icon: Laptop,
      colorPreview: 'bg-linear-to-r from-[#faf8f5] via-stone-400 to-[#10100F] text-foreground border-[var(--border)]',
    },
  ];

  return (
    <ShellLayout>
      <div className="max-w-4xl space-y-10 animate-in fade-in duration-200">
        {/* Header */}
        <div>
          <span className="text-[11px] font-mono tracking-widest text-[var(--accent-sand)] uppercase font-medium">
            PREFERENCES
          </span>
          <h1 className="text-2xl sm:text-3xl font-medium tracking-tight text-[var(--foreground)] mt-1">
            Settings
          </h1>
          <p className="text-xs sm:text-sm text-[var(--foreground-muted)] mt-1">
            Manage your visual appearance and workspace data lifecycle.
          </p>
        </div>

        {deleteSuccess && (
          <div className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-500 text-xs flex items-center gap-3">
            <Check className="h-4 w-4 shrink-0" />
            <span>Workspace permanently cleared. Redirecting to fresh dashboard...</span>
          </div>
        )}

        {/* SECTION 1: THEME */}
        <section aria-labelledby="theme-section-title" className="space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-[var(--border)]">
            <div>
              <h2 id="theme-section-title" className="text-base sm:text-lg font-medium text-[var(--foreground)]">
                Theme
              </h2>
              <p className="text-xs text-[var(--foreground-muted)] mt-0.5">
                Select your preferred color theme across the application.
              </p>
            </div>
            <div className="hidden sm:inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-[var(--surface-elevated)] border border-[var(--border)] text-[11px] font-mono text-[var(--accent-sand)]">
              <span>Current: {theme.toUpperCase()}</span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5 pt-1">
            {themeOptions.map((opt) => {
              const Icon = opt.icon;
              const isSelected = theme === opt.id;

              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setTheme(opt.id as any)}
                  className={`relative p-5 rounded-2xl border text-left flex flex-col justify-between transition-all cursor-pointer group select-none shadow-xs ${
                    isSelected
                      ? 'border-[var(--accent-sand)] bg-[var(--surface-elevated)] shadow-md ring-1 ring-[var(--accent-sand)]/30'
                      : 'border-[var(--border)] bg-[var(--surface-base)] hover:border-[var(--border-hover)] hover:bg-[var(--surface-elevated)]'
                  }`}
                  aria-pressed={isSelected}
                >
                  <div className="flex items-start justify-between w-full mb-4">
                    <div
                      className={`h-9 w-9 rounded-xl flex items-center justify-center transition-colors border ${
                        isSelected
                          ? 'bg-[var(--primary)] text-[var(--primary-foreground)] border-transparent'
                          : 'bg-[var(--surface-subtle)] text-[var(--foreground-muted)] border-[var(--border)] group-hover:text-[var(--foreground)]'
                      }`}
                    >
                      <Icon className="h-4 w-4" />
                    </div>

                    {isSelected && (
                      <span className="flex items-center gap-1 text-[11px] font-medium text-[var(--accent-sand)] bg-[var(--accent-sand-muted)] px-2 py-0.5 rounded-full border border-[var(--accent-sand)]/20">
                        <Check className="h-3 w-3 stroke-[2.5]" />
                        <span>Active</span>
                      </span>
                    )}
                  </div>

                  <div>
                    <h3 className="text-sm font-medium text-[var(--foreground)] mb-1">
                      {opt.title}
                    </h3>
                    <p className="text-xs text-[var(--foreground-muted)] leading-relaxed">
                      {opt.description}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        {/* SECTION 2: DELETE WORKSPACE PERMANENTLY */}
        <section aria-labelledby="danger-section-title" className="space-y-4 pt-4">
          <div className="pb-3 border-b border-[var(--border)]">
            <h2 id="danger-section-title" className="text-base sm:text-lg font-medium text-rose-500 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4" />
              <span>Delete workspace permanently</span>
            </h2>
            <p className="text-xs text-[var(--foreground-muted)] mt-0.5">
              Destructive action to erase all user-owned research content, collections, chats, and vector data.
            </p>
          </div>

          <div className="p-6 rounded-2xl border border-rose-500/25 bg-rose-500/5 dark:bg-rose-950/10 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="space-y-1.5 max-w-xl">
                <h3 className="text-sm font-semibold text-[var(--foreground)]">
                  Permanently delete all workspace data
                </h3>
                <p className="text-xs text-[var(--foreground-muted)] leading-relaxed">
                  This action permanently removes all documents, notes, saved URLs, MinIO storage files, collections,
                  chat history, memories, and pgvector embeddings. Your credentials will remain active so you can start
                  fresh with an empty workspace.
                </p>
              </div>

              <button
                type="button"
                onClick={() => {
                  setDeleteError(null);
                  setIsDeleteModalOpen(true);
                }}
                disabled={isDeleting}
                className="px-4 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-700 active:bg-rose-800 text-white text-xs font-semibold shrink-0 transition-colors cursor-pointer shadow-sm disabled:opacity-50 flex items-center justify-center gap-2"
              >
                <Trash2 className="h-3.5 w-3.5" />
                <span>Delete workspace permanently</span>
              </button>
            </div>
          </div>
        </section>

        {/* Dedicated Delete Confirmation Modal */}
        <DeleteConfirmationModal
          isOpen={isDeleteModalOpen}
          onClose={() => {
            if (!isDeleting) {
              setIsDeleteModalOpen(false);
              setDeleteError(null);
            }
          }}
          onConfirm={handleDeleteWorkspace}
          title="Delete this workspace?"
          eyebrow="IRREVERSIBLE ACTION"
          itemName="All personal content, files, chats & vectors"
          itemType="workspace"
          itemMeta="Complete Sovereign Reset"
          consequenceText="All saved documents, raw text, uploaded files, tags, collections, chat history, pgvector embeddings, and personal memories will be permanently erased. Your account credentials will be preserved so you can start fresh."
          warningText="This action is immediate and cannot be undone."
          isDeleting={isDeleting}
          errorMessage={deleteError}
          confirmLabel="Delete workspace permanently"
          cancelLabel="Keep workspace"
        />
      </div>
    </ShellLayout>
  );
}
