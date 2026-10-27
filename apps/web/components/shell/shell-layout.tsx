'use client';

import * as React from 'react';
import { Sidebar } from '@/components/shell/sidebar';
import { QuickAddModal } from '@/components/shell/quick-add-modal';
import { BrandLogo } from '@/components/ui/brand-logo';
import { Menu, HelpCircle, Plus } from 'lucide-react';

interface ShellLayoutProps {
  children: React.ReactNode;
}

export function ShellLayout({ children }: ShellLayoutProps) {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = React.useState(false);
  const [isMobileNavOpen, setIsMobileNavOpen] = React.useState(false);
  const [isQuickAddOpen, setIsQuickAddOpen] = React.useState(false);
  const [quickAddTab, setQuickAddTab] = React.useState<'document' | 'link' | 'note'>('document');
  const [quickAddColId, setQuickAddColId] = React.useState<string | undefined>(undefined);
  const [showHelpModal, setShowHelpModal] = React.useState(false);

  // Listen for global open quick-add event
  React.useEffect(() => {
    const handleOpenQuickAdd = (event: Event) => {
      const customEvent = event as CustomEvent;
      if (customEvent.detail?.tab) {
        setQuickAddTab(customEvent.detail.tab);
      } else {
        setQuickAddTab('document');
      }
      setQuickAddColId(customEvent.detail?.collectionId || undefined);
      setIsQuickAddOpen(true);
    };
    window.addEventListener('evermind:open-quick-add', handleOpenQuickAdd);
    window.addEventListener('mediacompile:open-quick-add', handleOpenQuickAdd);
    return () => {
      window.removeEventListener('evermind:open-quick-add', handleOpenQuickAdd);
      window.removeEventListener('mediacompile:open-quick-add', handleOpenQuickAdd);
    };
  }, []);

  return (
    <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)] flex flex-col antialiased selection:bg-[#d4c3b3]/30 selection:text-white transition-colors">
      {/* Mobile Top Bar (< lg only) */}
      <div className="lg:hidden h-14 border-b border-[var(--border)] bg-[var(--surface)]/90 backdrop-blur-md px-4 flex items-center justify-between sticky top-0 z-30">
        <button
          onClick={() => setIsMobileNavOpen(true)}
          className="p-1.5 rounded-lg text-[var(--foreground-muted)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)] transition-colors"
          aria-label="Open navigation menu"
        >
          <Menu className="h-5 w-5" />
        </button>

        <BrandLogo showWordmark={true} size="sm" />

        <button
          onClick={() => setIsQuickAddOpen(true)}
          className="p-1.5 rounded-lg text-[var(--foreground-muted)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)] transition-colors"
          aria-label="Add content"
        >
          <Plus className="h-5 w-5" />
        </button>
      </div>

      <div className="flex flex-1 min-h-0">
        {/* Responsive Sidebar */}
        <Sidebar
          isCollapsed={isSidebarCollapsed}
          setIsCollapsed={setIsSidebarCollapsed}
          isMobileOpen={isMobileNavOpen}
          setIsMobileOpen={setIsMobileNavOpen}
        />

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col min-w-0 bg-[var(--background)] relative">
          <main className="flex-1 p-6 lg:p-10 w-full max-w-[1400px] mx-auto animate-in fade-in duration-200 pb-20">
            {children}
          </main>

          {/* Floating Help Button (?) */}
          <button
            onClick={() => setShowHelpModal(true)}
            aria-label="Help and shortcuts"
            title="Help & Shortcuts"
            className="fixed bottom-5 right-5 z-40 h-8 w-8 rounded-full bg-[var(--surface-elevated)] hover:bg-[var(--surface-hover)] border border-[var(--border)] text-[var(--foreground-muted)] hover:text-[var(--foreground)] flex items-center justify-center text-xs font-semibold shadow-lg transition-all cursor-pointer"
          >
            ?
          </button>
        </div>
      </div>

      {/* Global Quick Add Modal */}
      <QuickAddModal
        isOpen={isQuickAddOpen}
        onClose={() => setIsQuickAddOpen(false)}
        initialTab={quickAddTab}
        defaultCollectionId={quickAddColId}
      />

      {/* Help Modal */}
      {showHelpModal && (
        <div
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150"
          onClick={() => setShowHelpModal(false)}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-[var(--border)] bg-[var(--surface-elevated)] text-[var(--foreground)] p-6 shadow-2xl space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-3 border-b border-[var(--border)]">
              <h3 className="text-base font-semibold text-[var(--foreground)] flex items-center gap-2">
                <HelpCircle className="h-4 w-4 text-[var(--accent-sand)]" />
                Evermind Help & Shortcuts
              </h3>
              <button
                onClick={() => setShowHelpModal(false)}
                className="text-[var(--foreground-muted)] hover:text-[var(--foreground)] text-xs p-1"
              >
                ✕
              </button>
            </div>
            <div className="space-y-3 text-xs text-[var(--foreground-muted)]">
              <p>
                <strong className="text-[var(--foreground)]">Grounded Personal RAG:</strong> Add PDFs, YouTube transcripts, notes, and web content to build your knowledge base.
              </p>
              <div className="space-y-2 pt-2">
                <div className="flex justify-between py-1 border-b border-[var(--border)] font-mono text-[11px]">
                  <span>Ask AI Assistant</span>
                  <span className="text-[var(--foreground-muted)]">⌘ + ↵ / Enter</span>
                </div>
                <div className="flex justify-between py-1 border-b border-[var(--border)] font-mono text-[11px]">
                  <span>Add URL or PDF</span>
                  <span className="text-[var(--foreground-muted)]">Content Library &gt; Upload</span>
                </div>
                <div className="flex justify-between py-1 font-mono text-[11px]">
                  <span>Vector Database</span>
                  <span className="text-[var(--foreground-muted)]">pgvector 384d</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
