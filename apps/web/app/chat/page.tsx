'use client';

import * as React from 'react';
import {
  Sparkles,
  Send,
  Plus,
  Search,
  Download,
  Copy,
  Check,
  Bookmark,
  Trash2,
  ExternalLink,
  Loader2,
  FileText,
  Link as LinkIcon,
  StickyNote,
  MessageSquare,
  Globe
} from 'lucide-react';
import { ShellLayout } from '@/components/shell/shell-layout';
import { FormattedMarkdown } from '@/components/ui/formatted-markdown';
import { Modal } from '@/components/ui/modal';
import { DeleteConfirmationModal } from '@/components/ui/delete-confirmation-modal';
import { useSession } from 'next-auth/react';
import { getUserInitial } from '@/lib/avatar';

interface Citation {
  citation_id?: string;
  source_index?: number;
  chunk_id: string;
  chunk_index?: number;
  item_id?: string;
  item_title: string;
  content_type?: string;
  source_url?: string;
  page_number?: number;
  timestamp?: string;
  timestamp_seconds?: number;
  timestamp_url?: string;
  excerpt: string;
  is_web?: boolean;
  platform?: string;
}

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  citations?: Citation[];
  timestamp: string;
  metadata?: Record<string, any>;
  answer_source?: string;
}

function renderSourceIndicator(answerSource?: string, metadata?: Record<string, any>, citations?: Citation[]) {
  const source = answerSource || metadata?.answer_source;

  if (source === 'saved_library') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium bg-[var(--surface-subtle)] text-[var(--foreground-muted)] border border-[var(--border)] select-none">
        <FileText className="h-2.5 w-2.5 text-[var(--accent-sand)]" />
        <span>Saved resources</span>
      </span>
    );
  }

  if (source === 'web_research') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium bg-[var(--surface-subtle)] text-[var(--foreground-muted)] border border-[var(--border)] select-none">
        <Globe className="h-2.5 w-2.5 text-sky-500" />
        <span>Internet</span>
      </span>
    );
  }

  if (source === 'saved_library_plus_web') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium bg-[var(--surface-subtle)] text-[var(--foreground-muted)] border border-[var(--border)] select-none">
        <Sparkles className="h-2.5 w-2.5 text-[var(--accent-sand)]" />
        <span>Saved resources + Internet</span>
      </span>
    );
  }

  if (source === 'general_knowledge') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium bg-[var(--surface-subtle)] text-[var(--foreground-muted)] border border-[var(--border)] select-none">
        <Sparkles className="h-2.5 w-2.5 text-[var(--foreground-muted)]" />
        <span>General knowledge</span>
      </span>
    );
  }

  // Fallback inferred strictly from verified citations when metadata is missing
  if (citations && citations.length > 0) {
    const hasWeb = citations.some((c) => c.is_web);
    const hasSaved = citations.some((c) => !c.is_web);
    if (hasWeb && hasSaved) {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium bg-[var(--surface-subtle)] text-[var(--foreground-muted)] border border-[var(--border)] select-none">
          <Sparkles className="h-2.5 w-2.5 text-[var(--accent-sand)]" />
          <span>Saved resources + Internet</span>
        </span>
      );
    }
    if (hasWeb) {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium bg-[var(--surface-subtle)] text-[var(--foreground-muted)] border border-[var(--border)] select-none">
          <Globe className="h-2.5 w-2.5 text-sky-500" />
          <span>Internet</span>
        </span>
      );
    }
    if (hasSaved) {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium bg-[var(--surface-subtle)] text-[var(--foreground-muted)] border border-[var(--border)] select-none">
          <FileText className="h-2.5 w-2.5 text-[var(--accent-sand)]" />
          <span>Saved resources</span>
        </span>
      );
    }
  }

  return null;
}

