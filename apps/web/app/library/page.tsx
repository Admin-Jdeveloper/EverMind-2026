'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  Search,
  LayoutGrid,
  List as ListIcon,
  Upload,
  Link as LinkIcon,
  FileText,
  UploadCloud,
  Folder,
  ArrowRight,
  MoreHorizontal,
  Trash2,
  Edit2,
  Eye,
  RotateCcw,
  Sparkles,
  Loader2,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  Plus,
  Download,
  Check,
  X
} from 'lucide-react';
import { ShellLayout } from '@/components/shell/shell-layout';
import { Modal } from '@/components/ui/modal';
import { DeleteConfirmationModal } from '@/components/ui/delete-confirmation-modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  getCanonicalContentMeta,
  CanonicalType,
  FormattedContentMeta
} from '@/lib/content-utils';

export interface LibraryItem {
  id: string;
  title: string;
  content_type: string;
  source_url?: string;
  file_key?: string;
  summary: string;
  raw_text?: string;
  collection: string;
  collection_id?: string | null;
  tags: string[];
  chunk_count: number;
  date: string;
  status: string;
  error_message?: string;
  metadata?: Record<string, any>;
  meta: FormattedContentMeta;
}

export interface ItemDetail {
  id: string;
  title: string;
  source_url: string;
  content_type: string;
  summary: string;
  raw_text: string;
  file_key?: string;
  ingestion_status: string;
  error_message: string;
  collection: { id: string; name: string } | null;
  tags_list: string[];
  chunk_count: number;
  chunks: Array<{
    id: string;
    chunk_index: number;
    text: string;
  }>;
  metadata?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

const pastelPalette = [
  'bg-[#CDB59B] text-[#1e1a16]', // warm sand / ochre
  'bg-[#8F969E] text-[#16181b]', // dusty slate
  'bg-[#9DAA94] text-[#161a15]', // dusty olive sage
  'bg-[#C7BA99] text-[#1c1a14]', // light khaki / wheat
  'bg-[#B98A77] text-[#221612]', // dusty terracotta
  'bg-[#A8A693] text-[#1c1a14]', // muted taupe
];

function mapApiItem(item: any): LibraryItem {
  const meta = getCanonicalContentMeta(item);

  const dateStr = item.created_at
    ? (() => {
        const d = new Date(item.created_at);
        const now = new Date();
        const diffDays = Math.floor((now.getTime() - d.getTime()) / (1000 * 3600 * 24));
        if (diffDays === 0) return 'Today';
        if (diffDays === 1) return 'Yesterday';
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      })()
    : 'Recent';

  return {
    id: String(item.id),
    title: item.title || (item.content_type === 'note' ? 'Untitled Note' : item.source_url || 'Untitled Source'),
    content_type: item.content_type,
    source_url: item.source_url,
    file_key: item.file_key,
    summary: item.summary || item.raw_text?.slice(0, 160) || '',
    raw_text: item.raw_text,
    collection: item.collection_name || 'General',
    collection_id: item.collection?.id || item.collection || null,
    tags: item.tags_list || [],
    chunk_count: item.chunk_count || 0,
    date: dateStr,
    status: item.ingestion_status || 'completed',
    error_message: item.error_message,
    metadata: item.metadata,
    meta,
  };
}

function renderStatusBadge(status: string, errorMessage?: string) {
  const normStatus = (status || '').toLowerCase();

  if (normStatus === 'completed' || normStatus === 'ready') {
    return (
      <span
        className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-0.5 rounded-full bg-[#F0F4EE] text-[#3D5236] border border-[#D4DFCE] dark:bg-[#1E261C] dark:text-[#9DAA94] dark:border-[#2C3829] shrink-0 select-none shadow-2xs"
        title="Content fully indexed and ready for grounded search"
      >
        <Check className="h-3 w-3 stroke-[2.2]" />
        <span>Ready</span>
      </span>
    );
  }

  if (normStatus === 'partial') {
    return (
      <span
        className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-0.5 rounded-full bg-[#F7F3EE] text-[#78644A] border border-[#E8DFD3] dark:bg-[#25201B] dark:text-[#CDB59B] dark:border-[#383129] shrink-0 select-none shadow-2xs"
        title={errorMessage || 'Partially indexed (e.g. metadata or partial document)'}
      >
        <AlertCircle className="h-3 w-3 stroke-[2]" />
        <span>Partial</span>
      </span>
    );
  }

  if (normStatus === 'failed') {
    return (
      <span
        className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-0.5 rounded-full bg-[#F9ECEC] text-[#8C3A3A] border border-[#EACDCD] dark:bg-[#2A1D1D] dark:text-[#C58B8B] dark:border-[#422C2C] shrink-0 select-none shadow-2xs"
        title={errorMessage || 'Indexing failed'}
      >
        <AlertCircle className="h-3 w-3 stroke-[2]" />
        <span>Failed</span>
      </span>
    );
  }

  // Active / in-progress states
  const stageLabels: Record<string, string> = {
    pending: 'Pending',
    processing: 'Processing...',
    extracting: 'Extracting...',
    chunking: 'Chunking...',
    embedding: 'Embedding...',
    indexing: 'Indexing...',
  };
  const label = stageLabels[normStatus] || 'Indexing...';

  return (
    <span
      className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-0.5 rounded-full bg-[var(--surface-subtle)] text-[var(--foreground-muted)] border border-[var(--border)] dark:bg-[var(--surface-hover)] dark:text-[var(--foreground-muted)] dark:border-[var(--border)] shrink-0 select-none shadow-2xs"
      title={`Processing in progress (${normStatus})`}
    >
      <Loader2 className="h-3 w-3 animate-spin stroke-[2]" />
      <span>{label}</span>
    </span>
  );
}

export default function LibraryPage() {
  const router = useRouter();
  const [items, setItems] = React.useState<LibraryItem[]>([]);
  const [collections, setCollections] = React.useState<Array<{ id: string; name: string }>>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [searchQuery, setSearchQuery] = React.useState('');
  const [filterType, setFilterType] = React.useState<'All' | 'Document' | 'Link' | 'Note'>('All');
  const [viewMode, setViewMode] = React.useState<'grid' | 'list'>('grid');

  // Modals & Menu
  const [menuOpenId, setMenuOpenId] = React.useState<string | null>(null);
  const [selectedItemId, setSelectedItemId] = React.useState<string | null>(null);
  const [itemDetail, setItemDetail] = React.useState<ItemDetail | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = React.useState(false);
  const [retryingId, setRetryingId] = React.useState<string | null>(null);

  // Edit / Note Editing State inside Detail View
  const [editTitle, setEditTitle] = React.useState('');
  const [editNoteBody, setEditNoteBody] = React.useState('');
  const [editCollectionId, setEditCollectionId] = React.useState('');
  const [isSavingEdit, setIsSavingEdit] = React.useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = React.useState(false);

  // Delete modal
  const [itemToDelete, setItemToDelete] = React.useState<LibraryItem | null>(null);
  const [isDeleting, setIsDeleting] = React.useState(false);
  const [deleteError, setDeleteError] = React.useState<string | null>(null);

  const openQuickAdd = () => {
    window.dispatchEvent(new CustomEvent('mediacompile:open-quick-add'));
  };

  const fetchItems = React.useCallback(async (silent = false) => {
    if (!silent) setIsLoading(true);
    try {
      const [itemsRes, colsRes] = await Promise.all([
        fetch('/api/v1/content/items/?ordering=-created_at', { cache: 'no-store' }),
        fetch('/api/v1/content/collections/', { cache: 'no-store' }),
      ]);

      if (itemsRes.ok) {
        const data = await itemsRes.json();
        const list = Array.isArray(data) ? data : data.results || [];
        setItems(list.map(mapApiItem));
      }

      if (colsRes.ok) {
        const colData = await colsRes.json();
        const colList = Array.isArray(colData) ? colData : colData.results || [];
        setCollections(colList.map((c: any) => ({ id: String(c.id), name: c.name })));
      }
    } catch (err) {
      console.error('Failed to load library items:', err);
    } finally {
      if (!silent) setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  // Check if any items are in active/non-terminal ingestion states
  const hasInProgress = React.useMemo(() => {
    return items.some((item) => {
      const s = (item.status || '').toLowerCase();
      return s && !['completed', 'partial', 'failed'].includes(s);
    });
  }, [items]);

  // Periodic bounded polling for status updates while any item is in-progress
  React.useEffect(() => {
    if (!hasInProgress) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch('/api/v1/content/items/?ordering=-created_at', { cache: 'no-store' });
        if (res.ok) {
          const data = await res.json();
          const list = Array.isArray(data) ? data : data.results || [];
          setItems(list.map(mapApiItem));

          // If the selected item in detail modal is currently in progress, refresh detail
          if (selectedItemId) {
            const currentItem = list.find((i: any) => String(i.id) === String(selectedItemId));
            if (currentItem) {
              const detailRes = await fetch(`/api/v1/content/items/${selectedItemId}/`, { cache: 'no-store' });
              if (detailRes.ok) {
                const detailData = await detailRes.json();
                setItemDetail(detailData);
              }
            }
          }
        }
      } catch (err) {
        console.error('Failed to poll indexing status:', err);
      }
    }, 2500);

    return () => clearInterval(interval);
  }, [hasInProgress, selectedItemId]);

  // Retry handler for failed content items
  const handleRetryItem = async (itemId: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    if (retryingId === itemId) return;
    setRetryingId(itemId);
    try {
      const res = await fetch(`/api/v1/content/items/${itemId}/retry/`, {
        method: 'POST',
      });
      if (res.ok) {
        setItems((prev) =>
          prev.map((i) => (i.id === itemId ? { ...i, status: 'pending', error_message: undefined } : i))
        );
        if (itemDetail && String(itemDetail.id) === String(itemId)) {
          setItemDetail((prev) => (prev ? { ...prev, ingestion_status: 'pending', error_message: '' } : null));
        }
      }
    } catch (err) {
      console.error('Failed to retry item:', err);
    } finally {
      setRetryingId(null);
    }
  };

  // Listen for items added via QuickAddModal
  React.useEffect(() => {
    const handleItemAdded = () => fetchItems(true);
    window.addEventListener('library-item-added', handleItemAdded);
    return () => window.removeEventListener('library-item-added', handleItemAdded);
  }, [fetchItems]);

  // Listen for items deleted across components to update immediately without refresh
  React.useEffect(() => {
    const handleContentDeleted = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.id) {
        setItems((prev) => prev.filter((i) => i.id !== detail.id));
      }
    };

    const handleCollectionCreated = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.id && detail?.name) {
        setCollections((prev) => [...prev, { id: String(detail.id), name: detail.name }]);
      }
    };

    const handleCollectionUpdated = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.id && detail?.name) {
        const updatedId = String(detail.id);
        const newName = detail.name;
        setCollections((prev) =>
          prev.map((c) => (c.id === updatedId ? { ...c, name: newName } : c))
        );
        // Also update any items referencing this collection
        setItems((prev) =>
          prev.map((item) =>
            item.collection_id === updatedId
              ? { ...item, collection: newName }
              : item
          )
        );
      }
    };

