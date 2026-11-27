export type AgentStatus =
  | "idle"
  | "working"
  | "terminando"
  | "waiting_approval"
  | "offline";

export interface AgentStateItem {
  agent_id: string;
  display_name?: string;
  role?: string;
  status: AgentStatus | string;
  current_task?: string;
  activity?: AgentActivityItem[];
}

export interface AgentActivityItem {
  action: string;
  status: string;
  details?: string;
  at?: string;
}

export interface MatchArgument {
  label: string;
  detail: string;
}

export interface OutreachVariant {
  approach: "direct_technical" | "business_roi" | "agile_collaborative" | string;
  subject: string;
  body: string;
}

export interface Traceability {
  source_platform: string;
  source_url?: string | null;
  company_or_client_name: string;
  contact_channel: string;
  contact_ref: string;
  contact_pending: boolean;
}

export interface DeliverableContent {
  fit_score?: number | null;
  match_probability?: number | null;
  eligible?: boolean;
  recommended?: boolean;
  role_title?: string;
  company?: string;
  prospect_name?: string;
  opportunity_type?: string;
  market?: string;
  url?: string;
  source_url?: string;
  summary?: string;
  tailored_summary?: string;
  proposed_solution?: string;
  gaps?: string[];
  pain_points?: string[];
  missing_info?: string[];
  next_steps?: string[];
  interview_prep?: string[];
  match_arguments?: (string | MatchArgument)[];
  outreach_variants?: OutreachVariant[];
  application_channel?: string;
  application_instructions?: string;
  hourly_rate_usd?: number | null;
  rate_justification?: string;
  complexity?: "baja" | "media" | "alta" | string;
  estimated_hours_per_day?: string;
  estimated_timeline?: string;
  delivery_modalities?: Array<{ model: string; description: string }>;
  preview_policy?: string;
  detailed_budget_note?: string;
  source_platform?: string;
  company_or_client_name?: string;
  contact_channel?: string;
  contact_ref?: string;
  contact_pending?: boolean;
  cv_reference?: string;
  short_pitch?: string;
  external_action?: string;
  reason?: string;
  [key: string]: unknown;
}

export interface DeliverableItem {
  id: string;
  agent_id?: string;
  category?: string;
  title?: string;
  source?: string;
  source_url?: string;
  fit_score?: number | null;
  match_probability?: number | null;
  summary?: string;
  status?: string;
  content_json?: DeliverableContent;
  content?: DeliverableContent;
  traceability?: Traceability;
}

export interface PreviewItem {
  id: string;
  title: string;
  source: string;
  fit_score?: number | null;
  summary: string;
  category?: string;
  content?: DeliverableContent | null;
  traceability?: Traceability;
}

export interface DailyBriefing {
  sara_message: string;
  jobs_count: number;
  clients_count: number;
  jobs_preview: PreviewItem[];
  clients_preview: PreviewItem[];
  reports_ready: number;
}

export interface FollowUpSummary {
  sent: number;
  awaiting_reply: number;
  responded: number;
  closed: number;
  total: number;
}

export interface TokenAlert {
  alert: boolean;
  exhausted: boolean;
  used: number;
  limit: number;
  remaining: number;
  ratio: number;
  threshold: number;
  message: string;
}

export interface SourceFinding {
  agent: string;
  title: string;
  source_platform: string;
  source_url?: string | null;
  application_status: string;
  message: string;
}

export interface Advisor {
  token_alert: TokenAlert;
  suggestions: string[];
  findings: SourceFinding[];
}

export interface AutomationAgentStatus {
  running: boolean;
  last_run?: string | null;
  next_run?: string | null;
  last_result?: unknown;
  last_error?: string | null;
  runs: number;
}

export interface AutomationStatus {
  state: "stopped" | "running" | "paused";
  enabled: boolean;
  started_at?: string | null;
  reason: string;
  max_age_days: number;
  budget: TokenAlert;
  agents: Record<string, AutomationAgentStatus>;
}

