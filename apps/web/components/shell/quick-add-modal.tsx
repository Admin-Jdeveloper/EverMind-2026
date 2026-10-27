'use client';

import * as React from 'react';
import {
  FileText,
  Link as LinkIcon,
  UploadCloud,
  Check,
  AlertCircle,
  Folder,
  Loader2,
  X
} from 'lucide-react';
import { Modal } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { UploadProgressBar } from '@/components/ui/loading-states';

export type AddContentType = 'document' | 'link' | 'note';

interface QuickAddModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (item: any) => void;
  initialTab?: AddContentType;
  defaultCollectionId?: string;
}

interface CollectionOption {
  id: string;
  name: string;
}

export function QuickAddModal({
  isOpen,
  onClose,
  onSuccess,
  initialTab = 'document',
  defaultCollectionId
}: QuickAddModalProps) {
  const [activeTab, setActiveTab] = React.useState<AddContentType>(initialTab);
  const [url, setUrl] = React.useState('');
  const [title, setTitle] = React.useState('');
  const [noteContent, setNoteContent] = React.useState('');
  const [tags, setTags] = React.useState('');
  const [selectedCollectionId, setSelectedCollectionId] = React.useState(defaultCollectionId || '');
  const [collections, setCollections] = React.useState<CollectionOption[]>([]);
  const [file, setFile] = React.useState<File | null>(null);
  const [isDragging, setIsDragging] = React.useState(false);
  const [isLoading, setIsLoading] = React.useState(false);
  const [uploadProgress, setUploadProgress] = React.useState<number | null>(null);
  const [isSuccess, setIsSuccess] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const fileInputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (initialTab) setActiveTab(initialTab);
    if (defaultCollectionId) setSelectedCollectionId(defaultCollectionId);
  }, [initialTab, defaultCollectionId]);

  // Load user's real collections from backend
  React.useEffect(() => {
    if (!isOpen) return;
    async function loadCollections() {
      try {
        const res = await fetch('/api/v1/content/collections/');
        if (res.ok) {
          const data = await res.json();
          const list = Array.isArray(data) ? data : data.results || [];
          setCollections(list.map((c: any) => ({ id: String(c.id), name: c.name })));
        }
      } catch {
        // Leave list empty if unauthenticated
      }
    }
    loadCollections();
  }, [isOpen]);

  const resetForm = () => {
    setUrl('');
    setTitle('');
    setNoteContent('');
    setTags('');
    setSelectedCollectionId(defaultCollectionId || '');
    setFile(null);
    setIsDragging(false);
    setIsSuccess(false);
    setUploadProgress(null);
    setErrorMessage(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

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
      setErrorMessage(`Unsupported format '${ext}'. Supported: PDF, DOCX, PPTX, XLSX, CSV, TXT, MD.`);
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
    if (isLoading) return; // Prevent duplicate submissions

    setIsLoading(true);
    setErrorMessage(null);
    setIsSuccess(false);

    try {
      let res: Response;
      const tagList = tags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean);

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
            collection_id: selectedCollectionId || null,
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
            collection_id: selectedCollectionId || null,
            tags: tagList,
          }),
        });
      } else {
        // Document
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
        if (selectedCollectionId) {
          formData.append('collection_id', selectedCollectionId);
        }
        tagList.forEach((t) => formData.append('tags', t));

        setUploadProgress(0);
        res = await uploadFileWithProgress(formData, (pct) => {
          setUploadProgress(pct);
        });
      }

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        let errorMsg = 'Failed to ingest content item.';
        if (typeof errorData === 'object' && errorData !== null) {
          if (errorData.error) {
            errorMsg = typeof errorData.error === 'string' ? errorData.error : errorData.error.message || JSON.stringify(errorData.error);
          } else if (errorData.detail) {
            errorMsg = errorData.detail;
          } else {
            const firstKey = Object.keys(errorData)[0];
            if (firstKey) {
              const val = errorData[firstKey];
              errorMsg = Array.isArray(val) ? `${firstKey}: ${val.join(' ')}` : `${firstKey}: ${val}`;
            }
          }
        }
        setErrorMessage(errorMsg);
        setIsLoading(false);
        return;
      }

      const createdItem = await res.json();
      setIsLoading(false);
      setIsSuccess(true);

      // Notify application views
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('library-item-added', { detail: createdItem }));
      }

      if (onSuccess) {
        onSuccess(createdItem);
      }

      setTimeout(() => {
        resetForm();
        onClose();
      }, 700);
    } catch (err: any) {
      setErrorMessage(err?.message || 'Network error while contacting server.');
      setIsLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Add Content"
      description="Select a content type to add to your personal library."
    >
      {/* Exactly Three Primary Choices */}
      <div className="grid grid-cols-3 gap-1 rounded-xl bg-[var(--surface-hover)] p-1 border border-[var(--border)] mb-4 sm:mb-5">
        <button
          type="button"
          onClick={() => {
            setActiveTab('document');
            setErrorMessage(null);
          }}
          className={`flex items-center justify-center gap-1 sm:gap-2 py-2 px-1 rounded-lg text-[11px] sm:text-xs font-medium transition-all cursor-pointer min-h-[36px] ${
            activeTab === 'document'
              ? 'bg-[var(--surface-elevated)] text-[var(--foreground)] border border-[var(--border)] shadow-2xs font-semibold'
              : 'text-[var(--foreground-muted)] hover:text-[var(--foreground)]'
          }`}
        >
          <UploadCloud className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">Document</span>
        </button>

        <button
          type="button"
          onClick={() => {
            setActiveTab('link');
            setErrorMessage(null);
          }}
          className={`flex items-center justify-center gap-1 sm:gap-2 py-2 px-1 rounded-lg text-[11px] sm:text-xs font-medium transition-all cursor-pointer min-h-[36px] ${
            activeTab === 'link'
              ? 'bg-[var(--surface-elevated)] text-[var(--foreground)] border border-[var(--border)] shadow-2xs font-semibold'
              : 'text-[var(--foreground-muted)] hover:text-[var(--foreground)]'
          }`}
        >
          <LinkIcon className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">Link</span>
        </button>

        <button
          type="button"
          onClick={() => {
            setActiveTab('note');
            setErrorMessage(null);
          }}
          className={`flex items-center justify-center gap-1 sm:gap-2 py-2 px-1 rounded-lg text-[11px] sm:text-xs font-medium transition-all cursor-pointer min-h-[36px] ${
            activeTab === 'note'
              ? 'bg-[var(--surface-elevated)] text-[var(--foreground)] border border-[var(--border)] shadow-2xs font-semibold'
              : 'text-[var(--foreground-muted)] hover:text-[var(--foreground)]'
          }`}
        >
          <FileText className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">Note</span>
        </button>
      </div>

      {errorMessage && (
        <div className="mb-4 flex items-center gap-2 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-500 text-xs break-words">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span className="break-words">{errorMessage}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Document Mode */}
        {activeTab === 'document' && (
          <div className="space-y-3">
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
              className={`border-2 border-dashed rounded-xl p-4 sm:p-6 text-center cursor-pointer transition-all ${
                isDragging
                  ? 'border-[var(--accent-sand)] bg-[var(--accent-sand-muted)]'
                  : file
                  ? 'border-emerald-500/50 bg-emerald-500/5'
                  : 'border-[var(--border)] hover:border-[var(--border-hover)] bg-[var(--surface)]'
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
                  <p className="text-xs font-semibold text-[var(--foreground)] break-all max-w-full">{file.name}</p>
                  <p className="text-xs text-[var(--foreground-muted)]">
                    {(file.size / (1024 * 1024)).toFixed(2)} MB · Click to change file
                  </p>
                </div>
              ) : (
                <div className="space-y-1.5">
                  <UploadCloud className="mx-auto h-7 w-7 text-[var(--foreground-muted)]" />
                  <p className="text-xs font-medium text-[var(--foreground)]">
                    Drop document here or <span className="text-[var(--accent-sand)] underline">browse</span>
                  </p>
                  <p className="text-[11px] text-[var(--foreground-muted)] leading-relaxed break-words px-2">
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
          </div>
        )}

        {/* Link Mode */}
        {activeTab === 'link' && (
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-[var(--foreground)] mb-1">
                Website or External URL
              </label>
              <Input
                type="url"
                required
                placeholder="https://example.com/article, YouTube, Instagram, X..."
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
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
          </div>
        )}

        {/* Note Mode */}
        {activeTab === 'note' && (
          <div className="space-y-3">
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
                Note Content
              </label>
              <textarea
                required
                rows={5}
                placeholder="Write your note, thoughts, or research notes..."
                value={noteContent}
                onChange={(e) => setNoteContent(e.target.value)}
                className="w-full px-3 py-2 rounded-xl bg-[var(--surface)] border border-[var(--border)] text-xs text-[var(--foreground)] placeholder-[var(--foreground-muted)] focus:outline-hidden focus:border-[var(--border-hover)] resize-none"
              />
            </div>
          </div>
        )}

        {/* Shared Collection Selector */}
        <div>
          <label className="block text-xs font-medium text-[var(--foreground)] mb-1">
            Assign to Collection (Optional)
          </label>
          <select
            value={selectedCollectionId}
            onChange={(e) => setSelectedCollectionId(e.target.value)}
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

        {/* Shared Tags Input */}
        <div>
          <label className="block text-xs font-medium text-[var(--foreground)] mb-1">
            Tags (Optional, comma separated)
          </label>
          <Input
            placeholder="ai, architecture, reading"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
          />
        </div>

        {/* Action Buttons */}
        <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-[var(--border)]">
          <Button type="button" variant="outline" size="sm" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>

          <Button
            type="submit"
            variant="primary"
            size="sm"
            disabled={isLoading || (activeTab === 'document' && !file)}
          >
            {isLoading ? (
              <span className="flex items-center gap-1.5">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Ingesting...
              </span>
            ) : isSuccess ? (
              <span className="flex items-center gap-1.5 text-emerald-400">
                <Check className="h-3.5 w-3.5" /> Added
              </span>
            ) : activeTab === 'document' ? (
              'Upload Document'
            ) : activeTab === 'link' ? (
              'Save Link'
            ) : (
              'Create Note'
            )}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
