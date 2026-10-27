'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import {
  Folder,
  Plus,
  Trash2,
  Edit2,
  FileText,
  Link as LinkIcon,
  StickyNote,
  Loader2,
  X,
  ExternalLink,
  MinusCircle
} from 'lucide-react';
import { ShellLayout } from '@/components/shell/shell-layout';
import { Modal } from '@/components/ui/modal';
import { DeleteConfirmationModal } from '@/components/ui/delete-confirmation-modal';
import { CollectionAddModal } from '@/components/collections/collection-add-modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { getCanonicalContentMeta, type CanonicalContentMeta } from '@/lib/content-utils';

interface Collection {
  id: string;
  name: string;
  description: string;
  item_count?: number;
}

const folderBgPalette = [
  'bg-[#CDB59B] text-[#1e1a16]', // tan
  'bg-[#9DAA94] text-[#161a15]', // sage
  'bg-[#8F969E] text-[#16181b]', // slate
  'bg-[#B98A77] text-[#221612]', // terracotta
  'bg-[#C7BA99] text-[#1c1a14]', // khaki
];

export default function CollectionsPage() {
  const router = useRouter();
  const [collections, setCollections] = React.useState<Collection[]>([]);
  const [selectedColId, setSelectedColId] = React.useState<string | null>(null);
  const [allSources, setAllSources] = React.useState<any[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);

  // New Collection Modal State
  const [isCreateOpen, setIsCreateOpen] = React.useState(false);
  const [newName, setNewName] = React.useState('');
  const [newDesc, setNewDesc] = React.useState('');
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);

  // Rename Collection Modal State
  const [isRenameOpen, setIsRenameOpen] = React.useState(false);
  const [renameName, setRenameName] = React.useState('');
  const [renameDesc, setRenameDesc] = React.useState('');
  const [isRenaming, setIsRenaming] = React.useState(false);
  const [renameError, setRenameError] = React.useState<string | null>(null);

  // Add Source Modal State
  const [isAddSourceOpen, setIsAddSourceOpen] = React.useState(false);
  const [assigningSourceId, setAssigningSourceId] = React.useState<string | null>(null);

  // Delete Collection Modal State
  const [colToDelete, setColToDelete] = React.useState<Collection | null>(null);
  const [isDeleting, setIsDeleting] = React.useState(false);
  const [deleteError, setDeleteError] = React.useState<string | null>(null);

  // Remove Item from Collection State
  const [removingItemId, setRemovingItemId] = React.useState<string | null>(null);

  const loadData = React.useCallback(async () => {
    setIsLoading(true);
    try {
      const [colRes, itemsRes] = await Promise.all([
        fetch('/api/v1/content/collections/', { cache: 'no-store' }),
        fetch('/api/v1/content/items/?ordering=-created_at', { cache: 'no-store' }),
      ]);

      let cols: Collection[] = [];
      if (colRes.ok) {
        const data = await colRes.json();
        cols = Array.isArray(data) ? data : data.results || [];
        setCollections(cols);
        if (cols.length > 0 && !selectedColId) {
          setSelectedColId(String(cols[0].id));
        }
      }

      if (itemsRes.ok) {
        const itemData = await itemsRes.json();
        const list = Array.isArray(itemData) ? itemData : itemData.results || [];
        setAllSources(list);
      }
    } catch (err) {
      console.error('Failed to load collections:', err);
    } finally {
      setIsLoading(false);
    }
  }, [selectedColId]);

  React.useEffect(() => {
    loadData();
  }, [loadData]);

  // Listen for items deleted elsewhere to immediately remove from view and update counts
  React.useEffect(() => {
    const handleContentDeleted = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.id) {
        setAllSources((prev) => prev.filter((s) => s.id !== detail.id));
        // Decrement item count in collections
        setCollections((prev) =>
          prev.map((c) => ({
            ...c,
            item_count: Math.max(0, (c.item_count || 1) - 1),
          }))
        );
      }
    };
    window.addEventListener('mediacompile:content-deleted', handleContentDeleted);
    return () => window.removeEventListener('mediacompile:content-deleted', handleContentDeleted);
  }, []);

  const selectedCol =
    collections.find((c) => String(c.id) === selectedColId) ||
    collections[0] || {
      id: 'default',
      name: 'General',
      description: 'Default collection',
      item_count: 0,
    };

  // Filter sources belonging to selected collection
  const activeSources = React.useMemo(() => {
    return allSources.filter(
      (s) =>
        String(s.collection) === String(selectedCol.id) ||
        String(s.collection_id) === String(selectedCol.id) ||
        (s.collection_name && s.collection_name === selectedCol.name)
    );
  }, [allSources, selectedCol]);

  // Handle Collection Creation
  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newName.trim();
    if (!trimmed || isSubmitting) return;

    setIsSubmitting(true);
    setCreateError(null);
    try {
      const res = await fetch('/api/v1/content/collections/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: trimmed,
          description: newDesc.trim(),
        }),
      });

      if (res.ok) {
        const created = await res.json();
        setCollections((prev) => [created, ...prev]);
        setSelectedColId(String(created.id));
        setNewName('');
        setNewDesc('');
        setIsCreateOpen(false);
        // Broadcast collection creation across the app
        window.dispatchEvent(
          new CustomEvent('mediacompile:collection-created', { detail: created })
        );
      } else {
        const errData = await res.json().catch(() => ({}));
        const rawMsg =
          errData.error?.details?.name?.[0] ||
          errData.error?.details?.non_field_errors?.[0] ||
          errData.error?.message ||
          errData.name?.[0] ||
          errData.non_field_errors?.[0] ||
          errData.detail ||
          'Failed to create collection';
        const cleanMsg =
          typeof rawMsg === 'string'
            ? rawMsg.replace(/^non_field_errors:\s*/i, '')
            : 'Failed to create collection';
        setCreateError(cleanMsg);
      }
    } catch (err: any) {
      setCreateError(err.message || 'Network error');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Open Rename Dialog
  const openRenameModal = () => {
    if (!selectedCol || selectedCol.id === 'default') return;
    setRenameName(selectedCol.name);
    setRenameDesc(selectedCol.description || '');
    setRenameError(null);
    setIsRenameOpen(true);
  };

  // Handle Collection Rename
  const handleRename = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = renameName.trim();
    if (!trimmed || isRenaming) return;

    if (selectedCol.id === 'default') {
      setRenameError('Cannot rename default collection. Please create a new collection.');
      return;
    }

    setIsRenaming(true);
    setRenameError(null);
    try {
      const res = await fetch(`/api/v1/content/collections/${selectedCol.id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: trimmed,
          description: renameDesc.trim(),
        }),
      });

      if (res.ok) {
        const updated = await res.json();
        const oldName = selectedCol.name;

        // 1. Update collection in local state preserving all metadata
        setCollections((prev) =>
          prev.map((c) => (c.id === updated.id ? { ...c, ...updated } : c))
        );

        // 2. Update in-memory allSources so filtering remains intact
        setAllSources((prev) =>
          prev.map((s) => {
            if (
              String(s.collection) === String(updated.id) ||
              String(s.collection_id) === String(updated.id) ||
              s.collection_name === oldName
            ) {
              return {
                ...s,
                collection: updated.id,
                collection_id: updated.id,
                collection_name: updated.name,
              };
            }
            return s;
          })
        );

        // 3. Broadcast collection update to other views (library, dashboard, sidebar)
        window.dispatchEvent(
          new CustomEvent('mediacompile:collection-updated', { detail: updated })
        );

        setIsRenameOpen(false);
      } else {
        const errData = await res.json().catch(() => ({}));
        const rawMsg =
          errData.error?.details?.name?.[0] ||
          errData.error?.details?.non_field_errors?.[0] ||
          errData.error?.message ||
          errData.name?.[0] ||
          errData.non_field_errors?.[0] ||
          errData.detail ||
          'Failed to rename collection';
        const cleanMsg =
          typeof rawMsg === 'string'
            ? rawMsg.replace(/^non_field_errors:\s*/i, '')
            : 'Failed to rename collection';
        setRenameError(cleanMsg);
      }
    } catch (err: any) {
      setRenameError(err.message || 'Network error');
    } finally {
      setIsRenaming(false);
    }
  };

  // Handle Collection Deletion with immediate UI update without refresh
  const handleDeleteCollection = async () => {
    if (!colToDelete || isDeleting) return;
    setIsDeleting(true);
    setDeleteError(null);

    const deletedColId = colToDelete.id;
    try {
      const res = await fetch(`/api/v1/content/collections/${deletedColId}/`, {
        method: 'DELETE',
      });
      if (res.ok) {
        const remaining = collections.filter((c) => c.id !== deletedColId);
        setCollections(remaining);
        if (selectedColId === deletedColId) {
          setSelectedColId(remaining.length > 0 ? String(remaining[0].id) : null);
        }
        // Broadcast collection deletion across the app
        window.dispatchEvent(
          new CustomEvent('mediacompile:collection-deleted', {
            detail: { id: deletedColId },
          })
        );
        setColToDelete(null);
      } else {
        const errData = await res.json().catch(() => ({}));
        setDeleteError(errData.detail || errData.error || 'Failed to delete collection from server.');
      }
    } catch (err: any) {
      setDeleteError(err.message || 'Network error while attempting to delete collection.');
    } finally {
      setIsDeleting(false);
    }
  };

  // Handle Assign Source to Selected Collection
  const handleAssignSource = async (sourceId: string) => {
    if (!selectedColId) return;
    setAssigningSourceId(sourceId);
    try {
      const res = await fetch(`/api/v1/content/collections/${selectedColId}/add-item/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_id: sourceId, content_id: sourceId }),
      });
      if (res.ok) {
        // Update local state immediately
        setAllSources((prev) =>
          prev.map((item) =>
            String(item.id) === sourceId
              ? {
                  ...item,
                  collection: selectedColId,
                  collection_id: selectedColId,
                  collection_name: selectedCol.name,
                }
              : item
          )
        );
        setCollections((prev) =>
          prev.map((c) =>
            String(c.id) === String(selectedColId)
              ? { ...c, item_count: (c.item_count || 0) + 1 }
              : c
          )
        );
        await loadData();
      }
    } catch (err) {
      console.error('Failed to assign source:', err);
    } finally {
      setAssigningSourceId(null);
    }
  };

  // Handle Remove Source from Collection (Preserves underlying item!)
  const handleRemoveSource = async (sourceId: string) => {
    if (!selectedColId) return;
    setRemovingItemId(sourceId);
    try {
      const res = await fetch(`/api/v1/content/collections/${selectedColId}/remove-item/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_id: sourceId, content_id: sourceId }),
      });
      if (res.ok) {
        // Update local state smoothly
        setAllSources((prev) =>
          prev.map((item) =>
            String(item.id) === sourceId
              ? { ...item, collection: null, collection_id: null, collection_name: null }
              : item
          )
        );
        // Decrement collection item_count
        setCollections((prev) =>
          prev.map((c) =>
            String(c.id) === String(selectedColId)
              ? { ...c, item_count: Math.max(0, (c.item_count || 1) - 1) }
              : c
          )
        );
      }
    } catch (err) {
      console.error('Failed to remove source from collection:', err);
    } finally {
      setRemovingItemId(null);
    }
  };

  const handleOpenUnifiedAdd = () => {
    window.dispatchEvent(
      new CustomEvent('mediacompile:open-quick-add', {
        detail: { defaultCollectionId: String(selectedCol.id) },
      })
    );
  };

  return (
    <ShellLayout>
      <div className="space-y-8 animate-in fade-in duration-200">
        {/* Header Row */}
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div>
            <span className="text-xs font-semibold tracking-wider text-[var(--muted-foreground)] uppercase">
              COLLECTIONS
            </span>
            <h1 className="text-2xl sm:text-3xl font-medium tracking-tight text-[var(--foreground)] mt-1">
              Organize ideas by context
            </h1>
            <p className="text-xs sm:text-sm text-[var(--muted-foreground)] mt-1">
              Group related documents, links, and notes together into organized workspaces.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsCreateOpen(true)}
              className="px-4 py-2 rounded-lg bg-[var(--primary)] hover:opacity-90 text-[var(--primary-foreground)] text-xs font-medium flex items-center gap-2 transition-colors cursor-pointer shadow-xs self-start sm:self-auto"
            >
              <Plus className="h-3.5 w-3.5 stroke-[2.2]" />
              <span>New collection</span>
            </button>
          </div>
        </div>

        {/* Two-Column Workspace Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Panel: Your collections list (4 cols) */}
          <div className="lg:col-span-4 rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-medium text-sm text-[var(--foreground)]">Your collections</h2>
              <span className="text-xs font-mono text-[var(--muted-foreground)]">{collections.length}</span>
            </div>

            {isLoading ? (
              <div className="py-12 text-center text-xs text-[var(--muted-foreground)] flex items-center justify-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading collections...
              </div>
            ) : collections.length === 0 ? (
              <div className="py-8 text-center text-xs text-[var(--muted-foreground)]">
                No collections yet. Create your first one below.
              </div>
            ) : (
              <div className="space-y-2">
                {collections.map((col, idx) => {
                  const isSelected = String(col.id) === String(selectedCol.id);
                  const bgIcon = folderBgPalette[idx % folderBgPalette.length];
                  const itemCount = allSources.filter(
                    (s) =>
                      String(s.collection) === String(col.id) ||
                      String(s.collection_id) === String(col.id) ||
                      (s.collection_name && s.collection_name === col.name)
                  ).length;

                  return (
                    <div
                      key={col.id}
                      onClick={() => setSelectedColId(String(col.id))}
                      className={`p-3.5 rounded-xl border transition-all cursor-pointer flex items-center justify-between gap-3 ${
                        isSelected
                          ? 'bg-[var(--surface-subtle)] border-[var(--foreground)]/30 shadow-xs'
                          : 'bg-[var(--surface-base)] hover:bg-[var(--surface-subtle)] border-[var(--border)] text-[var(--muted-foreground)]'
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className={`h-8 w-8 rounded-lg ${bgIcon} flex items-center justify-center shrink-0`}>
                          <Folder className="h-4 w-4" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-[var(--foreground)] truncate">{col.name}</p>
                          <p className="text-xs text-[var(--muted-foreground)] mt-0.5">{itemCount} items</p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Bottom New Collection Button */}
            <button
              onClick={() => setIsCreateOpen(true)}
              className="w-full py-2.5 rounded-xl border border-[var(--border)] hover:bg-[var(--surface-subtle)] text-xs text-[var(--foreground)] font-medium flex items-center justify-center gap-2 transition-colors cursor-pointer"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>New collection</span>
            </button>
          </div>

          {/* Right Panel: Selected Collection Detail & Sources (8 cols) */}
          <div className="lg:col-span-8 space-y-5">
            {/* Top Detail Card */}
            <div className="rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-5">
              <div className="flex items-start gap-4 min-w-0">
                <div className="h-12 w-12 rounded-xl bg-[#CDB59B] text-[#1e1a16] flex items-center justify-center shrink-0 shadow-xs">
                  <Folder className="h-6 w-6 stroke-[1.75]" />
                </div>
                <div className="min-w-0">
                  <span className="text-xs font-semibold tracking-wider text-[var(--muted-foreground)] uppercase">
                    COLLECTION
                  </span>
                  <h2 className="text-xl font-semibold text-[var(--foreground)] mt-0.5 truncate">
                    {selectedCol.name}
                  </h2>
                  <p className="text-xs text-[var(--muted-foreground)] mt-1 leading-relaxed max-w-lg">
                    {selectedCol.description || 'Collection items and organized context.'}
                  </p>
                </div>
              </div>

              {/* Action buttons (Rename & Delete) - only available for real user collections */}
              {collections.length > 0 && selectedCol.id !== 'default' && (
                <div className="flex items-center gap-2 self-start sm:self-auto shrink-0">
                  <button
                    onClick={openRenameModal}
                    className="px-3 py-2 rounded-lg bg-[var(--surface-subtle)] hover:bg-[var(--border)] border border-[var(--border)] text-xs font-medium text-[var(--foreground)] flex items-center gap-1.5 transition-colors cursor-pointer"
                    title="Rename collection"
                  >
                    <Edit2 className="h-3.5 w-3.5" />
                    <span>Rename</span>
                  </button>

                  <button
                    onClick={() => setColToDelete(selectedCol)}
                    className="p-2 rounded-lg text-[var(--muted-foreground)] hover:text-rose-500 hover:bg-[var(--surface-subtle)] transition-colors cursor-pointer"
                    title="Delete collection"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              )}
            </div>

            {/* Sources Header Row */}
            <div className="flex items-center justify-between px-1">
              <span className="text-xs text-[var(--muted-foreground)]">
                {activeSources.length} item{activeSources.length === 1 ? '' : 's'} in collection
              </span>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setIsAddSourceOpen(true)}
                  className="px-3 py-1.5 rounded-lg bg-[var(--surface-elevated)] hover:bg-[var(--surface-subtle)] border border-[var(--border)] text-xs text-[var(--foreground)] flex items-center gap-1.5 transition-colors cursor-pointer"
                >
                  <span>Attach from library</span>
                </button>
                <button
                  onClick={handleOpenUnifiedAdd}
                  className="px-3 py-1.5 rounded-lg bg-[var(--primary)] hover:opacity-90 text-[var(--primary-foreground)] text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer shadow-xs"
                >
                  <Plus className="h-3 w-3" />
                  <span>Add Content</span>
                </button>
              </div>
            </div>

            {/* Sources List */}
            <div className="space-y-2">
              {activeSources.length === 0 ? (
                <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-elevated)] p-8 text-center text-xs text-[var(--muted-foreground)]">
                  No content in this collection yet. Click &ldquo;Add Content&rdquo; to add a Document, Link, or Note.
                </div>
              ) : (
                activeSources.map((item, index) => {
                  const meta: CanonicalContentMeta = getCanonicalContentMeta(item);
                  const bgPastel = folderBgPalette[index % folderBgPalette.length];

                  return (
                    <div
                      key={item.id}
                      className="p-3.5 rounded-xl bg-[var(--surface-elevated)] hover:bg-[var(--surface-subtle)] border border-[var(--border)] flex items-center justify-between gap-3 transition-colors group"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className={`h-8 w-8 rounded-lg ${bgPastel} flex items-center justify-center shrink-0`}>
                          {meta.primaryType === 'Document' && <FileText className="h-4 w-4" />}
                          {meta.primaryType === 'Link' && <LinkIcon className="h-4 w-4" />}
                          {meta.primaryType === 'Note' && <StickyNote className="h-4 w-4" />}
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-[var(--foreground)] truncate">
                            {meta.title}
                          </p>
                          <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)] mt-0.5">
                            <span className="font-semibold text-[var(--foreground)]">{meta.primaryType}</span>
                            {meta.secondaryBadge && (
                              <>
                                <span>&middot;</span>
                                <span>{meta.secondaryBadge}</span>
                              </>
                            )}
                            {meta.statBadge && (
                              <>
                                <span>&middot;</span>
                                <span>{meta.statBadge}</span>
                              </>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0 text-xs">
                        {meta.url && (
                          <a
                            href={meta.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="p-1.5 rounded-lg text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--surface-subtle)]"
                            title="Open external URL"
                          >
                            <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        )}

                        <button
                          onClick={() => handleRemoveSource(String(item.id))}
                          disabled={removingItemId === String(item.id)}
                          className="px-2 py-1 rounded-md text-[11px] text-[var(--muted-foreground)] hover:text-rose-500 hover:bg-rose-500/10 flex items-center gap-1 transition-colors cursor-pointer"
                          title="Remove from this collection (preserves original item in library)"
                        >
                          <MinusCircle className="h-3.5 w-3.5" />
                          <span className="hidden sm:inline">Remove</span>
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* Modal: Create Collection */}
        {isCreateOpen && (
          <Modal
            isOpen={true}
            onClose={() => setIsCreateOpen(false)}
            title="Create New Collection"
          >
            <form onSubmit={handleCreate} className="space-y-4">
              {createError && (
                <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-500 text-xs">
                  {createError}
                </div>
              )}
              <Input
                label="Collection Name"
                placeholder="e.g. AI Research, System Architecture"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                required
              />
              <div className="space-y-1">
                <label className="text-xs font-medium text-[var(--foreground)]">Description</label>
                <textarea
                  placeholder="Optional description of this collection's focus"
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  className="w-full rounded-xl border border-[var(--border)] bg-[var(--surface-base)] p-3 text-xs text-[var(--foreground)] placeholder-[var(--muted-foreground)] focus:outline-hidden focus:border-[var(--foreground)] h-24"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" size="sm" type="button" onClick={() => setIsCreateOpen(false)}>
                  Cancel
                </Button>
                <button
                  type="submit"
                  disabled={isSubmitting || !newName.trim()}
                  className="px-4 py-2 rounded-lg bg-[var(--primary)] hover:opacity-90 text-[var(--primary-foreground)] text-xs font-medium transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {isSubmitting ? 'Creating...' : 'Create collection'}
                </button>
              </div>
            </form>
          </Modal>
        )}

        {/* Modal: Rename Collection */}
        {isRenameOpen && (
          <Modal
            isOpen={true}
            onClose={() => setIsRenameOpen(false)}
            title="Rename Collection"
          >
            <form onSubmit={handleRename} className="space-y-4">
              {renameError && (
                <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-500 text-xs">
                  {renameError}
                </div>
              )}
              <Input
                label="Collection Name"
                placeholder="New collection name"
                value={renameName}
                onChange={(e) => setRenameName(e.target.value)}
                required
              />
              <div className="space-y-1">
                <label className="text-xs font-medium text-[var(--foreground)]">Description</label>
                <textarea
                  placeholder="Collection description"
                  value={renameDesc}
                  onChange={(e) => setRenameDesc(e.target.value)}
                  className="w-full rounded-xl border border-[var(--border)] bg-[var(--surface-base)] p-3 text-xs text-[var(--foreground)] placeholder-[var(--muted-foreground)] focus:outline-hidden focus:border-[var(--foreground)] h-24"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" size="sm" type="button" onClick={() => setIsRenameOpen(false)}>
                  Cancel
                </Button>
                <button
                  type="submit"
                  disabled={
                    isRenaming ||
                    !renameName.trim() ||
                    (renameName.trim() === selectedCol.name && renameDesc.trim() === (selectedCol.description || ''))
                  }
                  className="px-4 py-2 rounded-lg bg-[var(--primary)] hover:opacity-90 text-[var(--primary-foreground)] text-xs font-medium transition-colors disabled:opacity-50 cursor-pointer flex items-center gap-1.5"
                >
                  {isRenaming && <Loader2 className="h-3 w-3 animate-spin" />}
                  <span>{isRenaming ? 'Saving...' : 'Save changes'}</span>
                </button>
              </div>
            </form>
          </Modal>
        )}

        {/* Modal: Add Items into Collection */}
        <CollectionAddModal
          isOpen={isAddSourceOpen}
          onClose={() => setIsAddSourceOpen(false)}
          collection={{ id: String(selectedCol.id), name: selectedCol.name }}
          onSuccess={async () => {
            await loadData();
          }}
          existingLibraryItems={allSources}
          onAttachExisting={handleAssignSource}
        />

        {/* Standardized Delete Collection Confirmation Modal */}
        <DeleteConfirmationModal
          isOpen={!!colToDelete}
          onClose={() => {
            if (!isDeleting) {
              setColToDelete(null);
              setDeleteError(null);
            }
          }}
          onConfirm={handleDeleteCollection}
          title="Delete this collection?"
          itemName={colToDelete?.name}
          itemType="collection"
          itemMeta={`${colToDelete?.item_count || 0} items organized`}
          consequenceText="The collection grouping will be removed. Your underlying saved documents, links, and notes will remain safely in your library."
          isDeleting={isDeleting}
          errorMessage={deleteError}
          confirmLabel="Delete permanently"
        />
      </div>
    </ShellLayout>
  );
}
