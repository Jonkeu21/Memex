// Mirrors backend/schemas.py — kept in sync by hand. Field names match the
// Python pydantic models 1:1 so the JSON wire format is the only contract.

export type SourceType = 'url' | 'file' | 'text' | 'voice';
export type QueueStatus =
  | 'queued'
  | 'processing'
  | 'filed'
  | 'needs_review'
  | 'failed';
export type ClaudeService = 'worker' | 'telegram_bot' | 'dashboard';
export type ClaudePurpose = 'file' | 'retrieve';

export interface QueueItem {
  id: number;
  created_at: string;
  updated_at: string;
  source_type: SourceType;
  source_payload: Record<string, unknown>;
  submitter: string;
  status: QueueStatus;
  attempts: number;
  last_error: string | null;
  processed_at: string | null;
  confidence: number | null;
  vault_path: string | null;
  claude_session_id: string | null;
  claude_input_tokens: number | null;
  claude_output_tokens: number | null;
  claude_duration_ms: number | null;
}

export interface QueueListing {
  items: QueueItem[];
  next_cursor: number | null;
}

export interface QueueActionAck {
  id: number;
  status: QueueStatus;
}

export interface InboxItem {
  path: string;
  title: string;
  captured_at: string | null;
  processed_at: string | null;
  confidence: number | null;
  needs_review: boolean;
  suggested_taxonomy: string | null;
  reason_for_inbox: string | null;
  queue_id: number | null;
  source: SourceType | null;
  size_bytes: number | null;
}

export interface InboxListing {
  items: InboxItem[];
}

export interface InboxFile {
  path: string;
  front_matter: Record<string, unknown>;
  body: string;
}

export interface TaxonomyOverride {
  autonomous_threshold: number | null;
  review_threshold: number | null;
}

export interface TaxonomyFolder {
  path: string;
  description: string;
  keywords: string[];
  confidence_override: TaxonomyOverride | null;
}

export interface TaxonomyDocument {
  schema_version: number;
  default_route: string;
  confidence: {
    autonomous_threshold: number;
    review_threshold: number;
  };
  folders: TaxonomyFolder[];
}

export interface TaxonomyResponse {
  document: TaxonomyDocument;
  raw_yaml: string;
}

export interface CaptureFile {
  path: string;
  title: string;
  captured_at: string | null;
  processed_at: string | null;
  folder: string;
  tags: string[];
  needs_review: boolean;
  size_bytes: number | null;
}

export interface CaptureListing {
  items: CaptureFile[];
  next_cursor: number | null;
}

export interface CaptureFileBody {
  path: string;
  front_matter: Record<string, unknown>;
  body: string;
}

export interface CallsByHourBucket {
  hour: string;
  service: ClaudeService;
  count: number;
  input_tokens: number;
  output_tokens: number;
}

export interface ClaudeCallRow {
  id: number;
  ts: string;
  service: ClaudeService;
  purpose: ClaudePurpose;
  queue_item_id: number | null;
  session_id: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  duration_ms: number | null;
  exit_code: number;
}

export interface RateLimitSnapshot {
  available: boolean;
  total_24h: number;
  error_rate_5m: number;
  last_call_ts: string | null;
  by_hour: CallsByHourBucket[];
  recent_calls: ClaudeCallRow[];
  services_breakdown_24h: Record<string, number>;
}

export interface RetrievalSource {
  path: string;
  title: string;
  exists: boolean;
}

export interface RetrievalQuote {
  source_index: number;
  text: string;
}

export interface RetrievalResponse {
  answer: string;
  sources: RetrievalSource[];
  quotes: RetrievalQuote[];
  confidence: number;
  duration_ms: number | null;
  session_id: string | null;
}

export interface ApiError {
  status: number;
  code: string;
  message: string;
}
