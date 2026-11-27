import type {
  AutomationStatus,
  BatchPayload,
  BatchResponse,
  DeliverableItem,
  GmailDraftResult,
  GmailStatus,
  GmailSyncResult,
  LoginResponse,
  LucianoSessionResponse,
  MentorMode,
  OutreachRecord,
  OutreachStatus,
  PublicOfficeSummary,
  ReviewResponse,
  SourceCollectResult,
} from "../types/office";

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

export class UnauthorizedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "UnauthorizedError";
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const data: unknown = await res.json();
    if (typeof data === "object" && data !== null) {
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) {
        return detail
          .map((entry) => {
            if (typeof entry === "object" && entry !== null && "msg" in entry) {
              return String((entry as { msg: unknown }).msg);
            }
            return String(entry);
          })
          .join("; ");
      }
      const message = (data as { message?: unknown }).message;
      if (typeof message === "string") return message;
    }
  } catch {
    // La respuesta no era JSON; se reporta el código HTTP.
  }
  return `Error HTTP ${res.status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new Error(
      `No se pudo conectar con el backend en ${API_BASE}. Verificá que FastAPI esté levantado.`,
    );
  }
  if (!res.ok) {
    const message = await parseError(res);
    throw res.status === 401 ? new UnauthorizedError(message) : new Error(message);
  }
  return (await res.json()) as T;
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export function fetchPublicOfficeSummary(): Promise<PublicOfficeSummary> {
  return request<PublicOfficeSummary>("/api/office/public-summary");
}

export function loginOperator(
  username: string,
  password: string,
): Promise<LoginResponse> {
  return request<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function fetchOperatorMe(token: string): Promise<{
  authenticated: boolean;
  operator: string;
  role: string;
}> {
  return request("/api/auth/me", { headers: authHeaders(token) });
}

export function fetchPendingDeliverables(token: string): Promise<DeliverableItem[]> {
  return request<{ items: DeliverableItem[] }>(
    "/api/deliverables?deliverable_status=pending_approval",
    { headers: authHeaders(token) },
  ).then((data) => data.items ?? []);
}

export function reviewDeliverable(
  token: string,
  deliverableId: string,
  decision: "approved" | "rejected",
  notes = "",
): Promise<ReviewResponse> {
  return request<ReviewResponse>(
    `/api/deliverables/${encodeURIComponent(deliverableId)}/review`,
    {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ decision, notes }),
    },
  );
}

export function runBatchEvaluationApi(
  token: string,
  payload: BatchPayload,
): Promise<BatchResponse> {
  return request<BatchResponse>("/api/office/batch-evaluate", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
}

export function runLucianoSessionApi(
  token: string,
  payload: {
    mode: MentorMode;
    topic: string;
    user_context?: string;
    num_questions?: number;
  },
): Promise<LucianoSessionResponse> {
  return request<LucianoSessionResponse>("/api/agents/luciano/session", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
}

export interface OutreachFeed {
  items: OutreachRecord[];
  reason?: string | null;
}

export function fetchOutreachFeed(
  token: string,
  filters: { status?: string; agent_id?: string } = {},
): Promise<OutreachFeed> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.agent_id) params.set("agent_id", filters.agent_id);
  const query = params.toString();
  return request<OutreachFeed>(
    `/api/outreach${query ? `?${query}` : ""}`,
    { headers: authHeaders(token) },
  );
}

export function fetchOutreachRecords(
  token: string,
  filters: { status?: string; agent_id?: string } = {},
): Promise<OutreachRecord[]> {
  return fetchOutreachFeed(token, filters).then((data) => data.items ?? []);
}

export function updateOutreachStatusApi(
  token: string,
  recordId: string,
  status: OutreachStatus,
  notes = "",
): Promise<OutreachRecord> {
  return request<OutreachRecord>(
    `/api/outreach/${encodeURIComponent(recordId)}/status`,
    {
      method: "PATCH",
      headers: authHeaders(token),
      body: JSON.stringify({ status, notes }),
    },
  );
}

export function fetchGmailStatus(token: string): Promise<GmailStatus> {
  return request<GmailStatus>("/api/gmail/status", { headers: authHeaders(token) });
}

export function syncGmailResponses(token: string): Promise<GmailSyncResult> {
  return request<GmailSyncResult>("/api/gmail/sync", {
    method: "POST",
    headers: authHeaders(token),
  });
}

export function registerGmailSentAction(
  token: string,
  payload: { outreach_id: string; gmail_message_id: string; label: "Clientes" | "Postulaciones" },
): Promise<{ external_action: string; error?: string | null }> {
  return request("/api/gmail/register-sent", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
}

export function createGmailControlDraft(
  token: string,
  outreachId: string,
): Promise<GmailDraftResult> {
  return request<GmailDraftResult>("/api/gmail/create-control-draft", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ outreach_id: outreachId, operator_confirmed: true }),
  });
}

export function collectSourcesApi(
  token: string,
  payload: {
    platform: "upwork" | "freelancer" | "remoteok" | "wwr" | "all";
    item_type: "client" | "job";
    upwork_limit?: number;
    freelancer_limit?: number;
    evaluate?: boolean;
    market?: "LATAM_ES" | "GLOBAL_EN";
    min_fit_score?: number;
    max_items_per_batch?: number;
  },
): Promise<SourceCollectResult> {
  return request<SourceCollectResult>("/api/sources/collect", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
}

export interface AutomationActionResult {
  status: AutomationStatus;
}

export function fetchAutomationStatus(token: string): Promise<AutomationActionResult> {
  return request<AutomationActionResult>("/api/automation/status", {
    headers: authHeaders(token),
  });
}

export function startAutomation(token: string): Promise<AutomationActionResult> {
  return request<AutomationActionResult>("/api/automation/start", {
    method: "POST",
    headers: authHeaders(token),
  });
}

export function pauseAutomation(token: string, reason?: string): Promise<AutomationActionResult> {
  return request<AutomationActionResult>("/api/automation/pause", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ reason: reason ?? "Pausado manualmente por el operador" }),
  });
}

export function resumeAutomation(token: string): Promise<AutomationActionResult> {
  return request<AutomationActionResult>("/api/automation/resume", {
    method: "POST",
    headers: authHeaders(token),
  });
}

export function stopAutomation(token: string): Promise<AutomationActionResult> {
  return request<AutomationActionResult>("/api/automation/stop", {
    method: "POST",
    headers: authHeaders(token),
  });
}
