'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  Upload,
  Play,
  Sparkles,
  ArrowRight,
  FileText,
  Link as LinkIcon,
  StickyNote,
  Folder,
  MessageSquare,
  MoreHorizontal,
  Plus,
  ChevronRight,
  Loader2,
  ExternalLink,
  AlertCircle,
  RotateCcw
} from 'lucide-react';
import { ShellLayout } from '@/components/shell/shell-layout';
import { getCanonicalContentMeta, type CanonicalContentMeta } from '@/lib/content-utils';

interface CollectionItem {
  id: string;
  name: string;
  item_count: number;
  description?: string;
  updated_at?: string;
}

interface ChatSession {
  id: string;
  title: string;
  updated_at: string;
  message_count?: number;
}

const pastelBgPalette = [
  'bg-[#CDB59B] text-[#1e1a16]', // warm tan
  'bg-[#8F969E] text-[#16181b]', // muted slate
  'bg-[#9DAA94] text-[#161a15]', // sage
  'bg-[#B98A77] text-[#221612]', // terracotta
  'bg-[#C7BA99] text-[#1c1a14]', // khaki
];

export default function DashboardPage() {
  const router = useRouter();
  const [recentRawItems, setRecentRawItems] = React.useState<any[]>([]);
  const [collections, setCollections] = React.useState<CollectionItem[]>([]);
  const [recentChats, setRecentChats] = React.useState<ChatSession[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [fetchError, setFetchError] = React.useState<string | null>(null);
  const [isAuthError, setIsAuthError] = React.useState(false);

  // Trigger quick add modal
  const openQuickAdd = (tab?: 'document' | 'link' | 'note') => {
    window.dispatchEvent(new CustomEvent('mediacompile:open-quick-add', { detail: { tab } }));
  };

  const loadData = React.useCallback(async (silent = false) => {
    if (!silent) setIsLoading(true);
    try {
      const [itemsRes, collectionsRes, sessionsRes] = await Promise.all([
        fetch('/api/v1/content/items/?ordering=-created_at', { cache: 'no-store' }),
        fetch('/api/v1/content/collections/', { cache: 'no-store' }),
        fetch('/api/v1/chat/sessions/', { cache: 'no-store' }),
      ]);

      if (itemsRes.ok) {
        setFetchError(null);
        setIsAuthError(false);
        const itemsData = await itemsRes.json();
        const list = Array.isArray(itemsData) ? itemsData : itemsData.results || [];
        setRecentRawItems(list.slice(0, 6));
      } else {
        if (itemsRes.status === 401 || itemsRes.status === 403) {
          setIsAuthError(true);
          setFetchError('Session expired or unauthorized.');
        } else {
          setFetchError('Unable to load content library items.');
        }
      }

      if (collectionsRes.ok) {
        const colData = await collectionsRes.json();
        const colList = Array.isArray(colData) ? colData : colData.results || [];
        setCollections(colList.slice(0, 4));
      }

      if (sessionsRes.ok) {
        const sessData = await sessionsRes.json();
        const sessList = Array.isArray(sessData) ? sessData : sessData.results || [];
        setRecentChats(sessList.slice(0, 4));
      }
    } catch (err: any) {
      console.error('Failed to load dashboard:', err);
      setFetchError(err?.message || 'Network error while loading dashboard.');
    } finally {
      if (!silent) setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadData();
  }, [loadData]);

  // Targeted bounded polling for any in-progress indexing items in recently added list
  const inProgressIdsKey = React.useMemo(() => {
    return recentRawItems
      .filter((item) => {
        const s = (item.ingestion_status || '').toLowerCase();
        return s && !['completed', 'partial', 'failed'].includes(s);
      })
      .map((i) => i.id)
      .sort()
      .join(',');
  }, [recentRawItems]);

  React.useEffect(() => {
    if (!inProgressIdsKey) return;
    const targetIds = inProgressIdsKey.split(',').filter(Boolean);
    if (targetIds.length === 0) return;

    let pollAttempts = 0;
    const maxPollAttempts = 25; // 25 attempts * 4s = 100s max

    const interval = setInterval(async () => {
      pollAttempts += 1;
      if (pollAttempts > maxPollAttempts) {
        clearInterval(interval);
        return;
      }

      try {
        const statusPromises = targetIds.map(async (id) => {
          const res = await fetch(`/api/v1/content/items/${id}/status/`, { cache: 'no-store' });
          if (res.ok) {
            return await res.json();
          }
          return null;
        });

        const results = await Promise.all(statusPromises);
        let anyTerminal = false;

        setRecentRawItems((prev) =>
          prev.map((item) => {
            const update = results.find((r) => r && r.id === item.id);
            if (update) {
              const newStatus = update.ingestion_status;
              if (['completed', 'partial', 'failed'].includes((newStatus || '').toLowerCase())) {
                anyTerminal = true;
              }
              return {
                ...item,
                ingestion_status: newStatus,
                error_message: update.error_message,
                chunk_count: update.chunk_count ?? item.chunk_count,
              };
            }
            return item;
          })
        );

        if (anyTerminal) {
          loadData(true);
        }
      } catch (err) {
        // Silently tolerate transient poll errors
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [inProgressIdsKey, loadData]);

  // Listen for items added via QuickAddModal
  React.useEffect(() => {
    const handleItemAdded = () => loadData(true);
    window.addEventListener('library-item-added', handleItemAdded);
    return () => window.removeEventListener('library-item-added', handleItemAdded);
  }, [loadData]);

  React.useEffect(() => {
    // Listen for items deleted elsewhere to immediately remove from dashboard without refresh
    const handleContentDeleted = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.id) {
        setRecentRawItems((prev) => prev.filter((i) => i.id !== detail.id));
      }
    };

    // Listen for collections deleted elsewhere
    const handleCollectionDeleted = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.id) {
        setCollections((prev) => prev.filter((c) => c.id !== detail.id));
      }
    };

    // Listen for collections created elsewhere
    const handleCollectionCreated = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.id) {
        setCollections((prev) => [
          {
            id: String(detail.id),
            name: detail.name,
            description: detail.description,
            item_count: detail.item_count || 0,
            updated_at: detail.updated_at || new Date().toISOString(),
          },
          ...prev,
        ]);
      }
    };

    // Listen for collections updated elsewhere
    const handleCollectionUpdated = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.id) {
        setCollections((prev) =>
          prev.map((c) =>
            c.id === detail.id
              ? {
                  ...c,
                  name: detail.name ?? c.name,
                  description: detail.description ?? c.description,
                  item_count: detail.item_count ?? c.item_count,
                  updated_at: detail.updated_at ?? c.updated_at,
                }
              : c
          )
        );
      }
    };

    // Listen for chats deleted elsewhere
    const handleChatDeleted = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.id) {
        setRecentChats((prev) => prev.filter((chat) => chat.id !== detail.id));
      }
    };

    window.addEventListener('mediacompile:content-deleted', handleContentDeleted);
    window.addEventListener('mediacompile:collection-deleted', handleCollectionDeleted);
    window.addEventListener('mediacompile:collection-created', handleCollectionCreated);
    window.addEventListener('mediacompile:collection-updated', handleCollectionUpdated);
    window.addEventListener('mediacompile:chat-deleted', handleChatDeleted);

    return () => {
      window.removeEventListener('mediacompile:content-deleted', handleContentDeleted);
      window.removeEventListener('mediacompile:collection-deleted', handleCollectionDeleted);
      window.removeEventListener('mediacompile:collection-created', handleCollectionCreated);
      window.removeEventListener('mediacompile:collection-updated', handleCollectionUpdated);
      window.removeEventListener('mediacompile:chat-deleted', handleChatDeleted);
    };
  }, []);

  return (
    <ShellLayout>
      <div className="space-y-8 animate-in fade-in duration-200">
        {/* Top Header Row */}
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-medium tracking-tight text-[var(--foreground)]">
              Dashboard
            </h1>
            <p className="text-xs sm:text-sm text-[var(--muted-foreground)] mt-1">
              Continue organizing your knowledge library, or ask questions grounded strictly across your saved content.
            </p>
          </div>

          <button
            onClick={() => openQuickAdd()}
            className="self-start sm:self-auto px-4 py-2 rounded-lg bg-[var(--primary)] hover:opacity-90 text-[var(--primary-foreground)] text-xs font-medium flex items-center gap-2 transition-colors cursor-pointer shadow-xs"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>Add Content</span>
          </button>
        </div>

        {/* Explore Actions Header */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 py-1">
          <div className="max-w-xl space-y-2">
            <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight text-[var(--foreground)]">
              What would you like to explore?
            </h2>
            <p className="text-sm text-[var(--muted-foreground)] leading-relaxed">
              Add documents, links, or notes to your sovereign library, or start a grounded conversation with your verified sources.
            </p>
          </div>

          {/* Unified Quick Actions: One Add Content Action + Ask Library */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full lg:w-auto">
            {/* Unified Action 1: Add Content */}
            <button
              onClick={() => openQuickAdd()}
              className="bg-[var(--surface-elevated)] hover:bg-[var(--surface-hover)] border border-[var(--border)] p-4 rounded-2xl flex flex-col justify-between transition-all cursor-pointer group min-h-[110px] w-full sm:w-52 select-none text-left shadow-xs hover:-translate-y-0.5"
            >
              <div className="h-8 w-8 rounded-xl bg-[var(--surface-base)] border border-[var(--border)] flex items-center justify-center text-[var(--foreground)]">
                <Plus className="h-4 w-4 text-[var(--accent-sand)]" />
              </div>
              <div className="mt-3">
                <p className="font-semibold text-xs text-[var(--foreground)]">Add Content</p>
                <p className="text-xs text-[var(--muted-foreground)] mt-0.5">Documents, Links & Notes</p>
              </div>
              <div className="mt-2 flex justify-end">
                <ArrowRight className="h-3.5 w-3.5 text-[var(--muted-foreground)] group-hover:translate-x-1 group-hover:text-[var(--foreground)] transition-all" />
              </div>
            </button>

            {/* Action 2: Ask Library */}
            <Link
              href="/chat"
              className="bg-[var(--surface-elevated)] hover:bg-[var(--surface-hover)] border border-[var(--border)] p-4 rounded-2xl flex flex-col justify-between transition-all cursor-pointer group min-h-[110px] w-full sm:w-52 select-none shadow-xs hover:-translate-y-0.5"
            >
              <div className="h-8 w-8 rounded-xl bg-[var(--surface-base)] border border-[var(--border)] flex items-center justify-center text-[var(--foreground)]">
                <Sparkles className="h-4 w-4 text-[var(--accent-sand)]" />
              </div>
              <div className="mt-3">
                <p className="font-semibold text-xs text-[var(--foreground)]">Ask Library</p>
                <p className="text-xs text-[var(--muted-foreground)] mt-0.5">Grounded RAG assistant</p>
              </div>
              <div className="mt-2 flex justify-end">
                <ArrowRight className="h-3.5 w-3.5 text-[var(--muted-foreground)] group-hover:translate-x-1 group-hover:text-[var(--foreground)] transition-all" />
              </div>
            </Link>
          </div>
        </div>

        {/* 2-Column Main Layout (Left: Recently Added + Conversations | Right: Collections + Processing) */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column (2/3) */}
          <div className="lg:col-span-2 space-y-6">
            {/* Recently added */}
            <div className="rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-medium text-sm text-[var(--foreground)]">Recently added</h3>
                <Link
                  href="/library"
                  className="text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] flex items-center gap-1 transition-colors"
                >
                  View library <ArrowRight className="h-3 w-3" />
                </Link>
              </div>

              {isLoading ? (
                <div className="py-8 text-center text-xs text-[var(--muted-foreground)] flex items-center justify-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading content...
                </div>
              ) : fetchError ? (
                <div className="py-6 px-4 text-center text-xs text-[var(--muted-foreground)] rounded-xl border border-rose-500/20 bg-rose-500/5 space-y-2">
                  <div className="flex items-center justify-center gap-1.5 text-rose-500 font-medium">
                    <AlertCircle className="h-4 w-4" />
                    <span>Failed to load content</span>
                  </div>
                  <p className="text-[11px] text-[var(--muted-foreground)]">{fetchError}</p>
                  <button
                    onClick={() => loadData()}
                    className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-[var(--surface-base)] border border-[var(--border)] text-xs hover:bg-[var(--surface-hover)] text-[var(--foreground)] transition-colors cursor-pointer"
                  >
                    <RotateCcw className="h-3 w-3" />
                    Retry
                  </button>
                </div>
              ) : recentRawItems.length === 0 ? (
                <div className="py-8 text-center text-xs text-[var(--muted-foreground)]">
                  No content added yet. Use &ldquo;Add Content&rdquo; above to start.
                </div>
              ) : (
                <div className="divide-y divide-[var(--border)]">
                  {recentRawItems.map((item, index) => {
                    const meta: CanonicalContentMeta = getCanonicalContentMeta(item);
                    const bgClass = pastelBgPalette[index % pastelBgPalette.length];

                    return (
                      <div
                        key={item.id}
                        className="py-2.5 px-2 rounded-xl hover:bg-[var(--surface-subtle)] flex items-center justify-between gap-3 transition-colors group"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          {/* Pastel icon box */}
                          <div
                            className={`h-8 w-8 rounded-lg ${bgClass} flex items-center justify-center shrink-0 shadow-xs`}
                          >
                            {meta.primaryType === 'Document' && <FileText className="h-4 w-4" />}
                            {meta.primaryType === 'Link' && <LinkIcon className="h-4 w-4" />}
                            {meta.primaryType === 'Note' && <StickyNote className="h-4 w-4" />}
                          </div>
                          <div className="min-w-0">
                            <Link
                              href={`/library?highlight=${item.id}`}
                              className="text-xs font-medium text-[var(--foreground)] group-hover:underline transition-colors truncate block"
                            >
                              {meta.title}
                            </Link>
                            <p className="text-xs text-[var(--muted-foreground)] truncate mt-0.5">
                              {item.collection_name || 'General Library'}
                            </p>
                          </div>
                        </div>

                        {/* Metadata row with real statistics */}
                        <div className="flex items-center gap-3 shrink-0">
                          <span className="px-2 py-0.5 rounded text-xs font-mono text-[var(--muted-foreground)] bg-[var(--surface-subtle)] border border-[var(--border)]">
                            {meta.primaryType}
                          </span>
                          {meta.secondaryBadge && (
                            <span className="text-xs text-[var(--muted-foreground)] font-mono hidden sm:inline">
                              {meta.secondaryBadge}
                            </span>
                          )}
                          {item.ingestion_status && item.ingestion_status !== 'completed' && (
                            <span className="px-2 py-0.5 rounded-full text-[11px] font-medium border border-[var(--border)] bg-[var(--surface-subtle)] text-[var(--foreground-muted)] flex items-center gap-1">
                              {item.ingestion_status === 'failed' ? (
                                <span className="text-[#8C3A3A] dark:text-[#C58B8B]">Failed</span>
                              ) : item.ingestion_status === 'partial' ? (
                                <span className="text-[#78644A] dark:text-[#CDB59B]">Partial</span>
                              ) : (
                                <>
                                  <Loader2 className="h-2.5 w-2.5 animate-spin" />
                                  <span>Indexing...</span>
                                </>
                              )}
                            </span>
                          )}
                          {meta.statBadge && (
                            <span className="text-xs text-[var(--muted-foreground)] font-mono hidden md:inline">
                              {meta.statBadge}
                            </span>
                          )}
                          <Link
                            href={`/library?highlight=${item.id}`}
                            className="p-1 rounded text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
                            title="View in library"
                          >
                            <MoreHorizontal className="h-4 w-4" />
                          </Link>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Recent conversations */}
            <div className="rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-medium text-sm text-[var(--foreground)]">Recent conversations</h3>
                <Link
                  href="/chat"
                  className="text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] flex items-center gap-1 transition-colors"
                >
                  Open chat <ArrowRight className="h-3 w-3" />
                </Link>
              </div>

              {recentChats.length === 0 ? (
                <div className="py-6 text-center text-xs text-[var(--muted-foreground)]">
                  No conversations yet. Ask your library to start grounded research.
                </div>
              ) : (
                <div className="divide-y divide-[var(--border)]">
                  {recentChats.map((chat) => (
                    <Link
                      key={chat.id}
                      href={`/chat`}
                      className="py-2.5 px-2 rounded-xl hover:bg-[var(--surface-subtle)] flex items-center justify-between gap-3 transition-colors group block"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="h-7 w-7 rounded-lg bg-[var(--surface-subtle)] flex items-center justify-center text-[var(--muted-foreground)] shrink-0">
                          <MessageSquare className="h-3.5 w-3.5" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-[var(--foreground)] group-hover:underline truncate">
                            {chat.title || 'Knowledge retrieval conversation'}
                          </p>
                          <p className="text-xs text-[var(--muted-foreground)] mt-0.5">
                            Grounded research conversation
                          </p>
                        </div>
                      </div>

                      <span className="text-[11px] text-[var(--muted-foreground)] shrink-0">
                        {chat.updated_at
                          ? new Date(chat.updated_at).toLocaleDateString('en-US', { weekday: 'short' })
                          : 'Recent'}
                      </span>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Right Column (1/3) */}
          <div className="space-y-6">
            {/* Collections Box */}
            <div className="rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-medium text-sm text-[var(--foreground)]">Collections</h3>
                <Link
                  href="/collections"
                  className="text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] flex items-center gap-1 transition-colors"
                >
                  View all <ArrowRight className="h-3 w-3" />
                </Link>
              </div>

              {collections.length > 0 ? (
                <div className="divide-y divide-[var(--border)]">
                  {collections.map((col, idx) => {
                    const iconBg = idx === 0 ? 'bg-[#CDB59B] text-[#1e1a16]' : 'bg-[#9DAA94] text-[#161a15]';
                    return (
                      <Link
                        key={col.id}
                        href={`/collections`}
                        className="py-2.5 px-2 rounded-xl hover:bg-[var(--surface-subtle)] flex items-center justify-between gap-3 transition-colors group block"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <div className={`h-8 w-8 rounded-lg ${iconBg} flex items-center justify-center shrink-0`}>
                            <Folder className="h-4 w-4" />
                          </div>
                          <div className="min-w-0">
                            <p className="text-xs font-medium text-[var(--foreground)] truncate">{col.name}</p>
                            <p className="text-xs text-[var(--muted-foreground)] mt-0.5">{col.item_count || 0} items</p>
                          </div>
                        </div>

                        <ChevronRight className="h-4 w-4 text-[var(--muted-foreground)] group-hover:text-[var(--foreground)] transition-colors shrink-0" />
                      </Link>
                    );
                  })}
                </div>
              ) : (
                <div className="py-4 text-center text-xs text-[var(--muted-foreground)]">
                  No collections created yet.
                </div>
              )}

              <Link
                href="/collections"
                className="w-full py-2.5 rounded-xl border border-[var(--border)] hover:bg-[var(--surface-subtle)] text-xs text-[var(--foreground)] font-medium flex items-center justify-center gap-2 transition-colors block text-center"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>New collection</span>
              </Link>
            </div>
          </div>
        </div>
      </div>
    </ShellLayout>
  );
}