function getVisibleCitations(rawCitations?: Citation[]): Citation[] {
  if (!rawCitations || rawCitations.length === 0) return [];

  // Deduplicate citations by source identity
  const seen = new Set<string>();
  const topCitations: Citation[] = [];

  for (const c of rawCitations) {
    const key = c.item_id || c.source_url || c.item_title;
    if (!seen.has(key)) {
      seen.add(key);
      topCitations.push(c);
    }
    if (topCitations.length === 3) break;
  }

  // If fewer than 3 unique sources exist, add distinct chunks/pages up to 3 total
  if (topCitations.length < 3 && rawCitations.length > topCitations.length) {
    for (const c of rawCitations) {
      if (!topCitations.includes(c)) {
        topCitations.push(c);
      }
      if (topCitations.length === 3) break;
    }
  }

  return topCitations.slice(0, 3);
}

interface ChatSessionItem {
  id: string;
  title: string;
  message_count?: number;
  created_at?: string;
  updated_at?: string;
}

export default function ChatPage() {
  const { data: session } = useSession();
  const [sessions, setSessions] = React.useState<ChatSessionItem[]>([]);
  const [activeSessionId, setActiveSessionId] = React.useState<string | null>(null);
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [inputValue, setInputValue] = React.useState('');
  const [searchChats, setSearchChats] = React.useState('');
  const [isGenerating, setIsGenerating] = React.useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = React.useState(false);
  const [copiedId, setCopiedId] = React.useState<string | null>(null);
  const [savedId, setSavedId] = React.useState<string | null>(null);
  const [isMobileChatsOpen, setIsMobileChatsOpen] = React.useState(false);

  // Citation modal
  const [activeCitation, setActiveCitation] = React.useState<Citation | null>(null);

  // Delete modal
  const [sessionToDelete, setSessionToDelete] = React.useState<ChatSessionItem | null>(null);
  const [isDeletingSession, setIsDeletingSession] = React.useState(false);
  const [sessionDeleteError, setSessionDeleteError] = React.useState<string | null>(null);

  const messagesEndRef = React.useRef<HTMLDivElement>(null);

  const displayName = session?.user?.name || (session?.user?.email ? session.user.email.split('@')[0] : 'You');
  const initial = getUserInitial(session?.user?.name, session?.user?.email, 'U');

  // Read URL query
  React.useEffect(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const q = params.get('query');
      if (q) setInputValue(q);
    }
  }, []);

  React.useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isGenerating]);

  // Load chat sessions from backend
  const loadSessions = React.useCallback(async () => {
    try {
      const res = await fetch('/api/v1/chat/sessions/', { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        const list: ChatSessionItem[] = Array.isArray(data) ? data : data.results || [];
        setSessions(list);
        if (list.length > 0) {
          setActiveSessionId((prev) => {
            if (prev && list.some((s) => s.id === prev)) {
              return prev;
            }
            loadMessages(list[0].id);
            return list[0].id;
          });
        }
      }
    } catch (err) {
      console.error('Failed to load chat sessions:', err);
    }
  }, []);

  React.useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // Load messages for a session
  const loadMessages = async (sessionId: string) => {
    setIsLoadingMessages(true);
    try {
      const res = await fetch(`/api/v1/chat/sessions/${sessionId}/`);
      if (res.ok) {
        const data = await res.json();
        const rawMsgs = data.messages || [];
        const formatted: Message[] = rawMsgs.map((m: any) => ({
          id: String(m.id),
          role: m.role,
          content: m.content,
          citations: m.citations || [],
          metadata: m.metadata || {},
          answer_source: m.metadata?.answer_source,
          timestamp: m.created_at
            ? new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            : 'Today',
        }));

        if (formatted.length === 0) {
          // Provide default initial welcome state
          setMessages([
            {
              id: 'init-1',
              role: 'assistant',
              content: `Welcome to **MediaCompile Grounded Chat**.\n\nAsk questions about your saved documents, website links, and notes. Every answer is grounded directly in your saved evidence with verified citations.`,
              timestamp: 'Just now',
            },
          ]);
        } else {
          setMessages(formatted);
        }
      }
    } catch (err) {
      console.error('Failed to load session messages:', err);
    } finally {
      setIsLoadingMessages(false);
    }
  };

  // Create new session
  const handleCreateSession = async () => {
    try {
      const res = await fetch('/api/v1/chat/sessions/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: 'New Conversation' }),
      });
      if (res.ok) {
        const newSession = await res.json();
        setSessions((prev) => [newSession, ...prev]);
        setActiveSessionId(newSession.id);
        setMessages([
          {
            id: 'welcome-new',
            role: 'assistant',
            content: `Welcome to your new conversation.\n\nAsk anything about your saved research, documents, or notes. MediaCompile will ground its answers directly in your evidence.`,
            timestamp: 'Just now',
          },
        ]);
      }
    } catch {
      // ignore
    }
  };

  // Delete session
  const handleDeleteSession = async () => {
    if (!sessionToDelete || isDeletingSession) return;
    setIsDeletingSession(true);
    setSessionDeleteError(null);
    try {
      const res = await fetch(`/api/v1/chat/sessions/${sessionToDelete.id}/`, {
        method: 'DELETE',
      });
      if (res.ok) {
        const remaining = sessions.filter((s) => s.id !== sessionToDelete.id);
        setSessions(remaining);
        if (activeSessionId === sessionToDelete.id) {
          if (remaining.length > 0) {
            setActiveSessionId(remaining[0].id);
            loadMessages(remaining[0].id);
          } else {
            setActiveSessionId(null);
            setMessages([
              {
                id: 'welcome-clean',
                role: 'assistant',
                content: `### Start a new conversation\n\nAsk questions about your saved documents, website links, and notes. MediaCompile will synthesize verified answers with citations directly from your library.`,
                timestamp: 'Just now',
              },
            ]);
          }
        }
        // Broadcast so other pages (like Dashboard recent conversations) update immediately without refresh
        window.dispatchEvent(
          new CustomEvent('mediacompile:chat-deleted', {
            detail: { id: sessionToDelete.id },
          })
        );
        setSessionToDelete(null);
      } else {
        const errData = await res.json().catch(() => ({}));
        const rawMsg =
          errData.error?.message ||
          errData.detail ||
          errData.error ||
          'Failed to delete conversation.';
        setSessionDeleteError(rawMsg);
      }
    } catch (err: any) {
      setSessionDeleteError(err.message || 'Network error while attempting to delete conversation.');
    } finally {
      setIsDeletingSession(false);
    }
  };

  // Send message
  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputValue.trim() || isGenerating) return;

    const userText = inputValue.trim();
    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: userText,
      timestamp: timeStr,
    };

    setMessages((prev) => [...prev, tempUserMsg]);
    setInputValue('');
    setIsGenerating(true);

    try {
      let targetSessionId = activeSessionId;
      if (!targetSessionId) {
        const sessionTitle = userText.length > 32 ? `${userText.slice(0, 32)}...` : userText;
        const createRes = await fetch('/api/v1/chat/sessions/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: sessionTitle }),
        });
        if (createRes.ok) {
          const newSession = await createRes.json();
          targetSessionId = newSession.id;
          setActiveSessionId(newSession.id);
          setSessions((prev) => [newSession, ...prev]);
        }
      }

      const res = await fetch(`/api/v1/chat/sessions/${targetSessionId}/messages/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: userText }),
      });

      if (res.ok) {
        const data = await res.json();
        const assistantData = data.assistant_message;
        const assistantMsg: Message = {
          id: String(assistantData.id),
          role: 'assistant',
          content: assistantData.content,
          citations: assistantData.citations || [],
          metadata: assistantData.metadata || {},
          answer_source: assistantData.metadata?.answer_source,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        };
        setMessages((prev) => [...prev, assistantMsg]);

        if (data.session && data.session.title) {
          setSessions((prev) =>
            prev.map((s) => (s.id === targetSessionId ? { ...s, title: data.session.title } : s))
          );
        }
      } else {
        const errorData = await res.json().catch(() => ({}));
        const errContent = errorData.error || errorData.detail || 'Could not complete grounded response.';
        setMessages((prev) => [
          ...prev,
          {
            id: `err-${Date.now()}`,
            role: 'assistant',
            content: `I could not complete the response: ${errContent}`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: 'Network error communicating with grounded search.',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setIsGenerating(false);
    }
  };

  const activeSession = sessions.find((s) => s.id === activeSessionId) || {
    id: 'active',
    title: 'New Conversation',
  };

  const filteredSessions = sessions.filter((s) =>
    searchChats ? s.title.toLowerCase().includes(searchChats.toLowerCase()) : true
  );

  return (
    <ShellLayout>
      <div className="h-[calc(100vh-6rem)] -mt-2 -mx-2 flex gap-4 overflow-hidden select-none">
        {/* Panel 1: Conversations (Left, ~260px) */}
        <div className="hidden md:flex w-64 flex-col rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] p-3.5 space-y-3.5 shrink-0">
          {/* Header */}
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-2">
              <h2 className="font-semibold text-sm text-[var(--foreground)]">Conversations</h2>
              <span className="text-xs font-mono text-[var(--muted-foreground)]">
                {sessions.length}
              </span>
            </div>
            <button
              onClick={handleCreateSession}
              className="p-1 rounded-md text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--surface-subtle)] transition-colors cursor-pointer"
              title="New conversation"
              aria-label="New conversation"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>

          {/* Search chats */}
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--muted-foreground)]" />
            <input
              type="text"
              placeholder="Search chats"
              value={searchChats}
              onChange={(e) => setSearchChats(e.target.value)}
              className="w-full pl-8 pr-2.5 py-1.5 rounded-lg bg-[var(--surface-base)] border border-[var(--border)] text-xs text-[var(--foreground)] placeholder-[var(--muted-foreground)] focus:outline-hidden focus:border-[var(--foreground)]"
            />
          </div>

          {/* Sessions List */}
          <div className="flex-1 overflow-y-auto space-y-2 pr-1 text-xs">
            {filteredSessions.length > 0 ? (
              filteredSessions.map((sess) => {
                const isActive = sess.id === activeSessionId;
                return (
                  <div
                    key={sess.id}
                    onClick={() => {
                      setActiveSessionId(sess.id);
                      loadMessages(sess.id);
                    }}
                    className={`group p-2.5 rounded-xl cursor-pointer transition-all flex items-center justify-between gap-2 ${
                      isActive
                        ? 'bg-[var(--surface-subtle)] text-[var(--foreground)] font-medium'
                        : 'text-[var(--muted-foreground)] hover:bg-[var(--surface-base)] hover:text-[var(--foreground)]'
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="font-medium truncate">{sess.title}</p>
                      <p className="text-xs text-[var(--muted-foreground)] mt-0.5">
                        {sess.updated_at ? new Date(sess.updated_at).toLocaleDateString() : 'Active chat'}
                      </p>
                    </div>

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setSessionToDelete(sess);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1 text-[var(--muted-foreground)] hover:text-rose-500 transition-opacity"
                      title="Delete chat"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                );
              })
            ) : (
              <div
                onClick={handleCreateSession}
                className="p-2.5 rounded-xl bg-[var(--surface-subtle)] text-[var(--foreground)] cursor-pointer hover:bg-[var(--surface-hover)]"
              >
                <p className="font-medium truncate">Start a new conversation</p>
                <p className="text-xs text-[var(--muted-foreground)] mt-0.5">Click to begin</p>
              </div>
            )}
          </div>
        </div>

        {/* Panel 2: Central Chat Workspace (Full Available Width - No Right Sources Sidebar) */}
        <div className="flex-1 flex flex-col rounded-2xl bg-[var(--surface-elevated)] border border-[var(--border)] overflow-hidden min-w-0">
          {/* Top Chat Header */}
          <div className="h-14 border-b border-[var(--border)] px-3 sm:px-5 flex items-center justify-between shrink-0 bg-[var(--surface-elevated)] gap-2">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <button
                onClick={() => setIsMobileChatsOpen(true)}
                className="md:hidden p-1.5 rounded-lg border border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)] transition-colors shrink-0 cursor-pointer"
                aria-label="Open conversations"
                title="Conversations"
              >
                <MessageSquare className="h-4 w-4" />
              </button>
              <h1 className="text-sm sm:text-lg font-semibold text-[var(--foreground)] truncate">
                {activeSession.title || 'Conversation'}
              </h1>
            </div>

            <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
              {/* Mobile + Desktop New Chat Button */}
              <button
                onClick={handleCreateSession}
                className="flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg bg-[var(--primary)] hover:opacity-90 text-[var(--primary-foreground)] text-xs font-medium transition-opacity shadow-xs cursor-pointer"
                title="Start a new chat"
              >
                <Plus className="h-3.5 w-3.5" />
                <span className="hidden xs:inline">New Chat</span>
              </button>

              {/* Delete Active Chat Button */}
              {activeSessionId && (
                <button
                  onClick={() => {
                    const current = sessions.find((s) => s.id === activeSessionId);
                    if (current) setSessionToDelete(current);
                  }}
                  className="p-1.5 rounded-lg border border-[var(--border)] text-[var(--muted-foreground)] hover:text-rose-500 hover:bg-rose-500/10 transition-colors shrink-0 cursor-pointer"
                  title="Delete current conversation"
                  aria-label="Delete conversation"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )}

              <button
                onClick={() => {
                  const chatDump = messages.map((m) => `${m.role.toUpperCase()}: ${m.content}`).join('\n\n');
                  const blob = new Blob([chatDump], { type: 'text/plain' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `${activeSession.title || 'chat'}.txt`;
                  a.click();
                }}
                className="hidden sm:flex px-2.5 py-1.5 rounded-md bg-[var(--surface-base)] hover:bg-[var(--surface-subtle)] border border-[var(--border)] text-xs text-[var(--foreground)] items-center gap-1.5 transition-colors cursor-pointer"
                title="Export conversation"
              >
                <Download className="h-3.5 w-3.5" />
                <span>Export</span>
              </button>
            </div>
          </div>

          {/* Messages Stream */}
          <div className="flex-1 overflow-y-auto px-3 sm:px-6 py-4 sm:py-6 space-y-4 sm:space-y-6 min-w-0">
            {isLoadingMessages ? (
              <div className="py-12 text-center text-xs text-[var(--muted-foreground)] flex items-center justify-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading conversation...
              </div>
            ) : (
              messages.map((msg) => {
                const isUser = msg.role === 'user';

                if (isUser) {
                  // User Message: Aligned on the RIGHT
                  return (
                    <div key={msg.id} className="flex justify-end w-full min-w-0">
                      <div className="max-w-2xl space-y-1.5 flex flex-col items-end min-w-0">
                        <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
                          <span className="font-medium text-[var(--foreground)]">{displayName}</span>
                          <span>&middot;</span>
                          <span className="text-xs">{msg.timestamp}</span>
                          <div className="h-6 w-6 rounded-full bg-[var(--accent-sand)] text-[#141518] flex items-center justify-center text-xs font-bold shrink-0">
                            {initial}
                          </div>
                        </div>

                        <div className="p-3.5 sm:p-4 rounded-2xl rounded-tr-xs bg-[var(--surface-subtle)] text-xs sm:text-sm leading-relaxed text-[var(--foreground)] break-words [overflow-wrap:anywhere] max-w-full">
                          <p className="whitespace-pre-wrap break-words">{msg.content}</p>
                        </div>
                      </div>
                    </div>
                  );
                }

                // Assistant Message: Aligned on the LEFT
                return (
                  <div key={msg.id} className="flex justify-start w-full min-w-0">
                    <div className="max-w-3xl space-y-2 flex flex-col items-start w-full min-w-0">
                      {/* Sender Header */}
                      <div className="flex items-center gap-2 sm:gap-2.5 flex-wrap">
                        <div className="h-6 w-6 rounded-md bg-[var(--surface-subtle)] border border-[var(--border)] flex items-center justify-center gap-[1.5px] px-1 shrink-0">
                          <span className="w-[1.5px] h-2 bg-[var(--foreground)] rounded-full" />
                          <span className="w-[1.5px] h-3 bg-[var(--foreground)] rounded-full" />
                          <span className="w-[1.5px] h-1.5 bg-[var(--foreground)] rounded-full" />
                        </div>
                        <span className="text-xs font-semibold text-[var(--foreground)]">MediaCompile</span>
                        <span className="text-[11px] sm:text-xs text-[var(--muted-foreground)]">&middot; {msg.timestamp}</span>
                        {renderSourceIndicator(msg.answer_source, msg.metadata, msg.citations)}
                      </div>

                      {/* Content */}
                      <div className="pl-1 sm:pl-8 text-xs sm:text-sm leading-relaxed text-[var(--foreground)] w-full min-w-0 break-words [overflow-wrap:anywhere]">
                        <FormattedMarkdown content={msg.content} />

                        {/* Inline Citations Associated with Message (Max 3 visible) */}
                        {(() => {
                          const visibleCitations = getVisibleCitations(msg.citations);
                          if (visibleCitations.length === 0) return null;

                          return (
                            <div className="mt-3.5 sm:mt-4 pt-3 border-t border-[var(--border)] max-w-full min-w-0">
                              <p className="text-[11px] sm:text-xs uppercase font-bold tracking-wider text-[var(--muted-foreground)] mb-2">
                                Sources & Citations
                              </p>
                              <div className="flex flex-wrap gap-1.5 sm:gap-2 max-w-full min-w-0">
                                {visibleCitations.map((c, i) => (
                                  <div
                                    key={i}
                                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[var(--surface-subtle)] hover:bg-[var(--surface-hover)] border border-[var(--border)] text-xs text-[var(--foreground)] transition-colors max-w-full shadow-2xs"
                                  >
                                    <button
                                      onClick={() => setActiveCitation(c)}
                                      className="flex items-center gap-1.5 cursor-pointer hover:underline min-w-0 text-left"
                                      title="View citation excerpt"
                                    >
                                      <span className="font-mono text-[var(--muted-foreground)] font-semibold shrink-0">[{i + 1}]</span>
                                      {c.is_web ? (
                                        <span className="inline-flex items-center gap-1 text-[10px] uppercase font-bold text-sky-600 dark:text-sky-400 bg-sky-500/10 px-1 py-0.5 rounded shrink-0">
                                          <Globe className="h-2.5 w-2.5" />
                                          Web
                                        </span>
                                      ) : null}
                                      <span className="font-medium truncate max-w-[140px] sm:max-w-xs">{c.item_title}</span>
                                      {c.page_number && (
                                        <span className="text-[var(--muted-foreground)] font-mono text-[11px] sm:text-xs shrink-0">
                                          &middot; p. {c.page_number}
                                        </span>
                                      )}
                                      {c.timestamp && (
                                        <span className="text-[var(--muted-foreground)] font-mono text-[11px] sm:text-xs shrink-0">
                                          &middot; {c.timestamp}
                                        </span>
                                      )}
                                    </button>

                                    {/* Direct clickable link for Web/YouTube/Platform Links */}
                                    {c.source_url && (
                                      <a
                                        href={c.timestamp_url || c.source_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-[var(--muted-foreground)] hover:text-[var(--foreground)] p-0.5 rounded transition-colors ml-0.5 shrink-0"
                                        title={`Open original source: ${c.source_url}`}
                                      >
                                        <ExternalLink className="h-3 w-3" />
                                      </a>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          );
                        })()}

                        {/* Message Actions */}
                        <div className="flex items-center gap-3 mt-3 text-[11px] text-[var(--muted-foreground)]">
                          <button
                            onClick={() => {
                              navigator.clipboard.writeText(msg.content);
                              setCopiedId(msg.id);
                              setTimeout(() => setCopiedId(null), 1500);
                            }}
                            className="hover:text-[var(--foreground)] flex items-center gap-1 cursor-pointer transition-colors"
                          >
                            {copiedId === msg.id ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
                            <span>{copiedId === msg.id ? 'Copied' : 'Copy'}</span>
                          </button>

                          <button
                            onClick={() => {
                              setSavedId(msg.id);
                              setTimeout(() => setSavedId(null), 1500);
                            }}
                            className="hover:text-[var(--foreground)] flex items-center gap-1 cursor-pointer transition-colors"
                          >
                            <Bookmark className="h-3 w-3" />
                            <span>{savedId === msg.id ? 'Saved' : 'Save'}</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })
            )}

            {isGenerating && (
              <div className="flex justify-start w-full min-w-0">
                <div className="max-w-3xl pl-1 sm:pl-8 flex items-center gap-2 text-xs text-[var(--muted-foreground)] animate-pulse">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--foreground)] shrink-0" />
                  <span>MediaCompile is retrieving evidence and synthesizing answer...</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Bottom Floating Composer */}
          <div className="p-3 sm:p-4 bg-[var(--surface-elevated)] border-t border-[var(--border)] shrink-0">
            <form
              onSubmit={handleSend}
              className="rounded-2xl bg-[var(--surface-base)] p-2.5 sm:p-3 focus-within:ring-1 focus-within:ring-[var(--foreground)] transition-all"
            >
              <textarea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    handleSend();
                  }
                }}
                placeholder="Ask anything grounded across your saved documents, links, and notes..."
                rows={2}
                className="w-full bg-transparent text-xs sm:text-sm text-[var(--foreground)] placeholder-[var(--muted-foreground)] resize-none focus:outline-hidden"
              />

              <div className="flex items-center justify-between pt-2 border-t border-[var(--border)] gap-2">
                <div className="flex items-center gap-1.5 sm:gap-2 text-[11px] sm:text-xs text-[var(--muted-foreground)] min-w-0">
                  <Sparkles className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                  <span className="truncate">Grounded in your library</span>
                </div>

                <div className="flex items-center gap-2 sm:gap-3 shrink-0">
                  <span className="text-xs text-[var(--muted-foreground)] font-mono hidden md:inline">
                    Ctrl + Enter to send
                  </span>

                  <button
                    type="submit"
                    disabled={isGenerating || !inputValue.trim()}
                    className="h-8 w-8 sm:h-7 sm:w-7 rounded-full bg-[var(--primary)] hover:opacity-90 text-[var(--primary-foreground)] flex items-center justify-center transition-opacity disabled:opacity-30 cursor-pointer shadow-xs shrink-0"
                    aria-label="Send message"
                  >
                    <Send className="h-3.5 w-3.5 stroke-[1.8]" />
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>

        {/* Citation Detail Modal */}
        {activeCitation && (
          <Modal
            isOpen={true}
            onClose={() => setActiveCitation(null)}
            title={`Citation: ${activeCitation.item_title}`}
          >
            <div className="space-y-4 text-xs text-[var(--foreground)]">
              <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--border)] space-y-1.5 text-[11px]">
                <p className="text-[var(--muted-foreground)]">
                  Source: <span className="text-[var(--foreground)] font-medium">{activeCitation.item_title}</span>
                </p>
                {activeCitation.page_number && (
                  <p className="text-[var(--muted-foreground)]">
                    Page: <span className="text-[var(--foreground)] font-mono">{activeCitation.page_number}</span>
                  </p>
                )}
                {activeCitation.timestamp && (
                  <p className="text-[var(--muted-foreground)]">
                    Timestamp: <span className="text-[var(--foreground)] font-mono">{activeCitation.timestamp}</span>
                  </p>
                )}
                {activeCitation.source_url && (
                  <p className="text-[var(--muted-foreground)] flex items-center gap-1 pt-1">
                    URL:
                    <a
                      href={activeCitation.timestamp_url || activeCitation.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-500 hover:underline inline-flex items-center gap-1"
                    >
                      <span className="truncate max-w-sm">{activeCitation.source_url}</span>
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </p>
                )}
              </div>

              <div>
                <h3 className="font-semibold text-[var(--foreground)] mb-1.5">Direct Source Excerpt</h3>
                <blockquote className="p-3.5 rounded-xl bg-[var(--surface-base)] border border-[var(--border)] text-[var(--foreground)] leading-relaxed italic text-xs">
                  &ldquo;{activeCitation.excerpt}&rdquo;
                </blockquote>
              </div>

              <div className="flex justify-between items-center pt-2">
                {activeCitation.source_url ? (
                  <a
                    href={activeCitation.timestamp_url || activeCitation.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-3 py-1.5 rounded-lg bg-[var(--primary)] hover:opacity-90 text-[var(--primary-foreground)] text-xs font-medium inline-flex items-center gap-1.5 transition-opacity"
                  >
                    <span>Open original link</span>
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                ) : <span />}

                <button
                  onClick={() => setActiveCitation(null)}
                  className="px-3.5 py-1.5 rounded-lg bg-[var(--surface-subtle)] hover:bg-[var(--border)] text-xs text-[var(--foreground)] cursor-pointer"
                >
                  Close
                </button>
              </div>
            </div>
          </Modal>
        )}

        {/* Mobile Conversations Drawer Modal */}
        {isMobileChatsOpen && (
          <Modal
            isOpen={isMobileChatsOpen}
            onClose={() => setIsMobileChatsOpen(false)}
            title="Conversations"
            description={`${sessions.length} conversations in your library`}
          >
            <div className="space-y-3">
              <button
                onClick={() => {
                  handleCreateSession();
                  setIsMobileChatsOpen(false);
                }}
                className="w-full py-2 px-3 rounded-xl bg-[var(--primary)] text-[var(--primary-foreground)] text-xs font-medium flex items-center justify-center gap-2 shadow-xs cursor-pointer hover:opacity-90 transition-opacity"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>New conversation</span>
              </button>

              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--muted-foreground)]" />
                <input
                  type="text"
                  placeholder="Search chats"
                  value={searchChats}
                  onChange={(e) => setSearchChats(e.target.value)}
                  className="w-full pl-8 pr-2.5 py-1.5 rounded-lg bg-[var(--surface-base)] border border-[var(--border)] text-xs text-[var(--foreground)] placeholder-[var(--muted-foreground)] focus:outline-hidden"
                />
              </div>

              <div className="max-h-[50vh] overflow-y-auto space-y-1.5 pr-1 text-xs divide-y divide-[var(--border)]">
                {filteredSessions.length > 0 ? (
                  filteredSessions.map((sess) => (
                    <div
                      key={sess.id}
                      onClick={() => {
                        setActiveSessionId(sess.id);
                        loadMessages(sess.id);
                        setIsMobileChatsOpen(false);
                      }}
                      className={`p-2.5 rounded-xl cursor-pointer flex items-center justify-between gap-2 ${
                        sess.id === activeSessionId
                          ? 'bg-[var(--surface-subtle)] font-medium text-[var(--foreground)]'
                          : 'text-[var(--foreground-muted)] hover:bg-[var(--surface-hover)]'
                      }`}
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate">{sess.title}</p>
                        <p className="text-[11px] text-[var(--muted-foreground)] mt-0.5">
                          {sess.updated_at ? new Date(sess.updated_at).toLocaleDateString() : 'Active chat'}
                        </p>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSessionToDelete(sess);
                          setIsMobileChatsOpen(false);
                        }}
                        className="p-2 text-[var(--muted-foreground)] hover:text-rose-500 hover:bg-rose-500/10 rounded-lg cursor-pointer transition-colors shrink-0"
                        title="Delete chat"
                        aria-label={`Delete chat ${sess.title}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))
                ) : (
                  <div className="py-6 text-center text-xs text-[var(--muted-foreground)]">
                    No conversations found.
                  </div>
                )}
              </div>
            </div>
          </Modal>
        )}

        {/* Standardized Delete Session Confirmation Modal */}
        <DeleteConfirmationModal
          isOpen={!!sessionToDelete}
          onClose={() => {
            if (!isDeletingSession) {
              setSessionToDelete(null);
              setSessionDeleteError(null);
            }
          }}
          onConfirm={handleDeleteSession}
          title="Delete this chat?"
          itemName={sessionToDelete?.title}
          itemType="chat"
          itemMeta={`${sessionToDelete?.message_count ?? 0} messages · Created ${sessionToDelete?.created_at ? new Date(sessionToDelete.created_at).toLocaleDateString() : 'Recently'}`}
          consequenceText="This will permanently delete this conversation and its message history. All saved sources and library items remain safe."
          isDeleting={isDeletingSession}
          errorMessage={sessionDeleteError}
        />
      </div>
    </ShellLayout>
  );
}
