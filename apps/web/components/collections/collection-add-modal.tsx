'use client';

import * as React from 'react';
import {
  UploadCloud,
  Link as LinkIcon,
  FileText,
  Bookmark,
  Check,
  AlertCircle,
  Loader2,
  X,
  Search,
  ExternalLink
} from 'lucide-react';
import { Modal } from '@/components/ui/modal';
import { Input } from '@/components/ui/input';
import { UploadProgressBar } from '@/components/ui/loading-states';
import { getCanonicalContentMeta } from '@/lib/content-utils';

export type CollectionAddMode = 'document' | 'link' | 'note' | 'existing';

export interface CollectionAddModalProps {
  isOpen: boolean;
  onClose: () => void;
  collection: {
    id: string;
    name: string;
  };
  onSuccess?: (newItem: any) => void;
  existingLibraryItems?: any[];
  onAttachExisting?: (itemId: string) => Promise<void>;
}

export function CollectionAddModal({
  isOpen,
  onClose,
  collection,
  onSuccess,
  existingLibraryItems = [],
  onAttachExisting,
}: CollectionAddModalProps) {
  const [activeTab, setActiveTab] = React.useState<CollectionAddMode>('document');
  const [url, setUrl] = React.useState('');
  const [title, setTitle] = React.useState('');
  const [noteContent, setNoteContent] = React.useState('');
  const [tags, setTags] = React.useState('');
  const [file, setFile] = React.useState<File | null>(null);
  const [isDragging, setIsDragging] = React.useState(false);
  const [isLoading, setIsLoading] = React.useState(false);
  const [uploadProgress, setUploadProgress] = React.useState<number | null>(null);
  const [isSuccess, setIsSuccess] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  // Existing library search filter
  const [existingSearch, setExistingSearch] = React.useState('');
  const [attachingId, setAttachingId] = React.useState<string | null>(null);

  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const resetForm = () => {
    setUrl('');
    setTitle('');
    setNoteContent('');
    setTags('');
    setFile(null);
    setIsDragging(false);
    setIsSuccess(false);
    setUploadProgress(null);
    setErrorMessage(null);
    setExistingSearch('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  React.useEffect(() => {
    if (!isOpen) {
      resetForm();
    }
  }, [isOpen]);

  const uploadFileWithProgress = (formData: FormData, onProgress: (pct: number) => void): Promise<Response> => {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/v1/content/files/');

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          const pct = Math.round((event.loaded / event.total) * 100);
          onProgress(pct);
        }
      };

      xhr.onload = () => {
        resolve(
          new Response(xhr.responseText, {
            status: xhr.status,
            statusText: xhr.statusText,
            headers: { 'Content-Type': xhr.getResponseHeader('Content-Type') || 'application/json' },
          })
        );
      };

      xhr.onerror = () => reject(new Error('Network error during file upload.'));
      xhr.onabort = () => reject(new Error('Upload was cancelled.'));
      xhr.send(formData);
    });
  };

  const handleFileSelect = (selectedFile: File) => {
    setErrorMessage(null);
    const ext = selectedFile.name.slice(selectedFile.name.lastIndexOf('.')).toLowerCase();
    const allowed = ['.pdf', '.docx', '.pptx', '.xlsx', '.csv', '.txt', '.md', '.markdown'];

    if (!allowed.includes(ext)) {
      setErrorMessage(`Unsupported format '${ext}'. Allowed: PDF, DOCX, PPTX, XLSX, CSV, TXT, MD.`);
      return;
    }

    if (selectedFile.size > 50 * 1024 * 1024) {
      setErrorMessage('File size exceeds the 50MB limit.');
      return;
    }

    setFile(selectedFile);
    if (!title) {
      setTitle(selectedFile.name.replace(/\.[^/.]+$/, ''));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isLoading) return;

    setIsLoading(true);
    setErrorMessage(null);
    setIsSuccess(false);

    try {
      let res: Response;
      const tagList = tags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean);

      const targetColId = collection.id !== 'default' ? collection.id : undefined;

      if (activeTab === 'link') {
        if (!url.trim()) {
          setErrorMessage('Please provide a valid website or video URL.');
          setIsLoading(false);
          return;
        }

        res = await fetch('/api/v1/content/urls/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            url: url.trim(),
            title: title.trim() || undefined,
            collection_id: targetColId,
            tags: tagList,
          }),
        });
      } else if (activeTab === 'note') {
        if (!noteContent.trim()) {
          setErrorMessage('Note content cannot be empty.');
          setIsLoading(false);
          return;
        }

        res = await fetch('/api/v1/content/notes/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: title.trim() || undefined,
            content: noteContent.trim(),
            collection_id: targetColId,
            tags: tagList,
          }),
        });
      } else if (activeTab === 'document') {
        if (!file) {
          setErrorMessage('Please select a document file to upload.');
          setIsLoading(false);
          return;
        }

        const formData = new FormData();
        formData.append('file', file);
        if (title.trim()) {
          formData.append('title', title.trim());
        }
        if (targetColId) {
          formData.append('collection_id', targetColId);
        }
        tagList.forEach((t) => formData.append('tags', t));

        setUploadProgress(0);
        res = await uploadFileWithProgress(formData, (pct) => {
          setUploadProgress(pct);
        });
      } else {
        setIsLoading(false);
        return;
      }

      if (!res.ok) {
        const requestId = res.headers.get('x-request-id') || '';
        const errJson = await res.json().catch(() => ({}));
        let msg = 'Failed to create item in this collection.';
        if (errJson?.error) {
          msg = typeof errJson.error === 'string' ? errJson.error : errJson.error.message || JSON.stringify(errJson.error);
        } else if (errJson?.detail) {
          msg = errJson.detail;
        }
        const refId = errJson?.error?.request_id || requestId;
        if (refId && !msg.includes(refId)) {
          msg = `${msg} (Ref: ${refId})`;
        }
        throw new Error(msg);
      }

      const createdItem = await res.json();
      setIsLoading(false);
      setIsSuccess(true);

      if (onSuccess) {
        onSuccess(createdItem);
      }

      // Notify global listeners
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('library-item-added', { detail: createdItem }));
      }

      resetForm();
      onClose();
    } catch (err: any) {
      setErrorMessage(err.message || 'An unexpected error occurred.');
      setIsLoading(false);
    }
  };

  const handleAttachExisting = async (itemId: string) => {
    if (attachingId || !onAttachExisting) return;
    setAttachingId(itemId);
    setErrorMessage(null);

    try {
      await onAttachExisting(itemId);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to attach item to collection.');
    } finally {
      setAttachingId(null);
    }
  };

  const filteredLibrary = React.useMemo(() => {
    if (!existingSearch.trim()) return existingLibraryItems;
    const q = existingSearch.toLowerCase();
    return existingLibraryItems.filter(
      (item) =>
        (item.title && item.title.toLowerCase().includes(q)) ||
        (item.source_url && item.source_url.toLowerCase().includes(q)) ||
        (item.summary && item.summary.toLowerCase().includes(q))
    );
  }, [existingLibraryItems, existingSearch]);

  const tabOptions: Array<{ id: CollectionAddMode; label: string; icon: React.ComponentType<{ className?: string }> }> = [
    { id: 'document', label: 'Document', icon: UploadCloud },
    { id: 'link', label: 'Link', icon: LinkIcon },
    { id: 'note', label: 'Note', icon: FileText },
    { id: 'existing', label: 'From library', icon: Bookmark },
  ];

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Add items to ${collection.name}`}
      description="Ingest new sources or organize existing material directly into this collection."
      className="max-w-xl"
    >
      <div className="space-y-4">
        {/* Navigation Tabs */}
        <div
          role="tablist"
          aria-label="Add content types"
          className="grid grid-cols-2 sm:grid-cols-4 gap-1 rounded-xl bg-[var(--surface-subtle)] p-1 border border-[var(--border)]"
        >
          {tabOptions.map((t) => {
            const Icon = t.icon;
            const isSelected = activeTab === t.id;

            return (
              <button
                key={t.id}
                role="tab"
                aria-selected={isSelected}
                type="button"
                onClick={() => {
                  setActiveTab(t.id);
                  setErrorMessage(null);
                }}
                className={`flex items-center justify-center gap-1.5 py-2 px-2 rounded-lg text-xs font-medium transition-all cursor-pointer min-h-[38px] ${
                  isSelected
                    ? 'bg-[var(--surface-elevated)] text-[var(--foreground)] border border-[var(--border)] shadow-xs font-semibold'
                    : 'text-[var(--foreground-muted)] hover:text-[var(--foreground)]'
                }`}
              >
                <Icon className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{t.label}</span>
              </button>
            );
          })}
        </div>

        {errorMessage && (
          <div className="flex items-center gap-2 p-3 rounded-xl bg-rose-500/10 border border-rose-500/25 text-rose-500 text-xs">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span className="break-words">{errorMessage}</span>
          </div>
        )}

        {isSuccess && (
          <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-500 text-xs">
            <Check className="h-4 w-4 shrink-0" />
            <span>Item successfully added to {collection.name}.</span>
          </div>
        )}

        {/* TAB 1: UPLOAD DOCUMENT */}
        {activeTab === 'document' && (
          <form onSubmit={handleSubmit} className="space-y-4 pt-1">
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={(e) => {
                e.preventDefault();
                setIsDragging(false);
              }}
              onDrop={(e) => {
                e.preventDefault();
                setIsDragging(false);
                if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                  handleFileSelect(e.dataTransfer.files[0]);
                }
              }}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-5 sm:p-6 text-center cursor-pointer transition-all ${
                isDragging
                  ? 'border-[var(--accent-sand)] bg-[var(--accent-sand-muted)]'
                  : file
                  ? 'border-emerald-500/50 bg-emerald-500/5'
                  : 'border-[var(--border)] hover:border-[var(--border-hover)] bg-[var(--surface-base)]'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept=".pdf,.docx,.pptx,.xlsx,.csv,.txt,.md,.markdown"
                onChange={(e) => {
                  if (e.target.files && e.target.files.length > 0) {
                    handleFileSelect(e.target.files[0]);
                  }
                }}
              />
              {file ? (
                <div className="space-y-1">
                  <Check className="mx-auto h-6 w-6 text-emerald-500" />
                  <p className="text-xs font-semibold text-[var(--foreground)] break-all max-w-full">
                    {file.name}
                  </p>
                  <p className="text-[11px] text-[var(--foreground-muted)] font-mono">
                    {(file.size / (1024 * 1024)).toFixed(2)} MB · Click to choose different file
                  </p>
                </div>
              ) : (
                <div className="space-y-1.5">
                  <UploadCloud className="mx-auto h-7 w-7 text-[var(--foreground-muted)]" />
                  <p className="text-xs font-medium text-[var(--foreground)]">
                    Drop document here or <span className="text-[var(--accent-sand)] underline">browse files</span>
                  </p>
                  <p className="text-[11px] text-[var(--foreground-muted)] leading-relaxed">
                    Supports PDF, DOCX, PPTX, XLSX, CSV, TXT, MD (Max 50MB)
                  </p>
                </div>
              )}
            </div>

            {uploadProgress !== null && (
              <UploadProgressBar progress={uploadProgress} filename={file?.name} />
            )}

            <div>
              <label className="block text-xs font-medium text-[var(--foreground)] mb-1">
                Document Title (Optional)
              </label>
              <Input
                placeholder="Defaults to filename"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-[var(--foreground)] mb-1">
                Tags (Optional, comma-separated)
              </label>
              <Input
                placeholder="e.g. report, q4, deep-learning"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
              />
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-[var(--border)]">
              <span className="text-[11px] text-[var(--foreground-muted)]">
                Assigned to: <strong className="text-[var(--foreground)]">{collection.name}</strong>
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-3 py-1.5 rounded-lg border border-[var(--border)] text-xs text-[var(--foreground)] hover:bg-[var(--surface-hover)] cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isLoading || !file}
                  className="px-4 py-1.5 rounded-lg bg-[var(--primary)] text-[var(--primary-foreground)] text-xs font-medium hover:opacity-90 disabled:opacity-50 transition-opacity flex items-center gap-1.5 cursor-pointer shadow-xs"
                >
                  {isLoading && <Loader2 className="h-3 w-3 animate-spin" />}
                  <span>{isLoading ? 'Uploading...' : `Add to ${collection.name}`}</span>
                </button>
              </div>
            </div>
          </form>
        )}

        {/* TAB 2: INGEST LINK */}
        {activeTab === 'link' && (
          <form onSubmit={handleSubmit} className="space-y-4 pt-1">
            <div>
              <label className="block text-xs font-medium text-[var(--foreground)] mb-1">
                URL or Video Link
              </label>
              <Input
                type="url"
                required
                placeholder="https://example.com/article or YouTube video"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
              <p className="text-[11px] text-[var(--foreground-muted)] mt-1">
                Content is extracted, cleaned, and indexed for search and RAG conversations.
              </p>
            </div>

            <div>
              <label className="block text-xs font-medium text-[var(--foreground)] mb-1">
                Title (Optional)
              </label>
              <Input
                placeholder="Auto-extracted if left blank"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-[var(--foreground)] mb-1">
                Tags (Optional, comma-separated)
              </label>
              <Input
                placeholder="e.g. video, tutorial, ai"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
              />
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-[var(--border)]">
              <span className="text-[11px] text-[var(--foreground-muted)]">
                Assigned to: <strong className="text-[var(--foreground)]">{collection.name}</strong>
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-3 py-1.5 rounded-lg border border-[var(--border)] text-xs text-[var(--foreground)] hover:bg-[var(--surface-hover)] cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isLoading || !url.trim()}
                  className="px-4 py-1.5 rounded-lg bg-[var(--primary)] text-[var(--primary-foreground)] text-xs font-medium hover:opacity-90 disabled:opacity-50 transition-opacity flex items-center gap-1.5 cursor-pointer shadow-xs"
                >
                  {isLoading && <Loader2 className="h-3 w-3 animate-spin" />}
                  <span>{isLoading ? 'Ingesting...' : `Save link`}</span>
                </button>
              </div>
            </div>
          </form>
        )}

        {/* TAB 3: WRITE NOTE */}
        {activeTab === 'note' && (
          <form onSubmit={handleSubmit} className="space-y-4 pt-1">
            <div>
              <label className="block text-xs font-medium text-[var(--foreground)] mb-1">
                Note Title
              </label>
              <Input
                placeholder="e.g. Distributed Consensus Thoughts"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-[var(--foreground)] mb-1">
                Note Content (Markdown supported)
              </label>
              <textarea
                required
                rows={6}
                placeholder="Write your research synthesis, meeting notes, or project specifications here..."
                value={noteContent}
                onChange={(e) => setNoteContent(e.target.value)}
                className="w-full rounded-xl border border-[var(--border)] bg-[var(--surface-base)] p-3 text-xs text-[var(--foreground)] placeholder-[var(--foreground-muted)] focus:outline-hidden focus:border-[var(--foreground)] transition-colors leading-relaxed font-sans"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-[var(--foreground)] mb-1">
                Tags (Optional, comma-separated)
              </label>
              <Input
                placeholder="e.g. synthesis, personal"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
              />
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-[var(--border)]">
              <span className="text-[11px] text-[var(--foreground-muted)]">
                Assigned to: <strong className="text-[var(--foreground)]">{collection.name}</strong>
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-3 py-1.5 rounded-lg border border-[var(--border)] text-xs text-[var(--foreground)] hover:bg-[var(--surface-hover)] cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isLoading || !noteContent.trim()}
                  className="px-4 py-1.5 rounded-lg bg-[var(--primary)] text-[var(--primary-foreground)] text-xs font-medium hover:opacity-90 disabled:opacity-50 transition-opacity flex items-center gap-1.5 cursor-pointer shadow-xs"
                >
                  {isLoading && <Loader2 className="h-3 w-3 animate-spin" />}
                  <span>{isLoading ? 'Saving...' : `Save note`}</span>
                </button>
              </div>
            </div>
          </form>
        )}

        {/* TAB 4: FROM LIBRARY (ATTACH EXISTING) */}
        {activeTab === 'existing' && (
          <div className="space-y-3 pt-1">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-[var(--foreground-muted)]" />
              <input
                type="text"
                placeholder="Search your library..."
                value={existingSearch}
                onChange={(e) => setExistingSearch(e.target.value)}
                className="w-full pl-9 pr-3 py-2 rounded-xl bg-[var(--surface-base)] border border-[var(--border)] text-xs text-[var(--foreground)] placeholder-[var(--foreground-muted)] focus:outline-hidden focus:border-[var(--foreground)]"
              />
            </div>

            <div className="space-y-2 max-h-64 sm:max-h-72 overflow-y-auto pr-1">
              {filteredLibrary.length === 0 ? (
                <div className="py-8 text-center text-xs text-[var(--foreground-muted)]">
                  {existingSearch ? 'No items match your search.' : 'No items found in your library.'}
                </div>
              ) : (
                filteredLibrary.map((item) => {
                  const meta = getCanonicalContentMeta(item);
                  const isAlreadyInCol =
                    String(item.collection) === String(collection.id) ||
                    String(item.collection_id) === String(collection.id);

                  return (
                    <div
                      key={item.id}
                      className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--border)] flex items-center justify-between gap-3 text-xs"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-[var(--foreground)] truncate">
                          {item.title || meta.secondaryLabel || 'Untitled item'}
                        </p>
                        <p className="text-[11px] text-[var(--foreground-muted)] truncate mt-0.5">
                          {meta.primaryType} &middot; {item.collection_name ? `Current: ${item.collection_name}` : 'Unfiled'}
                        </p>
                      </div>

                      <button
                        type="button"
                        onClick={() => handleAttachExisting(String(item.id))}
                        disabled={attachingId === String(item.id) || isAlreadyInCol}
                        className={`px-3 py-1.5 rounded-lg text-xs font-medium shrink-0 transition-colors cursor-pointer ${
                          isAlreadyInCol
                            ? 'bg-[var(--surface-subtle)] text-[var(--foreground-muted)] cursor-default'
                            : 'bg-[var(--primary)] text-[var(--primary-foreground)] hover:opacity-90 shadow-2xs'
                        }`}
                      >
                        {isAlreadyInCol ? 'Attached' : attachingId === String(item.id) ? 'Attaching...' : 'Attach'}
                      </button>
                    </div>
                  );
                })
              )}
            </div>

            <div className="flex justify-end pt-2 border-t border-[var(--border)]">
              <button
                type="button"
                onClick={onClose}
                className="px-3.5 py-1.5 rounded-lg border border-[var(--border)] text-xs text-[var(--foreground)] hover:bg-[var(--surface-hover)] cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
