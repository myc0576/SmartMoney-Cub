export type Tone = 'up' | 'down' | 'flat';

export interface Summary {
  trade_count: number;
  win_count: number;
  loss_count: number;
  flat_count: number;
  win_rate: number;
  profit_factor: number | null;
  profit_factor_note: string;
  total_net_pnl: number;
  total_fees: number;
  avg_return_pct: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  avg_holding_days: number;
  max_drawdown: number;
  open_position_count: number;
  sample_note: string;
  equity_curve: { exit_time: string; symbol: string; net_pnl: number; cumulative_pnl: number }[];
}

export interface RoundTrip {
  round_trip_id: string;
  symbol: string;
  name: string;
  regime: string;
  thesis: string;
  tags: string[];
  entry_time: string;
  exit_time: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  net_pnl: number;
  return_pct: number;
  fees: number;
  holding_days: number;
  invalidation_price: number | null;
  matched_lots: { entry_time: string; entry_price: number; quantity: number; buy_fee: number }[];
}

export interface OpenPosition {
  position_id: string;
  symbol: string;
  name: string;
  quantity: number;
  avg_cost: number;
  opened_at: string;
}

export interface Issue {
  code: string;
  severity: string;
  symbol: string;
  fill_id: string;
  detail: string;
}

export interface CalendarDay {
  date: string;
  trade_count: number;
  net_pnl: number;
  win_count: number;
  trades: { round_trip_id: string; symbol: string; name: string; net_pnl: number; return_pct: number }[];
}

export interface Portfolio {
  portfolio_id: string;
  name: string;
  description: string;
}

export interface Overview {
  portfolio_id: string;
  portfolios: Portfolio[];
  year: number;
  month: number;
  summary: Summary;
  calendar: CalendarDay[];
  open_positions: OpenPosition[];
  blocking_issues: Issue[];
  issues: Issue[];
  ledger_status: string;
  round_trips: RoundTrip[];
  recent_trades: RoundTrip[];
  fill_count: number;
  recent_documents: SourceDocument[];
}

export interface SourceDocument {
  document_id: string;
  file_name: string;
  media_type: string;
  byte_size: number;
  source_kind: string;
  imported_at: string;
}

export interface CandidateRow {
  candidate_id: string;
  row_index: number;
  trade_date: string | null;
  trade_time: string | null;
  symbol: string | null;
  name: string | null;
  side: string | null;
  price: number | null;
  quantity: number | null;
  field_confidence: Record<string, number>;
  raw_text: string;
  warnings: string[];
}

export interface Extraction {
  extraction_id: string;
  document_id: string;
  engine: string;
  engine_version: string;
  status: string;
  row_count: number;
  mean_confidence: number | null;
  detail: Record<string, unknown>;
  rows: CandidateRow[];
}

export interface UploadResult {
  status: string;
  document: SourceDocument;
  extraction: Extraction;
  engine_status: Record<string, boolean>;
  raw_file_stays_local: boolean;
}

export interface KeyValue {
  key: string;
  trade_count: number;
  win_rate: number;
  net_pnl: number;
  avg_return_pct: number;
  profit_factor: number | null;
  small_sample: boolean;
}

export interface RuleRecord {
  rule_id: string;
  family: string | null;
  title: string | null;
  status: string;
  metrics: Record<string, unknown>;
  promotion_note: string | null;
  promoted_at: string | null;
  updated_at: string;
}

export interface ProviderView {
  provider_id: string;
  label: string;
  base_url: string;
  protocol: string;
  default_model: string;
  requires_key: boolean;
  has_key: boolean;
  key_source: string;
  description: string;
  stored_base_url?: string;
  stored_model?: string;
}

export interface SessionSummary {
  session_id: string;
  title: string;
  context: Record<string, unknown>;
  provider_id: string;
  model: string;
  reasoning: string;
  status: string;
  forked_from: string | null;
  created_at: string;
  updated_at: string;
}

export interface SessionEvent {
  event_id: number;
  seq: number;
  kind: string;
  role: string | null;
  payload: Record<string, any>;
  created_at: string;
}

export interface AuditRecord {
  audit_id: number;
  session_id: string | null;
  provider_id: string;
  model: string;
  payload_sha256: string;
  sent_keys: string[];
  redaction_summary: Record<string, any>;
  blocked: boolean;
  reason: string | null;
  created_at: string;
}

export interface Meta {
  app: string;
  version: string;
  safety: string;
  redaction_policy: string;
  engine: Record<string, boolean>;
  providers: ProviderView[];
  default_provider: string;
  store_counts: Record<string, number>;
  trend_color_scheme: 'cn' | 'intl';
}

