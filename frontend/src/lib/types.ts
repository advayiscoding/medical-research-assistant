// Mirror of the backend Pydantic schemas. Kept in one file so a backend
// contract change has exactly one place to update on the frontend.

export interface User {
  id: string;
  email: string;
  full_name: string | null;
}

export interface Paper {
  id: string;
  pmid: string | null;
  doi: string | null;
  title: string;
  authors: string[];
  abstract: string | null;
  journal: string | null;
  publication_date: string | null;
  source: string;
  sources: string[];
  citation_count: number;
  url: string | null;
  is_preprint: boolean;
}

export interface SearchResponse {
  query: string;
  count: number;
  papers: Paper[];
}

export interface RetrievedChunk {
  chunk_id: string | null;
  chroma_id: string;
  text: string;
  score: number;
  source_type: string;
  pmid: string | null;
  doi: string | null;
  title: string;
  journal: string;
  year: number | null;
  source: string;
  sources: string[];
  url: string | null;
  citation_count: number;
}

export interface Citation {
  marker: number;
  chunk: RetrievedChunk;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  citations: Citation[];
}

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface SessionDetail extends ChatSession {
  messages: ChatMessage[];
}

export interface PostMessageResponse {
  session_id: string;
  user_message: ChatMessage;
  assistant_message: ChatMessage;
  insufficient_evidence: boolean;
}

export interface DocumentItem {
  id: string;
  filename: string;
  title: string | null;
  status: "pending" | "processing" | "ready" | "failed";
  error: string | null;
  created_at: string;
}

export interface DocumentUploadResponse {
  document: DocumentItem;
  chunks_created: number;
}

export interface SearchHistoryItem {
  id: string;
  query: string;
  result_count: number;
  created_at: string;
}
