"use client";

import Link from "next/link";
import {
  FormEvent,
  KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { Markdown } from "@/components/Markdown";
import {
  api,
  getStoredUser,
  hasToken,
  mediaUrl,
  type AiChat,
  type AiChatListItem,
  type AiMessage,
  type AiProject,
  type HistoryItem,
  type ImportConversation,
} from "@/lib/api";

type Tab = "projects" | "history" | "chat" | "personal";

const TABS: { id: Tab; label: string }[] = [
  { id: "chat", label: "Chat" },
  { id: "personal", label: "Personal" },
  { id: "projects", label: "Projects" },
  { id: "history", label: "History" },
];

export default function WorkspacePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialTab = (searchParams.get("tab") as Tab) || "chat";
  const [tab, setTab] = useState<Tab>(
    TABS.some((t) => t.id === initialTab) ? initialTab : "chat"
  );

  const [error, setError] = useState("");
  const [projects, setProjects] = useState<AiProject[]>([]);
  const [projectName, setProjectName] = useState("");
  const [projectDesc, setProjectDesc] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState("");

  const [historyQ, setHistoryQ] = useState("");
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [importView, setImportView] = useState<ImportConversation | null>(null);

  const [workChats, setWorkChats] = useState<AiChatListItem[]>([]);
  const [personalChats, setPersonalChats] = useState<AiChatListItem[]>([]);
  const [activeChat, setActiveChat] = useState<AiChat | null>(null);
  const [draft, setDraft] = useState("");
  const [makeFeed, setMakeFeed] = useState(false);
  const [imageMode, setImageMode] = useState(false);
  const [imageStyle, setImageStyle] = useState<"poster" | "general">("poster");
  const [sending, setSending] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [creating, setCreating] = useState(false);
  const [draftPackId, setDraftPackId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [continuingId, setContinuingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [busyMsgId, setBusyMsgId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const loadProjects = useCallback(async () => {
    setProjects(await api.workspaceProjects());
  }, []);

  const loadHistory = useCallback(async (q = "") => {
    setHistory(await api.workspaceHistory(q));
  }, []);

  const loadChats = useCallback(async () => {
    const [work, personal] = await Promise.all([
      api.workspaceChats({ mode: "work" }),
      api.workspaceChats({ mode: "personal" }),
    ]);
    setWorkChats(work);
    setPersonalChats(personal);
  }, []);

  useEffect(() => {
    if (!hasToken()) {
      router.replace("/login");
      return;
    }
    const u = getStoredUser();
    if (u?.role !== "admin") {
      router.replace("/feed");
      return;
    }
    Promise.all([loadProjects(), loadHistory(), loadChats()]).catch((err) =>
      setError(err instanceof Error ? err.message : "Failed to load workspace")
    );
  }, [router, loadProjects, loadHistory, loadChats]);

  const chatList = useMemo(
    () => (tab === "personal" ? personalChats : workChats),
    [tab, personalChats, workChats]
  );

  const visibleMessages = useMemo(
    () =>
      (activeChat?.messages ?? []).filter(
        (m) => m.role === "user" || m.role === "assistant"
      ),
    [activeChat?.messages]
  );

  const isChatTab = tab === "chat" || tab === "personal";

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [visibleMessages.length, sending, streaming, streamText, tab, activeChat?.id]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "0px";
    ta.style.height = `${Math.min(ta.scrollHeight, 180)}px`;
  }, [draft]);

  function applyChat(chat: AiChat | null | undefined) {
    if (chat) setActiveChat(chat);
  }

  function switchTab(next: Tab) {
    setTab(next);
    setError("");
    setImportView(null);
    setDraftPackId(null);
    setSidebarOpen(false);
    setEditingId(null);
    if (next === "chat" || next === "personal") {
      if (
        activeChat &&
        activeChat.mode !== (next === "personal" ? "personal" : "work")
      ) {
        setActiveChat(null);
      }
    }
    router.replace(`/admin/workspace?tab=${next}`, { scroll: false });
  }

  async function onCreateProject(e: FormEvent) {
    e.preventDefault();
    if (!projectName.trim()) return;
    setCreating(true);
    setError("");
    try {
      const p = await api.createWorkspaceProject({
        name: projectName.trim(),
        description: projectDesc.trim(),
      });
      setProjectName("");
      setProjectDesc("");
      setSelectedProjectId(p.id);
      await loadProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create project");
    } finally {
      setCreating(false);
    }
  }

  async function onSearchHistory(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await loadHistory(historyQ);
    } catch (err) {
      setError(err instanceof Error ? err.message : "History search failed");
    }
  }

  async function openHistoryItem(item: HistoryItem) {
    setError("");
    setDraftPackId(null);
    try {
      if (item.source === "import") {
        setImportView(await api.workspaceImport(item.id));
        setActiveChat(null);
        return;
      }
      const chat = await api.getWorkspaceChat(item.id);
      setImportView(null);
      setActiveChat(chat);
      setTab(chat.mode === "personal" ? "personal" : "chat");
      setSidebarOpen(false);
      router.replace(
        `/admin/workspace?tab=${chat.mode === "personal" ? "personal" : "chat"}`,
        { scroll: false }
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open item");
    }
  }

  async function continueFromImport(
    importId: string,
    mode: "work" | "personal" = "work"
  ) {
    setContinuingId(importId);
    setError("");
    setDraftPackId(null);
    try {
      const chat = await api.continueImport(importId, {
        mode,
        project_id:
          mode === "work" && selectedProjectId ? selectedProjectId : null,
      });
      setImportView(null);
      setActiveChat(chat);
      setTab(mode === "personal" ? "personal" : "chat");
      setSidebarOpen(false);
      await loadChats();
      await loadHistory();
      router.replace(
        `/admin/workspace?tab=${mode === "personal" ? "personal" : "chat"}`,
        { scroll: false }
      );
      textareaRef.current?.focus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not continue chat");
    } finally {
      setContinuingId(null);
    }
  }

  async function openChat(id: string) {
    setError("");
    setImportView(null);
    setDraftPackId(null);
    setSidebarOpen(false);
    setEditingId(null);
    try {
      setActiveChat(await api.getWorkspaceChat(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open chat");
    }
  }

  async function startNewChat() {
    setCreating(true);
    setError("");
    setDraftPackId(null);
    try {
      const mode = tab === "personal" ? "personal" : "work";
      const chat = await api.createWorkspaceChat({
        mode,
        project_id:
          mode === "work" && selectedProjectId ? selectedProjectId : null,
        title: mode === "personal" ? "Personal chat" : "New chat",
      });
      setActiveChat(chat);
      setDraft("");
      setMakeFeed(false);
      setImageMode(false);
      setSidebarOpen(false);
      await loadChats();
      await loadHistory();
      textareaRef.current?.focus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start chat");
    } finally {
      setCreating(false);
    }
  }

  async function renameActiveChat() {
    if (!activeChat) return;
    const next = window.prompt("Rename chat", activeChat.title);
    if (next == null) return;
    const title = next.trim();
    if (!title) return;
    try {
      const chat = await api.renameWorkspaceChat(activeChat.id, title);
      setActiveChat(chat);
      await loadChats();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rename failed");
    }
  }

  async function deleteActiveChat() {
    if (!activeChat) return;
    if (!window.confirm(`Delete “${activeChat.title}”? This cannot be undone.`)) {
      return;
    }
    try {
      await api.deleteWorkspaceChat(activeChat.id);
      setActiveChat(null);
      await loadChats();
      await loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function copyMessage(m: AiMessage) {
    try {
      await navigator.clipboard.writeText(m.content || "");
      setCopiedId(m.id);
      window.setTimeout(() => setCopiedId(null), 1200);
    } catch {
      setError("Could not copy to clipboard");
    }
  }

  async function deleteMessage(m: AiMessage) {
    if (!activeChat) return;
    if (!window.confirm("Delete this message?")) return;
    setBusyMsgId(m.id);
    try {
      await api.deleteWorkspaceMessage(activeChat.id, m.id);
      setActiveChat(await api.getWorkspaceChat(activeChat.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusyMsgId(null);
    }
  }

  function startEdit(m: AiMessage) {
    if (m.role !== "user") return;
    setEditingId(m.id);
    setEditDraft(m.content);
  }

  async function saveEdit() {
    if (!activeChat || !editingId || !editDraft.trim()) return;
    setBusyMsgId(editingId);
    setError("");
    try {
      const res = await api.editWorkspaceMessage(activeChat.id, editingId, {
        content: editDraft.trim(),
        regenerate: true,
      });
      applyChat(res.chat);
      if (!res.chat) {
        setActiveChat(await api.getWorkspaceChat(activeChat.id));
      }
      setEditingId(null);
      setEditDraft("");
      await loadChats();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Edit failed");
    } finally {
      setBusyMsgId(null);
    }
  }

  async function onSend(e?: FormEvent) {
    e?.preventDefault();
    if (!activeChat || !draft.trim() || sending) return;
    setSending(true);
    setError("");
    setDraftPackId(null);
    setStreamText("");
    const content = draft.trim();
    setDraft("");
    try {
      if (imageMode) {
        const res = await api.generateWorkspaceImage(activeChat.id, {
          prompt: content,
          make_feed: makeFeed,
          style: imageStyle,
        });
        applyChat(res.chat);
        if (!res.chat) {
          setActiveChat(await api.getWorkspaceChat(activeChat.id));
        }
        if (res.draft_pack_id) {
          setDraftPackId(res.draft_pack_id);
          setMakeFeed(false);
        }
      } else {
        const chatId = activeChat.id;
        setStreaming(true);
        let finished = false;
        let streamError = "";
        let localStream = "";

        const mergeAssistant = (message: AiMessage, chat?: AiChat | null) => {
          if (chat?.messages?.length) {
            setActiveChat(chat);
            return;
          }
          setActiveChat((prev) => {
            if (!prev) return prev;
            const withoutDup = prev.messages.filter((m) => m.id !== message.id);
            // Drop any optimistic streaming placeholder
            const withoutTemp = withoutDup.filter(
              (m) => !m.id.startsWith("stream-")
            );
            return {
              ...prev,
              messages: [...withoutTemp, message],
            };
          });
        };

        await api.streamWorkspaceMessage(
          chatId,
          { content, make_feed: makeFeed },
          {
            onUser: (message) => {
              setActiveChat((prev) => {
                if (!prev) return prev;
                const title =
                  prev.title === "New chat" || prev.title === "Personal chat"
                    ? content.slice(0, 80)
                    : prev.title;
                const withoutDup = prev.messages.filter((m) => m.id !== message.id);
                return {
                  ...prev,
                  title,
                  messages: [...withoutDup, message],
                };
              });
            },
            onDelta: (text) => {
              localStream += text;
              setStreamText(localStream);
            },
            onDone: (res) => {
              finished = true;
              // Keep stream text visible until chat state includes the reply.
              mergeAssistant(res.message, res.chat);
              if (res.draft_pack_id) {
                setDraftPackId(res.draft_pack_id);
                setMakeFeed(false);
              }
            },
            onFeed: (draftPackId) => {
              setDraftPackId(draftPackId);
              setMakeFeed(false);
            },
            onError: (detail) => {
              streamError = detail;
              setError(detail);
            },
          }
        );

        // Always reconcile from the server so a dropped "done" event cannot
        // wipe a reply that was already shown while streaming.
        let reconciled: AiChat | null = null;
        for (let attempt = 0; attempt < 6; attempt++) {
          try {
            reconciled = await api.getWorkspaceChat(chatId);
            const visible = reconciled.messages.filter(
              (m) => m.role === "user" || m.role === "assistant"
            );
            const last = visible[visible.length - 1];
            if (last?.role === "assistant" && last.content.trim()) break;
            if (finished && !localStream) break;
          } catch {
            /* retry */
          }
          await new Promise((r) => setTimeout(r, 250));
        }

        if (reconciled) {
          setActiveChat(reconciled);
        } else if (localStream.trim()) {
          // Last resort: keep what the user already saw.
          setActiveChat((prev) => {
            if (!prev) return prev;
            const already = prev.messages.some(
              (m) => m.role === "assistant" && m.content === localStream
            );
            if (already) return prev;
            return {
              ...prev,
              messages: [
                ...prev.messages.filter((m) => !m.id.startsWith("stream-")),
                {
                  id: `stream-${Date.now()}`,
                  role: "assistant",
                  content: localStream,
                  created_at: new Date().toISOString(),
                },
              ],
            };
          });
        } else if (!finished && streamError) {
          throw new Error(streamError);
        }

        setStreaming(false);
        setStreamText("");
      }
      await loadChats();
      // Don't await history here — it is unrelated to the open thread and
      // used to make the reply feel like it "left" for the History tab.
    } catch (err) {
      setDraft(content);
      setError(err instanceof Error ? err.message : "Send failed");
      setStreaming(false);
      setStreamText("");
      if (activeChat) {
        try {
          setActiveChat(await api.getWorkspaceChat(activeChat.id));
        } catch {
          /* ignore */
        }
      }
    } finally {
      setSending(false);
      textareaRef.current?.focus();
    }
  }

  function onComposerKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void onSend();
    }
  }

  return (
    <AppShell variant="immersive">
      <div className="chat-shell relative">
        {sidebarOpen ? (
          <button
            type="button"
            className="absolute inset-0 z-20 bg-fjord/20 md:hidden"
            aria-label="Close sidebar"
            onClick={() => setSidebarOpen(false)}
          />
        ) : null}

        <aside className={`chat-sidebar ${sidebarOpen ? "open" : ""}`}>
          <div className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-3 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-mist">
              Workspace
            </p>
            <button
              type="button"
              className="rounded-md px-2 py-1 text-xs text-mist md:hidden"
              onClick={() => setSidebarOpen(false)}
            >
              Close
            </button>
          </div>

          <div className="grid grid-cols-2 gap-1 p-2">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => switchTab(t.id)}
                className={`rounded-md px-2 py-2 text-xs font-medium transition-colors ${
                  tab === t.id
                    ? "bg-white text-fjord shadow-sm"
                    : "text-ink/45 hover:bg-white/60 hover:text-fjord"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {isChatTab ? (
            <div className="flex min-h-0 flex-1 flex-col px-2 pb-3">
              <button
                type="button"
                onClick={startNewChat}
                disabled={creating}
                className="mb-2 flex min-h-10 items-center justify-center gap-2 rounded-lg border border-[var(--line)] bg-white text-sm font-medium text-fjord transition-colors hover:bg-ice/50 disabled:opacity-50"
              >
                <span aria-hidden className="text-lg leading-none">
                  +
                </span>
                {creating ? "Starting…" : "New chat"}
              </button>

              {tab === "chat" && projects.length > 0 ? (
                <label className="mb-2 block px-1">
                  <span className="mb-1 block text-[10px] font-medium uppercase tracking-[0.12em] text-mist">
                    Project
                  </span>
                  <select
                    value={selectedProjectId}
                    onChange={(e) => setSelectedProjectId(e.target.value)}
                    className="min-h-9 w-full rounded-md border border-[var(--line)] bg-white px-2 text-sm outline-none focus:border-glacier"
                  >
                    <option value="">General</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}

              <p className="mb-2 px-1 text-[11px] leading-relaxed text-ink/40">
                Chat · images · feed drafts · edit/copy/delete
              </p>

              <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto">
                {chatList.length === 0 ? (
                  <li className="px-2 py-4 text-xs text-ink/35">No chats yet</li>
                ) : (
                  chatList.map((c) => (
                    <li key={c.id} className="group flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => openChat(c.id)}
                        className={`min-w-0 flex-1 truncate rounded-lg px-2.5 py-2.5 text-left text-sm transition-colors ${
                          activeChat?.id === c.id
                            ? "bg-white font-medium text-fjord shadow-sm"
                            : "text-ink/55 hover:bg-white/70 hover:text-fjord"
                        }`}
                      >
                        {c.title || "Untitled"}
                      </button>
                    </li>
                  ))
                )}
              </ul>
            </div>
          ) : (
            <div className="px-3 py-2 text-xs leading-relaxed text-ink/45">
              {tab === "projects"
                ? "Organize workstreams for curriculum and packs."
                : "Search imported history — Continue to pick up a thread."}
            </div>
          )}
        </aside>

        <section className="chat-thread relative">
          <div className="flex items-center gap-2 border-b border-[var(--line)] px-3 py-2.5 sm:px-5">
            <button
              type="button"
              className="rounded-md border border-[var(--line)] bg-white px-2.5 py-1.5 text-xs font-medium text-fjord md:hidden"
              onClick={() => setSidebarOpen(true)}
            >
              Menu
            </button>
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-sm font-medium text-fjord sm:text-base">
                {isChatTab
                  ? activeChat?.title ||
                    (tab === "personal" ? "Personal" : "Chat")
                  : tab === "projects"
                    ? "Projects"
                    : "History"}
              </h1>
              <p className="truncate text-[11px] text-mist">
                Educational workspace · grounded in brief and history
              </p>
            </div>
            {isChatTab && activeChat ? (
              <div className="flex shrink-0 gap-1">
                <button
                  type="button"
                  onClick={renameActiveChat}
                  className="rounded-md border border-[var(--line)] bg-white px-2 py-1.5 text-[11px] font-medium text-fjord"
                >
                  Rename
                </button>
                <button
                  type="button"
                  onClick={deleteActiveChat}
                  className="rounded-md border border-red-200 bg-white px-2 py-1.5 text-[11px] font-medium text-red-700"
                >
                  Delete
                </button>
              </div>
            ) : null}
          </div>

          {error ? (
            <p className="mx-3 mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 sm:mx-5">
              {error}
            </p>
          ) : null}

          {draftPackId ? (
            <p className="mx-3 mt-3 rounded-lg border border-fjord/10 bg-ice/70 px-3 py-2 text-sm text-fjord sm:mx-5">
              Draft pack ready —{" "}
              <Link
                href={`/packs/${draftPackId}`}
                className="font-medium underline underline-offset-4"
              >
                review before publish
              </Link>
            </p>
          ) : null}

          {tab === "projects" ? (
            <div className="chat-scroll px-4 py-6 sm:px-8">
              <div className="mx-auto max-w-2xl space-y-6">
                <form onSubmit={onCreateProject} className="panel space-y-3 p-5">
                  <h2 className="font-display text-xl text-fjord">New project</h2>
                  <input
                    value={projectName}
                    onChange={(e) => setProjectName(e.target.value)}
                    placeholder="e.g. MACCE curriculum"
                    className="input-field rounded-md"
                    required
                  />
                  <textarea
                    value={projectDesc}
                    onChange={(e) => setProjectDesc(e.target.value)}
                    placeholder="Optional notes"
                    rows={2}
                    className="input-field rounded-md"
                  />
                  <button type="submit" disabled={creating} className="btn-primary rounded-md">
                    {creating ? "Saving…" : "Add project"}
                  </button>
                </form>
                <ul className="divide-y divide-[var(--line)]">
                  {projects.length === 0 ? (
                    <li className="py-8 text-center text-sm text-ink/40">
                      No projects yet.
                    </li>
                  ) : (
                    projects.map((p) => (
                      <li
                        key={p.id}
                        className="flex items-start justify-between gap-3 py-4"
                      >
                        <div>
                          <p className="font-medium text-fjord">{p.name}</p>
                          {p.description ? (
                            <p className="mt-1 text-sm text-ink/55">
                              {p.description}
                            </p>
                          ) : null}
                        </div>
                        <button
                          type="button"
                          className="shrink-0 text-xs font-medium text-glacier underline underline-offset-4"
                          onClick={() => {
                            setSelectedProjectId(p.id);
                            switchTab("chat");
                          }}
                        >
                          Open chat
                        </button>
                      </li>
                    ))
                  )}
                </ul>
              </div>
            </div>
          ) : null}

          {tab === "history" ? (
            <div className="chat-scroll px-4 py-6 sm:px-8">
              <div className="mx-auto max-w-2xl space-y-4">
                <form onSubmit={onSearchHistory} className="flex gap-2">
                  <input
                    value={historyQ}
                    onChange={(e) => setHistoryQ(e.target.value)}
                    placeholder="Search imports and chats"
                    className="input-field rounded-md"
                  />
                  <button type="submit" className="btn-primary shrink-0 rounded-md px-4">
                    Search
                  </button>
                </form>

                {importView ? (
                  <div className="panel space-y-3 p-5">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-mist">
                          Imported
                        </p>
                        <h2 className="font-display text-xl text-fjord">
                          {importView.title || "Conversation"}
                        </h2>
                      </div>
                      <button
                        type="button"
                        className="text-xs font-medium text-glacier"
                        onClick={() => setImportView(null)}
                      >
                        Close
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        disabled={continuingId === importView.id}
                        onClick={() => continueFromImport(importView.id, "work")}
                        className="btn-primary rounded-md px-4"
                      >
                        {continuingId === importView.id
                          ? "Starting…"
                          : "Continue in Chat"}
                      </button>
                      <button
                        type="button"
                        disabled={continuingId === importView.id}
                        onClick={() =>
                          continueFromImport(importView.id, "personal")
                        }
                        className="btn-secondary rounded-md px-4"
                      >
                        Continue in Personal
                      </button>
                    </div>
                    <pre className="max-h-[50vh] overflow-auto whitespace-pre-wrap text-sm leading-relaxed text-ink/75">
                      {importView.user_text}
                    </pre>
                  </div>
                ) : null}

                <ul className="divide-y divide-[var(--line)]">
                  {history.length === 0 ? (
                    <li className="py-8 text-center text-sm text-ink/40">
                      No history matches.
                    </li>
                  ) : (
                    history.map((item) => (
                      <li
                        key={`${item.source}-${item.id}`}
                        className="flex items-start gap-2 py-3.5"
                      >
                        <button
                          type="button"
                          onClick={() => openHistoryItem(item)}
                          className="min-w-0 flex-1 text-left transition-colors hover:opacity-80"
                        >
                          <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-mist">
                            {item.source}
                            {item.mode ? ` · ${item.mode}` : ""}
                          </span>
                          <span className="mt-0.5 block text-sm font-medium text-fjord">
                            {item.title}
                          </span>
                          {item.preview ? (
                            <span className="mt-0.5 line-clamp-2 block text-xs text-ink/45">
                              {item.preview}
                            </span>
                          ) : null}
                        </button>
                        {item.source === "import" ? (
                          <button
                            type="button"
                            disabled={continuingId === item.id}
                            onClick={() => continueFromImport(item.id, "work")}
                            className="shrink-0 rounded-md border border-[var(--line)] bg-white px-2.5 py-1.5 text-xs font-medium text-fjord hover:bg-ice/50 disabled:opacity-50"
                          >
                            {continuingId === item.id ? "…" : "Continue"}
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => openHistoryItem(item)}
                            className="shrink-0 rounded-md border border-[var(--line)] bg-white px-2.5 py-1.5 text-xs font-medium text-fjord hover:bg-ice/50"
                          >
                            Open
                          </button>
                        )}
                      </li>
                    ))
                  )}
                </ul>
              </div>
            </div>
          ) : null}

          {isChatTab ? (
            <>
              <div ref={scrollRef} className="chat-scroll">
                {!activeChat ? (
                  <div className="flex h-full min-h-[20rem] flex-col items-center justify-center px-6 text-center">
                    <div className="chat-avatar chat-avatar-ai mb-4 size-10 text-sm">
                      AI
                    </div>
                    <h2 className="font-display text-2xl tracking-tight text-fjord sm:text-3xl">
                      Educational workspace
                    </h2>
                    <p className="mt-2 max-w-md text-sm leading-relaxed text-ink/50">
                      Plan curriculum, continue imported history, draft feed packs,
                      and generate teaching visuals — with replies grounded in your
                      program brief.
                    </p>
                    <button
                      type="button"
                      onClick={startNewChat}
                      disabled={creating}
                      className="btn-primary mt-6 rounded-lg px-6"
                    >
                      {creating ? "Starting…" : "Start conversation"}
                    </button>
                  </div>
                ) : visibleMessages.length === 0 && !streaming ? (
                  <div className="flex h-full min-h-[16rem] flex-col items-center justify-center px-6 text-center">
                    <h2 className="font-display text-xl text-fjord sm:text-2xl">
                      {activeChat.title}
                    </h2>
                    <p className="mt-2 max-w-sm text-sm text-ink/45">
                      Describe the teaching outcome you need, or enable Image for a
                      visual.
                    </p>
                  </div>
                ) : (
                  <div className="mx-auto w-full max-w-3xl px-3 py-6 sm:px-6 sm:py-8">
                    {activeChat.title.startsWith("Continue:") ? (
                      <p className="mb-5 border-l-2 border-fjord/25 bg-ice/40 px-3 py-2 text-xs leading-relaxed text-ink/55">
                        Continuing imported history — prior transcript is loaded as
                        context for this conversation.
                      </p>
                    ) : null}
                    {visibleMessages.map((m) => {
                      const isUser = m.role === "user";
                      const img = m.image_path ? mediaUrl(m.image_path) : "";
                      return (
                        <div
                          key={m.id}
                          className={`chat-message-row group mb-6 flex gap-3 sm:mb-7 sm:gap-3.5 ${
                            isUser ? "flex-row-reverse" : ""
                          }`}
                        >
                          <div
                            className={`chat-avatar ${
                              isUser ? "chat-avatar-user" : "chat-avatar-ai"
                            }`}
                            aria-hidden
                          >
                            {isUser ? "Y" : "AI"}
                          </div>
                          <div
                            className={`min-w-0 max-w-[min(100%,40rem)] flex-1 ${
                              isUser ? "flex flex-col items-end" : ""
                            }`}
                          >
                            <p
                              className={`mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-mist ${
                                isUser ? "text-right" : ""
                              }`}
                            >
                              {isUser ? "You" : "Assistant"}
                            </p>
                            {editingId === m.id ? (
                              <div className="w-full space-y-2">
                                <textarea
                                  value={editDraft}
                                  onChange={(e) => setEditDraft(e.target.value)}
                                  rows={3}
                                  className="input-field rounded-md"
                                />
                                <div className="flex gap-2">
                                  <button
                                    type="button"
                                    onClick={saveEdit}
                                    disabled={busyMsgId === m.id}
                                    className="btn-primary rounded-md px-3 text-[11px]"
                                  >
                                    {busyMsgId === m.id
                                      ? "Saving…"
                                      : "Save & regenerate"}
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setEditingId(null);
                                      setEditDraft("");
                                    }}
                                    className="btn-secondary rounded-md px-3 text-[11px]"
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <>
                                <div
                                  className={
                                    isUser
                                      ? "rounded-xl bg-[var(--user-bubble)] px-4 py-2.5 text-[0.95rem] leading-relaxed text-snow"
                                      : "chat-assistant-bubble text-[0.95rem] leading-relaxed text-ink/88"
                                  }
                                >
                                  {isUser ? (
                                    <p className="whitespace-pre-wrap">
                                      {m.content}
                                    </p>
                                  ) : (
                                    <Markdown content={m.content} />
                                  )}
                                  {img ? (
                                    // eslint-disable-next-line @next/next/no-img-element
                                    <img
                                      src={img}
                                      alt="Generated teaching visual"
                                      className="mt-3 max-h-80 w-full rounded-md border border-[var(--line)] object-contain"
                                    />
                                  ) : null}
                                </div>
                                <div
                                  className={`mt-1.5 flex flex-wrap gap-1 opacity-100 sm:opacity-0 sm:transition-opacity sm:group-hover:opacity-100 ${
                                    isUser ? "justify-end" : ""
                                  }`}
                                >
                                  <button
                                    type="button"
                                    onClick={() => copyMessage(m)}
                                    className="rounded px-2 py-1 text-[11px] font-medium text-mist hover:bg-ice/60 hover:text-fjord"
                                  >
                                    {copiedId === m.id ? "Copied" : "Copy"}
                                  </button>
                                  {isUser ? (
                                    <button
                                      type="button"
                                      onClick={() => startEdit(m)}
                                      className="rounded px-2 py-1 text-[11px] font-medium text-mist hover:bg-ice/60 hover:text-fjord"
                                    >
                                      Edit
                                    </button>
                                  ) : null}
                                  {img ? (
                                    <a
                                      href={img}
                                      download
                                      className="rounded px-2 py-1 text-[11px] font-medium text-mist hover:bg-ice/60 hover:text-fjord"
                                    >
                                      Download
                                    </a>
                                  ) : null}
                                  <button
                                    type="button"
                                    disabled={busyMsgId === m.id}
                                    onClick={() => deleteMessage(m)}
                                    className="rounded px-2 py-1 text-[11px] font-medium text-mist hover:bg-red-50 hover:text-red-700"
                                  >
                                    Delete
                                  </button>
                                </div>
                              </>
                            )}
                          </div>
                        </div>
                      );
                    })}
                    {sending && imageMode ? (
                      <div className="chat-message-row mb-6 flex gap-3 sm:gap-3.5">
                        <div className="chat-avatar chat-avatar-ai" aria-hidden>
                          AI
                        </div>
                        <div>
                          <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-mist">
                            Assistant
                          </p>
                          <p className="text-sm text-mist">Generating image…</p>
                        </div>
                      </div>
                    ) : null}
                    {streaming &&
                    !visibleMessages.some(
                      (m) =>
                        m.role === "assistant" &&
                        streamText &&
                        (m.content === streamText ||
                          m.content.startsWith(streamText.slice(0, 48)) ||
                          streamText.startsWith(m.content.slice(0, 48)))
                    ) ? (
                      <div className="chat-message-row mb-6 flex gap-3 sm:gap-3.5">
                        <div className="chat-avatar chat-avatar-ai" aria-hidden>
                          AI
                        </div>
                        <div className="min-w-0 max-w-[min(100%,40rem)] flex-1">
                          <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-mist">
                            Assistant
                          </p>
                          <div className="chat-assistant-bubble text-[0.95rem] leading-relaxed text-ink/88">
                            {streamText ? (
                              <>
                                <Markdown content={streamText} />
                                <span className="chat-stream-caret" aria-hidden />
                              </>
                            ) : (
                              <p className="text-sm text-mist">
                                Composing response
                                <span className="chat-stream-dots" aria-hidden />
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>

              <div
                className="shrink-0 border-t border-transparent bg-gradient-to-t from-[var(--surface)] via-[var(--surface)] to-transparent px-3 pb-3 pt-2 sm:px-6 sm:pb-5"
                style={{
                  paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))",
                }}
              >
                <form
                  onSubmit={onSend}
                  className="mx-auto w-full max-w-3xl space-y-2"
                >
                  <div className="flex flex-wrap items-center gap-3 px-1 text-xs text-ink/50">
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={makeFeed}
                        onChange={(e) => setMakeFeed(e.target.checked)}
                        className="size-3.5 accent-fjord"
                      />
                      Make this a feed draft
                    </label>
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={imageMode}
                        onChange={(e) => setImageMode(e.target.checked)}
                        className="size-3.5 accent-fjord"
                      />
                      Image
                    </label>
                    {imageMode ? (
                      <select
                        value={imageStyle}
                        onChange={(e) =>
                          setImageStyle(e.target.value as "poster" | "general")
                        }
                        className="rounded-md border border-[var(--line)] bg-white px-2 py-1 text-xs text-fjord"
                      >
                        <option value="poster">Teaching poster</option>
                        <option value="general">General visual</option>
                      </select>
                    ) : null}
                  </div>
                  <div className="chat-composer flex items-end gap-2 px-3 py-2 sm:px-4 sm:py-2.5">
                    <textarea
                      ref={textareaRef}
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={onComposerKeyDown}
                      rows={1}
                      placeholder={
                        !activeChat
                          ? "Start a conversation to begin…"
                          : imageMode
                            ? "Describe the teaching visual…"
                            : "Message the workspace…"
                      }
                      disabled={sending || !activeChat}
                      className="max-h-[180px] min-h-[44px] flex-1 resize-none bg-transparent py-2.5 text-base text-ink outline-none placeholder:text-ink/35 disabled:opacity-50"
                    />
                    <button
                      type="submit"
                      disabled={sending || !draft.trim() || !activeChat}
                      className="mb-1 flex size-9 shrink-0 items-center justify-center rounded-xl bg-fjord text-snow transition-opacity disabled:opacity-35"
                      aria-label={imageMode ? "Generate image" : "Send message"}
                    >
                      <svg
                        width="16"
                        height="16"
                        viewBox="0 0 24 24"
                        fill="none"
                        aria-hidden
                      >
                        <path
                          d="M12 19V5M12 5l-6 6M12 5l6 6"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </button>
                  </div>
                  <p className="px-1 text-center text-[10px] text-mist">
                    Enter to send · Responses stream live · Feed drafts stay
                    unpublished until you review
                  </p>
                </form>
              </div>
            </>
          ) : null}
        </section>
      </div>
    </AppShell>
  );
}
