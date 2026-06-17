// Single API client. Same-origin /api in production (FastAPI serves the SPA);
// `next dev` proxies /api to localhost:8000 via the rewrite in next.config.mjs.

const BASE = "/api";

export type AuthSession = {
  access_token: string;
  refresh_token: string | null;
  expires_at?: number | null;
  expires_in?: number | null;
  user_id?: string | null;
};

export type ApiResult<T> = {
  data: T | null;
  error: string | null;
  status: number;
};

type CallOpts = {
  token?: string | null;
  json?: unknown;
  form?: FormData;
};

type AuthRefreshHandler = (failedToken: string) => Promise<string | null>;

let authRefreshHandler: AuthRefreshHandler | null = null;

export function configureAuthRefresh(handler: AuthRefreshHandler | null) {
  authRefreshHandler = handler;
}

function asMessage(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (detail) return JSON.stringify(detail);
  return `Server error (HTTP ${status})`;
}

async function send<T>(
  method: string,
  path: string,
  opts: CallOpts,
  tokenOverride?: string | null,
): Promise<ApiResult<T>> {
  const headers: Record<string, string> = {};
  const authToken = tokenOverride ?? opts.token;
  if (authToken) headers.Authorization = `Bearer ${authToken}`;

  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  } else if (opts.form) {
    body = opts.form; // browser sets multipart boundary
  }

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { method, headers, body });
  } catch {
    return {
      data: null,
      error: "Cannot reach the server. Check your connection and try again.",
      status: 0,
    };
  }

  let payload: unknown = null;
  try {
    payload = await res.json();
  } catch {
    /* non-JSON body (shouldn't happen on our API) */
  }

  if (!res.ok) {
    const detail = (payload as { detail?: unknown } | null)?.detail;
    return { data: null, error: asMessage(detail, res.status), status: res.status };
  }
  return { data: payload as T, error: null, status: res.status };
}

export async function call<T>(
  method: string,
  path: string,
  opts: CallOpts = {},
): Promise<ApiResult<T>> {
  const first = await send<T>(method, path, opts);
  if (first.status === 401 && opts.token && authRefreshHandler) {
    const freshToken = await authRefreshHandler(opts.token);
    if (freshToken) return send<T>(method, path, opts, freshToken);
  }
  return first;
}

// ---- API types ----
export type Status = {
  total_files: number;
  total_chars: number;
  total_tokens: number;
  mode: "direct" | "rag";
  processed_documents?: number;
  available_reports?: number;
  available_summaries?: number;
  exported_conversations?: number;
  generated_outputs?: number;
  organization_id?: string;
  organization_name?: string;
  org_enabled?: boolean;
  user_id?: string;
  role?: "user" | "author" | "admin";
  can_read_all?: boolean;
  can_write_all?: boolean;
  is_read_only?: boolean;
  can_upload?: boolean;
  can_delete?: boolean;
};

export type FileRow = {
  id: string;
  filename: string;
  file_type: string;
  char_count: number;
  upload_date: string;
  indexed: boolean;
};

export type UploadResponse = Status & {
  job_id?: string | null;
  uploaded: { file_id: string; filename: string; char_count: number }[];
  replaced: { file_id: string; filename: string; char_count: number }[];
  skipped: { filename: string; reason: string }[];
};

export type AskResponse = {
  answer: string;
  mode: "direct" | "rag" | "structured" | "decision" | "memory" | "none";
  sources: string[];
  sql?: string;
};

export type SearchResult = {
  content: string;
  filename: string;
  snippet: string;
  rank: number;
};

export type SearchResponse = {
  query: string;
  results: SearchResult[];
};

export type ConversationMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  mode?: AskResponse["mode"] | null;
  sources: string[];
  metadata: Record<string, unknown>;
  created_at: string;
};

export type GeneratedOutput = {
  id: string;
  kind: string;
  title: string;
  content: string;
  format: string;
  sources: string[];
  metadata: Record<string, unknown>;
  storage_path?: string | null;
  file_id?: string | null;
  created_at: string;
};

export type ConversationExport = {
  filename: string;
  mime_type: string;
  content: string;
  attached: boolean;
  attached_file?: unknown;
};

export type Memory = {
  id: string;
  content: string;
  created_at: string;
};

export type MemberRow = {
  organization_id: string;
  user_id: string;
  email?: string | null;
  role: "user" | "author" | "admin";
  is_bootstrap_admin?: boolean;
  created_at: string;
};

export type SummarizeResponse = {
  summary: string;
  mode: "direct" | "rag" | "none";
  collective?: boolean;
};

export type ReportResponse = {
  id: string | null;
  report_ids?: string[];
  created_at?: string | null;
  job_id?: string | null;
  report: string;
  mode: "direct" | "rag" | "none";
  sources: string[];
  structured_analysis: string;
  qualitative_analysis: string;
  collective?: boolean;
};

export type ReportRow = {
  id: string;
  title: string;
  report: string;
  mode: "direct" | "rag" | "none";
  sources: string[];
  created_at: string;
};

export type JobRow = {
  id: string;
  kind: string;
  status: "queued" | "running" | "completed" | "failed";
  detail: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};
