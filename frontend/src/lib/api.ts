const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";
const MEDIA_URL = process.env.NEXT_PUBLIC_MEDIA_URL ?? "";

export const TOKEN_KEY = "oer_access_token";
export const USER_KEY = "oer_user";

export function mediaUrl(path: string | null | undefined): string {
  if (!path) return "";
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${MEDIA_URL.replace(/\/$/, "")}${path.startsWith("/") ? path : `/${path}`}`;
}

export type User = {
  id: string;
  email: string;
  name: string;
  role: string;
  cadre: string;
  site: string;
  education_level: string;
  experience_years: number;
  learning_goals: string;
  topics_of_interest: string;
  preferred_language: string;
  local_context: string;
  created_at: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: User;
};

export type PackListItem = {
  id: string;
  status: string;
  topic: string;
  poster_title: string;
  poster_image_path: string;
  created_at: string;
  published_at: string | null;
  question_count: number;
};

export type Question = {
  id: string;
  prompt: string;
  question_type: string;
  rubric: string;
  sort_order: number;
};

export type Pack = {
  id: string;
  status: string;
  topic: string;
  poster_title: string;
  poster_caption: string;
  poster_visual_prompt: string;
  poster_image_path: string;
  elaboration: string;
  case_study: string;
  created_at: string;
  published_at: string | null;
  questions: Question[];
};

export type Submission = {
  id: string;
  question_id: string;
  answer: string;
  score: number;
  feedback: string;
  created_at: string;
};

export type SocialExport = {
  id: string;
  pack_id: string;
  platform: string;
  status: string;
  caption: string;
  visual_prompt: string;
  poster_title: string;
  poster_image_path: string;
  external_id: string;
  error_message: string;
  created_at: string;
};

export type ProgramBrief = {
  id: string;
  version: number;
  is_active: boolean;
  program_topic: string;
  target_learners: string;
  oer_rationale: string;
  distribution_channels: string;
  learning_objectives: string;
  approved_references: string;
  local_context: string;
  preferred_language: string;
  restricted_topics: string;
  brand_tone: string;
  responsible_educator: string;
  created_at: string;
};

export type ProgramBriefInput = Omit<
  ProgramBrief,
  "id" | "version" | "is_active" | "created_at"
>;

export type AiProject = {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
};

export type AiMessage = {
  id: string;
  role: string;
  content: string;
  image_path?: string;
  created_at: string;
};

export type AiChat = {
  id: string;
  project_id: string | null;
  title: string;
  mode: "work" | "personal" | string;
  created_at: string;
  updated_at: string;
  messages: AiMessage[];
};

export type AiChatListItem = {
  id: string;
  project_id: string | null;
  title: string;
  mode: string;
  created_at: string;
  updated_at: string;
};

export type HistoryItem = {
  id: string;
  title: string;
  source: "platform" | "import" | string;
  mode: string | null;
  updated_at: string | null;
  preview: string;
};

export type ImportConversation = {
  id: string;
  title: string;
  source_filename: string;
  user_text: string;
  conversation_created_at: string | null;
  conversation_updated_at: string | null;
  imported_at: string;
};

export type AiMessageResponse = {
  message: AiMessage;
  draft_pack_id: string | null;
  chat?: AiChat | null;
};

export type MessageToFeedResponse = {
  pack_id: string;
  status: string;
  poster_title: string;
};

function authHeaders(): HeadersInit {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem(TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function parseErrorMessage(text: string, statusText: string): Promise<string> {
  const trimmed = text.trim();
  if (!trimmed) return statusText;
  try {
    const data = JSON.parse(trimmed) as { detail?: unknown; message?: unknown };
    if (typeof data.detail === "string") return data.detail;
    if (data.detail != null) return JSON.stringify(data.detail);
    if (typeof data.message === "string") return data.message;
    return trimmed;
  } catch {
    return trimmed;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers ?? {}),
    },
  });
  const text = await res.text();
  if (!res.ok) {
    const message = await parseErrorMessage(text, res.statusText);
    if (res.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    }
    throw new Error(message || res.statusText);
  }
  if (!text.trim()) {
    return undefined as T;
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error("Invalid JSON response from API");
  }
}

export function saveAuth(token: string, user: User) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getStoredUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function hasToken(): boolean {
  return typeof window !== "undefined" && !!localStorage.getItem(TOKEN_KEY);
}

export const api = {
  signup: (body: {
    email: string;
    password: string;
    name: string;
    cadre?: string;
    site?: string;
    education_level?: string;
    experience_years?: number;
    learning_goals?: string;
    topics_of_interest?: string;
    preferred_language?: string;
    local_context?: string;
  }) =>
    request<AuthResponse>("/auth/signup", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  login: (body: { email: string; password: string }) =>
    request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  me: () => request<User>("/auth/me"),
  generatePack: (body: { topic: string; focus?: string }) =>
    request<Pack>("/packs/generate", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  regenerateImage: (id: string) =>
    request<Pack>(`/packs/${id}/regenerate-image`, { method: "POST" }),
  adminPacks: () => request<PackListItem[]>("/packs/admin"),
  feed: () => request<PackListItem[]>("/packs/feed"),
  getPack: (id: string) => request<Pack>(`/packs/${id}`),
  publishPack: (id: string) =>
    request<Pack>(`/packs/${id}/publish`, { method: "POST" }),
  deletePack: (id: string) =>
    request<void>(`/packs/${id}`, { method: "DELETE" }),
  publishSocial: (id: string) =>
    request<SocialExport[]>(`/packs/${id}/publish-social`, { method: "POST" }),
  submitAnswer: (questionId: string, answer: string) =>
    request<Submission>(`/submissions/questions/${questionId}`, {
      method: "POST",
      body: JSON.stringify({ answer }),
    }),
  mySubmissions: () => request<Submission[]>("/submissions/me"),
  currentProgramBrief: () =>
    request<ProgramBrief>("/program-brief/current"),
  programBriefHistory: () =>
    request<ProgramBrief[]>("/program-brief/history"),
  updateProgramBrief: (body: ProgramBriefInput) =>
    request<ProgramBrief>("/program-brief/current", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  workspaceProjects: () => request<AiProject[]>("/workspace/projects"),
  createWorkspaceProject: (body: { name: string; description?: string }) =>
    request<AiProject>("/workspace/projects", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  workspaceHistory: (q?: string) =>
    request<HistoryItem[]>(
      `/workspace/history${q?.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`
    ),
  workspaceImport: (id: string) =>
    request<ImportConversation>(`/workspace/imports/${id}`),
  continueImport: (
    id: string,
    body?: { mode?: "work" | "personal"; project_id?: string | null }
  ) =>
    request<AiChat>(`/workspace/imports/${id}/continue`, {
      method: "POST",
      body: JSON.stringify({
        mode: body?.mode ?? "work",
        project_id: body?.project_id ?? null,
      }),
    }),
  workspaceChats: (opts?: { mode?: string; project_id?: string }) => {
    const params = new URLSearchParams();
    if (opts?.mode) params.set("mode", opts.mode);
    if (opts?.project_id) params.set("project_id", opts.project_id);
    const qs = params.toString();
    return request<AiChatListItem[]>(`/workspace/chats${qs ? `?${qs}` : ""}`);
  },
  createWorkspaceChat: (body: {
    mode: "work" | "personal";
    project_id?: string | null;
    title?: string;
  }) =>
    request<AiChat>("/workspace/chats", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getWorkspaceChat: (id: string) => request<AiChat>(`/workspace/chats/${id}`),
  renameWorkspaceChat: (id: string, title: string) =>
    request<AiChat>(`/workspace/chats/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  deleteWorkspaceChat: (id: string) =>
    request<void>(`/workspace/chats/${id}`, { method: "DELETE" }),
  sendWorkspaceMessage: (
    chatId: string,
    body: { content: string; make_feed?: boolean }
  ) =>
    request<AiMessageResponse>(`/workspace/chats/${chatId}/messages`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  streamWorkspaceMessage: async (
    chatId: string,
    body: { content: string; make_feed?: boolean },
    handlers: {
      onUser?: (message: AiMessage) => void;
      onDelta?: (text: string) => void;
      onDone?: (payload: AiMessageResponse) => void;
      onFeed?: (draftPackId: string) => void;
      onError?: (detail: string) => void;
    }
  ) => {
    const res = await fetch(`${API_URL}/workspace/chats/${chatId}/messages/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...authHeaders(),
      },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text();
      const message = await parseErrorMessage(text, res.statusText);
      if (res.status === 401 && typeof window !== "undefined") {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
      }
      throw new Error(message || res.statusText);
    }
    if (!res.body) {
      throw new Error("Streaming is not supported in this browser");
    }

    const dispatch = (part: string) => {
      const line = part
        .split("\n")
        .map((l) => l.trim())
        .find((l) => l.startsWith("data:"));
      if (!line) return;
      const raw = line.slice(5).trim();
      if (!raw) return;
      let event: {
        type?: string;
        message?: AiMessage;
        text?: string;
        detail?: string;
        draft_pack_id?: string | null;
        chat?: AiChat | null;
      };
      try {
        event = JSON.parse(raw) as typeof event;
      } catch {
        return;
      }
      if (event.type === "user" && event.message) {
        handlers.onUser?.(event.message);
      } else if (event.type === "delta" && event.text) {
        handlers.onDelta?.(event.text);
      } else if (event.type === "done" && event.message) {
        handlers.onDone?.({
          message: event.message,
          draft_pack_id: event.draft_pack_id ?? null,
          chat: event.chat ?? null,
        });
      } else if (event.type === "feed" && event.draft_pack_id) {
        handlers.onFeed?.(event.draft_pack_id);
      } else if (event.type === "feed_error") {
        handlers.onError?.(event.detail || "Draft feed pack failed");
      } else if (event.type === "error") {
        handlers.onError?.(event.detail || "Stream failed");
      }
    };

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (value) {
        buffer += decoder.decode(value, { stream: true });
      }
      const parts = buffer.split("\n\n");
      buffer = done ? "" : (parts.pop() ?? "");
      for (const part of parts) {
        if (part.trim()) dispatch(part);
      }
      // Flush a trailing event that may omit the final blank line.
      if (done && buffer.trim()) {
        dispatch(buffer);
        buffer = "";
      }
      if (done) break;
    }
  },
  editWorkspaceMessage: (
    chatId: string,
    messageId: string,
    body: { content: string; regenerate?: boolean }
  ) =>
    request<AiMessageResponse>(
      `/workspace/chats/${chatId}/messages/${messageId}`,
      {
        method: "PATCH",
        body: JSON.stringify(body),
      }
    ),
  deleteWorkspaceMessage: (chatId: string, messageId: string) =>
    request<void>(`/workspace/chats/${chatId}/messages/${messageId}`, {
      method: "DELETE",
    }),
  workspaceMessageToFeed: (
    chatId: string,
    messageId: string,
    body?: { publish?: boolean }
  ) =>
    request<MessageToFeedResponse>(
      `/workspace/chats/${chatId}/messages/${messageId}/to-feed`,
      {
        method: "POST",
        body: JSON.stringify({ publish: body?.publish ?? false }),
      }
    ),
  generateWorkspaceImage: (
    chatId: string,
    body: {
      prompt: string;
      make_feed?: boolean;
      style?: "poster" | "general";
    }
  ) =>
    request<AiMessageResponse>(`/workspace/chats/${chatId}/images`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