export interface PublicOfficeSummary {
  mode: string;
  actions_enabled: boolean;
  agents: AgentStateItem[];
  daily_briefing: DailyBriefing;
  follow_up?: FollowUpSummary;
  advisor?: Advisor;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  operator: string;
}

export interface ReviewResponse {
  status: "approved" | "rejected";
  operator: string;
  deliverable: DeliverableItem;
  execution: DeliverableContent | null;
  message: string;
}

export interface BatchResult {
  processed: number;
  saved_for_approval: number;
  duplicates: number;
  filtered_out: number;
  total_tokens: number;
  reason?: string;
  results: Array<{
    index: number;
    url: string;
    executed: boolean;
    saved_for_approval: boolean;
    duplicate: boolean;
    filtered_out: boolean;
    reason?: string;
    tokens_used?: number;
    evaluation?: DeliverableContent;
    activity?: AgentActivityItem[];
  }>;
}

export interface BatchResponse {
  operator: string;
  result: BatchResult;
  age_filtered?: number;
}

export type MentorMode =
  | "explain"
  | "quiz"
  | "interview_prep"
  | "client_negotiation";

export interface QuizQuestionItem {
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
}

export interface LucianoSessionPayload {
  mode: MentorMode;
  title: string;
  summary: string;
  explanation_or_guide: string;
  code_or_prompt_example: string;
  quiz_questions?: QuizQuestionItem[];
  communication_tips?: string[];
}

export interface LucianoSessionResponse {
  operator: string;
  provider?: string;
  tokens_used?: number;
  session: LucianoSessionPayload;
  activity?: AgentActivityItem[];
}

export type OutreachStatus =
  | "enviado"
  | "espera_respuesta"
  | "respondido"
  | "cerrado"
  | "pending_approval"
  | "approved"
  | "rejected";

export interface OutreachRecord {
  id: string;
  agent_id: string;
  category: string;
  title: string;
  recipient: string;
  source_platform: string;
  source_url?: string | null;
  source_url_of_application?: string | null;
  company_or_client_name: string;
  contact_channel: string;
  contact_ref: string;
  contact_ref_pending: boolean;
  full_text: string;
  summary: string;
  cv_reference?: string | null;
  attachment_reference?: string | null;
  hourly_rate_usd?: number | null;
  rate_model?: string | null;
  status: OutreachStatus;
  gmail_message_id?: string | null;
  gmail_thread_id?: string | null;
  gmail_label?: "Clientes" | "Postulaciones" | string | null;
  last_response_at?: string | null;
  notes?: string | null;
  operator?: string | null;
  created_at?: string | null;
}

export interface GmailStatus {
  enabled: boolean;
  account?: string | null;
  labels?: string[];
  reason?: string | null;
}

export interface GmailUpdate {
  gmail_message_id: string;
  gmail_thread_id: string;
  gmail_label: string;
  subject: string;
  from: string;
  date: string;
  snippet: string;
  known_thread: boolean;
}

export interface GmailSyncResult {
  checked: boolean;
  updates: GmailUpdate[];
  reason?: string | null;
}

export interface SourceItem {
  title?: string;
  source_platform: string;
  source_url: string;
  company_or_client_name: string;
  contact_channel: string;
  contact_ref: string;
  raw_client_text?: string;
  raw_job_text?: string;
  prefiltered_out?: boolean;
  prefilter_reason?: string;
}

export interface SourceCollectResult {
  platform: string;
  fetched: number;
  prefiltered_out: number;
  items: SourceItem[];
  evaluate: boolean;
  notes?: string[];
  batch?: BatchResult | null;
}

export type BatchItem = {
  job_url?: string;
  raw_job_text?: string;
  client_ref?: string;
  raw_client_text?: string;
  source?: string;
  source_platform?: string;
  source_url?: string;
  published_at?: string;
  company_or_client_name?: string;
  contact_channel?: string;
  contact_ref?: string;
  market?: "LATAM_ES" | "GLOBAL_EN";
  channel?: string;
};

export type BatchPayload = {
  item_type: "job" | "client";
  items: BatchItem[];
  market?: "LATAM_ES" | "GLOBAL_EN";
  min_fit_score?: number;
  max_items_per_batch?: number;
};
