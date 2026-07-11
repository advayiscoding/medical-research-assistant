// Typed API client — the single place that knows how to reach the backend and
// how to attach the JWT. Every page calls these functions, never fetch()
// directly, so auth headers, base URL, and error shaping live in one spot.

import type {
  ChatSession,
  DocumentItem,
  DocumentUploadResponse,
  PostMessageResponse,
  SearchHistoryItem,
  SearchResponse,
  SessionDetail,
  User,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

const TOKEN_KEY = "medresearch_token";

export const tokenStore = {
  get: (): string | null =>
    typeof window === "undefined" ? null : localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = tokenStore.get();
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  // Don't force JSON content-type for FormData (browser sets the boundary).
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (res.status === 401) {
    tokenStore.clear();
    // Let callers/route guards react; surface a typed error.
    throw new ApiError(401, "Session expired. Please sign in again.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  // --- auth ---
  register: (email: string, password: string, fullName?: string) =>
    request<{ access_token: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name: fullName || null }),
    }),
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<User>("/auth/me"),

  // --- search ---
  search: (query: string, maxResults = 10) =>
    request<SearchResponse>("/search", {
      method: "POST",
      body: JSON.stringify({ query, max_results: maxResults }),
    }),

  // --- chat ---
  createSession: () =>
    request<ChatSession>("/chat/sessions", { method: "POST" }),
  listSessions: () => request<ChatSession[]>("/chat/sessions"),
  getSession: (id: string) => request<SessionDetail>(`/chat/sessions/${id}`),
  postMessage: (id: string, question: string, topK = 5) =>
    request<PostMessageResponse>(`/chat/sessions/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ question, top_k: topK }),
    }),

  // --- documents ---
  listDocuments: () => request<DocumentItem[]>("/documents"),
  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentUploadResponse>("/documents", {
      method: "POST",
      body: form,
    });
  },

  // --- history ---
  searchHistory: () => request<SearchHistoryItem[]>("/history/searches"),
};