    const handleCollectionDeleted = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.id) {
        const deletedId = String(detail.id);
        setCollections((prev) => prev.filter((c) => c.id !== deletedId));
      }
    };

    window.addEventListener('mediacompile:content-deleted', handleContentDeleted);
    window.addEventListener('mediacompile:collection-created', handleCollectionCreated);
    window.addEventListener('mediacompile:collection-updated', handleCollectionUpdated);
    window.addEventListener('mediacompile:collection-deleted', handleCollectionDeleted);

    return () => {
      window.removeEventListener('mediacompile:content-deleted', handleContentDeleted);
      window.removeEventListener('mediacompile:collection-created', handleCollectionCreated);
      window.removeEventListener('mediacompile:collection-updated', handleCollectionUpdated);
      window.removeEventListener('mediacompile:collection-deleted', handleCollectionDeleted);
    };
  }, []);

  // Open full detail modal
  const handleOpenDetail = async (id: string) => {
    setSelectedItemId(id);
    setIsLoadingDetail(true);
    setMenuOpenId(null);
    setHasUnsavedChanges(false);

    try {
      const res = await fetch(`/api/v1/content/items/${id}/`);
      if (res.ok) {
        const data: ItemDetail = await res.json();
        setItemDetail(data);
        setEditTitle(data.title || '');
        setEditNoteBody(data.raw_text || '');
        setEditCollectionId(data.collection ? String(data.collection.id) : '');
      }
    } catch {
      // ignore
    } finally {
      setIsLoadingDetail(false);
    }
  };

  // Save changes from Detail View
  const handleSaveDetailChanges = async () => {
    if (!itemDetail) return;
    setIsSavingEdit(true);

    try {
      const payload: Record<string, any> = {
        title: editTitle.trim(),
        collection: editCollectionId || null,
      };

      if (itemDetail.content_type === 'note') {
        payload.raw_text = editNoteBody;
      }

      const res = await fetch(`/api/v1/content/items/${itemDetail.id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const updated = await res.json();
        setHasUnsavedChanges(false);
        setItemDetail((prev) => (prev ? { ...prev, ...updated } : null));
        setItems((prev) =>
          prev.map((i) => (i.id === itemDetail.id ? mapApiItem({ ...i, ...updated }) : i))
        );
      }
    } catch (err) {
      console.error('Failed to update content item:', err);
    } finally {
      setIsSavingEdit(false);
    }
  };

  // Delete item with immediate UI update without refresh
  const handleConfirmDelete = async () => {
    if (!itemToDelete || isDeleting) return;
    setIsDeleting(true);
    setDeleteError(null);

    const deletedId = itemToDelete.id;
    try {
      const res = await fetch(`/api/v1/content/items/${deletedId}/`, {
        method: 'DELETE',
      });

      if (res.ok) {
        // 1. Immediately remove from current state
        setItems((prev) => prev.filter((i) => i.id !== deletedId));
        if (selectedItemId === deletedId) {
          setSelectedItemId(null);
          setItemDetail(null);
          if (typeof window !== 'undefined' && window.location.search) {
            window.history.replaceState({}, '', '/library');
          }
        }
        // 2. Broadcast to other components (dashboard, collections, sidebar)
        window.dispatchEvent(
          new CustomEvent('mediacompile:content-deleted', {
            detail: { id: deletedId },
          })
        );
        setItemToDelete(null);
      } else {
        const errorData = await res.json().catch(() => ({}));
        setDeleteError(errorData.detail || errorData.error || 'Failed to delete item from server.');
      }
    } catch (err: any) {
      setDeleteError(err.message || 'Network error while attempting deletion.');
    } finally {
      setIsDeleting(false);
    }
  };

  // Filter items strictly by canonical type
  const filteredItems = items.filter((item) => {
    if (filterType !== 'All' && item.meta.primaryType !== filterType) {
      return false;
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        item.title.toLowerCase().includes(q) ||
        item.collection.toLowerCase().includes(q) ||
        item.summary.toLowerCase().includes(q) ||
        item.meta.secondaryLabel.toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <ShellLayout>
      <div className="space-y-6 animate-in fade-in duration-200" onClick={() => setMenuOpenId(null)}>
        {/* Header Row: Unified Add Content Button */}
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div>
            <span className="text-xs font-semibold tracking-wider text-[var(--foreground-muted)] uppercase">
              WORKSPACE
            </span>
            <h1 className="text-2xl sm:text-3xl font-medium tracking-tight text-[var(--foreground)] mt-1">
              Content library
            </h1>
            <p className="text-xs sm:text-sm text-[var(--foreground-muted)] mt-1">
              Every document, link, and note ready to search, organize, and discuss.
            </p>
          </div>

          <button
            onClick={openQuickAdd}
            className="px-4 py-2.5 rounded-xl bg-[var(--surface-elevated)] hover:bg-[var(--surface-hover)] border border-[var(--border)] text-xs font-semibold text-[var(--foreground)] flex items-center gap-2 transition-all cursor-pointer shadow-xs self-start sm:self-auto"
          >
            <Plus className="h-4 w-4 text-[var(--accent-sand)]" />
            <span>Add Content</span>
          </button>
        </div>

        {/* Controls Bar: Search, Canonical Type Filters, View Mode */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pt-2">
          <div className="flex flex-wrap items-center gap-3">
            {/* Search Input */}
            <div className="relative w-full sm:w-72">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--foreground-muted)]" />
              <input
                type="text"
                placeholder="Search your library..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-xs text-[var(--foreground)] placeholder-[var(--foreground-muted)] focus:outline-hidden focus:border-[var(--border-hover)] transition-colors"
              />
            </div>

            {/* Canonical Content Type Filter Pills */}
            <div className="flex items-center gap-1 bg-[var(--surface)] p-1 rounded-lg border border-[var(--border)]">
              {(['All', 'Document', 'Link', 'Note'] as const).map((type) => (
                <button
                  key={type}
                  onClick={() => setFilterType(type)}
                  className={`px-3 py-1 rounded-md text-xs font-normal transition-colors cursor-pointer ${
                    filterType === type
                      ? 'bg-[var(--surface-elevated)] text-[var(--foreground)] font-semibold border border-[var(--border)] shadow-2xs'
                      : 'text-[var(--foreground-muted)] hover:text-[var(--foreground)]'
                  }`}
                >
                  {type}
                </button>
              ))}
            </div>
          </div>

          {/* Right: Counter and View Mode Toggle */}
          <div className="flex items-center gap-4 text-xs text-[var(--foreground-muted)] self-end md:self-auto">
            <span className="font-mono text-[11px]">{filteredItems.length} items</span>
            <span className="text-[var(--border)]">|</span>

            {/* View Mode icons */}
            <div className="flex items-center gap-1">
              <button
                onClick={() => setViewMode('grid')}
                className={`p-1.5 rounded-md ${
                  viewMode === 'grid' ? 'text-[var(--foreground)] bg-[var(--surface-elevated)] border border-[var(--border)]' : 'text-[var(--foreground-muted)] hover:text-[var(--foreground)]'
                }`}
                title="Grid view"
              >
                <LayoutGrid className="h-4 w-4" />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`p-1.5 rounded-md ${
                  viewMode === 'list' ? 'text-[var(--foreground)] bg-[var(--surface-elevated)] border border-[var(--border)]' : 'text-[var(--foreground-muted)] hover:text-[var(--foreground)]'
                }`}
                title="List view"
              >
                <ListIcon className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Content Items: Grid or List */}
        {isLoading ? (
          <div className="py-20 text-center text-xs text-[var(--foreground-muted)] flex items-center justify-center gap-2">
            <Loader2 className="h-5 w-5 animate-spin" />
            Loading knowledge library...
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="py-16 text-center text-xs text-[var(--foreground-muted)] rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface)] p-8 space-y-3">
            <FileText className="mx-auto h-8 w-8 text-[var(--foreground-muted)] opacity-60" />
            <p className="text-sm font-medium text-[var(--foreground)]">No content found</p>
            <p className="text-[var(--foreground-muted)] max-w-sm mx-auto">
              {searchQuery
                ? `No items match "${searchQuery}". Clear your search or filter.`
                : 'Use "+ Add Content" to add your first document, link, or note.'}
            </p>
          </div>
        ) : viewMode === 'grid' ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {filteredItems.map((item, index) => {
              const bgPastel = pastelPalette[index % pastelPalette.length];
              const isDoc = item.meta.primaryType === 'Document';
              const isLink = item.meta.primaryType === 'Link';

              return (
                <div
                  key={item.id}
                  className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] overflow-hidden group hover:border-[var(--border-hover)] transition-all flex flex-col justify-between shadow-2xs"
                >
                  {/* Upper Pastel Preview */}
                  <div
                    onClick={() => handleOpenDetail(item.id)}
                    className={`h-36 ${bgPastel} p-4 relative flex flex-col justify-between select-none cursor-pointer`}
                  >
                    <div className="flex justify-between items-start">
                      <div className="w-2/3 space-y-2 pt-1 opacity-70">
                        <div className="h-1.5 bg-black/20 rounded-full w-full" />
                        <div className="h-1.5 bg-black/20 rounded-full w-4/5" />
                        <div className="h-1.5 bg-black/20 rounded-full w-3/5" />
                      </div>

                      {/* Dropdown menu trigger */}
                      <div className="relative" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => setMenuOpenId(menuOpenId === item.id ? null : item.id)}
                          className="h-6 w-6 rounded-md bg-black/20 hover:bg-black/30 flex items-center justify-center text-black/80 transition-colors cursor-pointer"
                        >
                          <MoreHorizontal className="h-4 w-4" />
                        </button>

                        {menuOpenId === item.id && (
                          <div className="absolute right-0 top-7 w-36 rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-1.5 shadow-2xl z-20 space-y-0.5 text-xs">
                            <button
                              onClick={() => handleOpenDetail(item.id)}
                              className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-[var(--foreground)] hover:bg-[var(--surface-hover)] text-left cursor-pointer"
                            >
                              <Eye className="h-3.5 w-3.5" />
                              View detail
                            </button>
                            {item.status === 'failed' && (
                              <button
                                onClick={(e) => handleRetryItem(item.id, e)}
                                disabled={retryingId === item.id}
                                className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-amber-600 dark:text-amber-400 hover:bg-amber-500/10 text-left cursor-pointer"
                              >
                                <RotateCcw className={`h-3.5 w-3.5 ${retryingId === item.id ? 'animate-spin' : ''}`} />
                                Retry indexing
                              </button>
                            )}
                            <button
                              onClick={() => {
                                setItemToDelete(item);
                                setMenuOpenId(null);
                              }}
                              className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-rose-500 hover:bg-rose-500/10 text-left cursor-pointer"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                              Delete
                            </button>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Bottom Left Pill Icon */}
                    <div className="h-7 w-7 rounded-lg bg-white/90 shadow-2xs flex items-center justify-center text-stone-800">
                      {isDoc ? (
                        <UploadCloud className="h-3.5 w-3.5" />
                      ) : isLink ? (
                        <LinkIcon className="h-3.5 w-3.5" />
                      ) : (
                        <FileText className="h-3.5 w-3.5" />
                      )}
                    </div>
                  </div>

                  {/* Lower Content Box */}
                  <div className="p-4 bg-[var(--surface)] space-y-3 flex-1 flex flex-col justify-between">
                    <div>
                      {/* Canonical Type & Genuine Stats & Readiness Badge */}
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-mono tracking-wider text-[var(--foreground-muted)] uppercase truncate">
                          {item.meta.primaryType} · {item.meta.statsLabel}
                        </span>
                        {renderStatusBadge(item.status, item.error_message)}
                      </div>

                      {/* Title */}
                      <h3
                        onClick={() => handleOpenDetail(item.id)}
                        className="text-sm font-semibold text-[var(--foreground)] group-hover:text-[var(--accent-sand)] transition-colors mt-1.5 line-clamp-1 cursor-pointer"
                      >
                        {item.title}
                      </h3>

                      {/* Collection */}
                      <div className="flex items-center gap-1.5 text-xs text-[var(--foreground-muted)] mt-2">
                        <Folder className="h-3.5 w-3.5 text-[var(--foreground-muted)]" />
                        <span>{item.collection}</span>
                      </div>
                    </div>

                    {/* Bottom row: date and Details link */}
                    <div className="flex items-center justify-between pt-2 border-t border-[var(--border)] text-xs">
                      <span className="text-[var(--foreground-muted)] font-mono text-[11px]">{item.date}</span>

                      <button
                        onClick={() => handleOpenDetail(item.id)}
                        className="text-[var(--foreground-muted)] hover:text-[var(--foreground)] flex items-center gap-1 font-medium transition-colors cursor-pointer"
                      >
                        Details <ArrowRight className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          /* List View */
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] divide-y divide-[var(--border)]">
            {filteredItems.map((item, index) => {
              const bgPastel = pastelPalette[index % pastelPalette.length];
              const isDoc = item.meta.primaryType === 'Document';
              const isLink = item.meta.primaryType === 'Link';

              return (
                <div
                  key={item.id}
                  className="p-3.5 flex items-center justify-between gap-4 hover:bg-[var(--surface-hover)] transition-colors group"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={`h-8 w-8 rounded-lg ${bgPastel} flex items-center justify-center shrink-0`}>
                      {isDoc ? (
                        <UploadCloud className="h-3.5 w-3.5" />
                      ) : isLink ? (
                        <LinkIcon className="h-3.5 w-3.5" />
                      ) : (
                        <FileText className="h-3.5 w-3.5" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <p
                        onClick={() => handleOpenDetail(item.id)}
                        className="text-xs font-medium text-[var(--foreground)] group-hover:text-[var(--accent-sand)] truncate cursor-pointer"
                      >
                        {item.title}
                      </p>
                      <div className="flex items-center gap-2 text-xs text-[var(--foreground-muted)] mt-0.5 flex-wrap">
                        <span className="font-semibold text-[var(--foreground)]">{item.meta.primaryType}</span>
                        <span>•</span>
                        <span>{item.meta.statsLabel}</span>
                        <span>•</span>
                        <span>{item.collection}</span>
                        <span>•</span>
                        {renderStatusBadge(item.status, item.error_message)}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2.5 shrink-0 text-xs">
                    <span className="text-[var(--foreground-muted)] font-mono hidden md:inline">{item.date}</span>
                    {item.status === 'failed' && (
                      <button
                        onClick={(e) => handleRetryItem(item.id, e)}
                        disabled={retryingId === item.id}
                        className="px-2.5 py-1 rounded-lg bg-[var(--surface-elevated)] hover:bg-[var(--surface-hover)] border border-[var(--border)] text-amber-600 dark:text-amber-400 font-medium text-xs flex items-center gap-1.5 cursor-pointer shadow-2xs"
                        title="Retry indexing"
                      >
                        <RotateCcw className={`h-3 w-3 ${retryingId === item.id ? 'animate-spin' : ''}`} />
                        <span>Retry</span>
                      </button>
                    )}
                    <button
                      onClick={() => handleOpenDetail(item.id)}
                      className="px-2.5 py-1 rounded bg-[var(--surface-elevated)] hover:bg-[var(--surface-hover)] border border-[var(--border)] text-[var(--foreground)] font-medium text-xs cursor-pointer"
                    >
                      View
                    </button>
                    <button
                      onClick={() => setItemToDelete(item)}
                      className="p-1 rounded text-[var(--foreground-muted)] hover:text-rose-500 transition-colors cursor-pointer"
                      title="Delete source"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* DEDICATED DETAIL & EDIT MODAL (Requirement 11) */}
        {selectedItemId && (
          <Modal
            isOpen={true}
            onClose={() => {
              setSelectedItemId(null);
              setItemDetail(null);
              setHasUnsavedChanges(false);
            }}
            title={itemDetail ? `${itemDetail.title || 'Content Details'}` : 'Loading...'}
            description={
              itemDetail
                ? `${getCanonicalContentMeta(itemDetail).primaryType} · ${getCanonicalContentMeta(itemDetail).statsLabel}`
                : undefined
            }
          >
            {isLoadingDetail ? (
              <div className="py-12 text-center text-xs text-[var(--foreground-muted)] flex items-center justify-center gap-2">
                <Loader2 className="h-5 w-5 animate-spin" />
                Loading details...
              </div>
            ) : itemDetail ? (
              <div className="space-y-4 text-xs">
                {/* Meta Overview Box */}
                <div className="p-3.5 rounded-xl bg-[var(--surface)] border border-[var(--border)] space-y-2">
                  <div className="grid grid-cols-2 gap-2 text-[11px] items-center">
                    <div>
                      <span className="text-[var(--foreground-muted)]">Type: </span>
                      <strong className="text-[var(--foreground)] font-semibold">
                        {getCanonicalContentMeta(itemDetail).primaryType}
                      </strong>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[var(--foreground-muted)]">Status: </span>
                      {renderStatusBadge(itemDetail.ingestion_status, itemDetail.error_message)}
                      {itemDetail.ingestion_status === 'failed' && (
                        <button
                          onClick={(e) => handleRetryItem(itemDetail.id, e)}
                          disabled={retryingId === itemDetail.id}
                          className="px-2 py-0.5 rounded text-[11px] font-medium bg-[var(--surface-hover)] hover:bg-[var(--surface-elevated)] border border-[var(--border)] text-amber-600 dark:text-amber-400 flex items-center gap-1 cursor-pointer"
                        >
                          <RotateCcw className={`h-2.5 w-2.5 ${retryingId === itemDetail.id ? 'animate-spin' : ''}`} />
                          <span>Retry</span>
                        </button>
                      )}
                    </div>
                    <div>
                      <span className="text-[var(--foreground-muted)]">Indexed Chunks: </span>
                      <span className="text-[var(--foreground)] font-mono font-semibold">{itemDetail.chunk_count}</span>
                    </div>
                    <div>
                      <span className="text-[var(--foreground-muted)]">Collection: </span>
                      <span className="text-[var(--foreground)] font-medium">{itemDetail.collection?.name || 'General'}</span>
                    </div>
                  </div>

                  {/* Clickable Original Link for Link types */}
                  {itemDetail.source_url && (
                    <div className="pt-2 border-t border-[var(--border)] flex items-center justify-between text-[11px]">
                      <span className="text-[var(--foreground-muted)]">Original Link:</span>
                      <a
                        href={itemDetail.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[var(--accent-sand)] hover:underline flex items-center gap-1 max-w-[260px] truncate"
                      >
                        <span className="truncate">{itemDetail.source_url}</span>
                        <ExternalLink className="h-3 w-3 shrink-0" />
                      </a>
                    </div>
                  )}

                  {/* Document Download Link */}
                  {itemDetail.file_key && (
                    <div className="pt-2 border-t border-[var(--border)] flex items-center justify-between text-[11px]">
                      <span className="text-[var(--foreground-muted)]">Stored Document:</span>
                      <a
                        href={`/api/v1/content/items/${itemDetail.id}/download/`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[var(--accent-sand)] hover:underline flex items-center gap-1"
                      >
                        <Download className="h-3 w-3" />
                        <span>Download Original File</span>
                      </a>
                    </div>
                  )}
                </div>

                {/* Edit Form */}
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium text-[var(--foreground)] mb-1">
                      Title
                    </label>
                    <Input
                      value={editTitle}
                      onChange={(e) => {
                        setEditTitle(e.target.value);
                        setHasUnsavedChanges(true);
                      }}
                      placeholder="Title"
                    />
                  </div>

                  {/* Note Body Editing */}
                  {itemDetail.content_type === 'note' && (
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <label className="text-xs font-medium text-[var(--foreground)]">
                          Note Content
                        </label>
                        {hasUnsavedChanges && (
                          <span className="text-xs text-amber-500 font-medium">Unsaved changes</span>
                        )}
                      </div>
                      <textarea
                        rows={7}
                        value={editNoteBody}
                        onChange={(e) => {
                          setEditNoteBody(e.target.value);
                          setHasUnsavedChanges(true);
                        }}
                        className="w-full px-3 py-2 rounded-xl bg-[var(--surface)] border border-[var(--border)] text-xs text-[var(--foreground)] focus:outline-hidden focus:border-[var(--border-hover)] resize-none font-mono leading-relaxed"
                        placeholder="Note body..."
                      />
                    </div>
                  )}

                  {/* Extracted Text Preview for Documents & Links */}
                  {itemDetail.content_type !== 'note' && (
                    <div>
                      <label className="block text-xs font-medium text-[var(--foreground)] mb-1">
                        Extracted Content Preview
                      </label>
                      <div className="p-3 rounded-xl bg-[var(--surface)] border border-[var(--border)] max-h-40 overflow-y-auto text-[11px] text-[var(--foreground-muted)] leading-relaxed font-mono">
                        {itemDetail.summary || itemDetail.raw_text?.slice(0, 800) || 'No extracted text available.'}
                      </div>
                    </div>
                  )}

                  {/* Collection Assignment */}
                  <div>
                    <label className="block text-xs font-medium text-[var(--foreground)] mb-1">
                      Collection
                    </label>
                    <select
                      value={editCollectionId}
                      onChange={(e) => {
                        setEditCollectionId(e.target.value);
                        setHasUnsavedChanges(true);
                      }}
                      className="w-full px-3 py-2 rounded-xl bg-[var(--surface)] border border-[var(--border)] text-xs text-[var(--foreground)] focus:outline-hidden focus:border-[var(--border-hover)]"
                    >
                      <option value="">No Collection (General Library)</option>
                      {collections.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Modal Footer Actions */}
                <div className="flex items-center justify-between pt-3 border-t border-[var(--border)]">
                  <button
                    onClick={() => {
                      setItemToDelete(mapApiItem(itemDetail));
                    }}
                    className="text-xs text-rose-500 hover:text-rose-600 flex items-center gap-1 cursor-pointer"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    <span>Delete item</span>
                  </button>

                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setSelectedItemId(null);
                        setItemDetail(null);
                        setHasUnsavedChanges(false);
                      }}
                    >
                      Close
                    </Button>

                    <Button
                      variant="primary"
                      size="sm"
                      onClick={handleSaveDetailChanges}
                      disabled={isSavingEdit || !hasUnsavedChanges}
                    >
                      {isSavingEdit ? (
                        <span className="flex items-center gap-1">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          Saving...
                        </span>
                      ) : (
                        'Save Changes'
                      )}
                    </Button>
                  </div>
                </div>
              </div>
            ) : null}
          </Modal>
        )}

        {/* Standardized Delete Confirmation Modal */}
        <DeleteConfirmationModal
          isOpen={!!itemToDelete}
          onClose={() => {
            if (!isDeleting) {
              setItemToDelete(null);
              setDeleteError(null);
            }
          }}
          onConfirm={handleConfirmDelete}
          title={`Delete this ${itemToDelete?.meta?.primaryType?.toLowerCase() || 'content'}?`}
          itemName={itemToDelete?.title}
          itemType="content"
          itemMeta={`${itemToDelete?.meta?.secondaryLabel || itemToDelete?.content_type?.toUpperCase() || 'Source'} · ${itemToDelete?.chunk_count || 0} chunks · ${itemToDelete?.date || 'Recent'}`}
          isDeleting={isDeleting}
          errorMessage={deleteError}
        />
      </div>
    </ShellLayout>
  );
}
