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
  /** Aggregate fee the extractor reconciled from the broker's fee columns. */
  fee?: number | null;
  /** Free-text rationale the broker export carried, when it had one. */
  thesis?: string | null;
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

export interface RuleRecord {
  rule_id: string;
  family: string | null;
  title: string | null;
  status: string;
  metrics: Record<string, unknown>;
  promotion_note: string | null;
  promoted_at: string | null;
  updated_at: string;
  /**
   * Why this rule cannot be recommended for promotion yet, computed by the same
   * threshold check the rest of the product uses. Absent on a rule read before
   * the field existed, so callers must treat it as optional.
   */
  promotion_blockers?: string[];
}

/**
 * One reasoning level a model advertises.
 *
 * The level is the wire value; the label is what the picker shows. Learning
 * this from DSH: a level without a human name reads as a raw enum, and a level
 * without a description leaves the user guessing what "xhigh" buys them.
 */
export interface ReasoningEffort {
  level: string;
  label: string;
  description?: string;
  is_default?: boolean;
}

export interface ModelEntry {
  id: string;
  label: string;
  reasoning_efforts: string[];
  default_effort: string;
  /** Richer effort rows. Falls back to reasoning_efforts when absent. */
  effort_details?: ReasoningEffort[];
  context_window?: number;
  max_tokens?: number;
  description?: string;
  input_modalities?: string[];
  /** True when the provider no longer publishes this id. Shown, never hidden. */
  stale?: boolean;
  /** True when the id was confirmed against the live endpoint. */
  verified?: boolean;
}

/**
 * How the API-key state should be drawn.
 *
 * DSH draws a solid green dot only when it can confirm a key is configured, a
 * red dot only when it can confirm a named reference is missing, and no dot
 * when it cannot tell. Reusing that rule keeps us from implying a broken
 * provider when we simply do not know.
 */
export type KeyStatus = 'configured' | 'missing' | 'unknown';

export interface ProviderView {
  provider_id: string;
  label: string;
  portal_url?: string;
  base_url: string;
  protocol: string;
  protocol_label?: string;
  default_model: string;
  models: ModelEntry[];
  reasoning_efforts: string[];
  requires_key: boolean;
  removable: boolean;
  installable: boolean;
  has_key: boolean;
  key_source: string;
  description: string;
  incomplete?: boolean;
  key_status?: KeyStatus;
  /** True when this provider's profile was hand-declared rather than catalog. */
  is_custom?: boolean;
  /** True when the route is usable right now (key present and endpoint set). */
  routable?: boolean;
  models_checked_at?: string;
  /** Set when the last model lookup failed; the row still renders. */
  models_error?: string;
}

export interface CatalogEntry {
  provider_id: string;
  label: string;
  portal_url?: string;
  base_url: string;
  protocol: string;
  protocol_label: string;
  description: string;
  installed: boolean;
  has_env_key: boolean;
  models: ModelEntry[];
}

export interface ProtocolOption {
  id: string;
  label: string;
}

export interface DefaultSelection {
  provider_id: string;
  model: string;
  reasoning: string;
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

export interface ReviewScopeResponse {
  status: string;
  phase: string;
  confirmed: boolean;
  envelope: {
    schema: string;
    scope: Record<string, unknown>;
    payload: Record<string, unknown>;
    payload_sha256: string;
    redaction_policy: string;
    sent_keys: string[];
    safety: string;
  };
  safety: string;
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
  default_model: string;
  default_reasoning: string;
  store_counts: Record<string, number>;
  trend_color_scheme: 'cn' | 'intl';
}

/* ---- trader product ------------------------------------------------- */

/**
 * The execution ban, carried on every trader response.
 *
 * Modelled as a field rather than a base interface so an omitting response is
 * a type error at the call site rather than a silent gap. The server is the
 * authority: these types describe what it sends, they do not assert it.
 */
export interface SafetyEnvelope {
  safety: string;
}

export interface TraderHealth extends SafetyEnvelope {
  status: string;
  mode: string;
  store: string;
  market_data_mode: string;
  tenant_mode: string;
}

export interface TraderMeta extends SafetyEnvelope {
  app: string;
  version: string;
  schema: string;
  mode: string;
  tenant_mode: string;
  market_data_mode: string;
  currencies: string[];
  intervals: string[];
  dimensions: string[];
  playbook_fields: string[];
  backtest_dsl_version: number;
  /** The resolved identity the route serves: the shell names the local ledger
   *  and its mode from here. Optional because the route sends it and a caller
   *  that reads only the version should not fall over when it is absent. */
  tenant?: TraderTenant;
  auth_mode?: string;
  storage_engine?: string;
  capabilities?: string[];
}

/** The identity one trader request was served under. */
export interface TraderTenant {
  user_id: string;
  tenant_id: string;
  display_name: string;
  mode: string;
}

export interface MarketProvider {
  provider_id: string;
  label: string;
  markets: string[];
  requires_key: boolean;
  source_quality: string;
  description: string;
}

export interface MarketProviders extends SafetyEnvelope {
  providers: MarketProvider[];
}

export interface MarketBar {
  symbol: string;
  interval: string;
  open_time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface MarketBars extends SafetyEnvelope {
  provider_id: string;
  symbol: string;
  interval: string;
  fetched_at: string;
  source_quality: string;
  warnings: string[];
  bars: MarketBar[];
}

/**
 * One row of the journal, as `/api/trader/trades` returns it.
 *
 * One interface rather than two, deliberately. The endpoint is the only list
 * route, and the detail route is addressed by round trip id, so a row may be
 * addressed as either. Modelling both id fields as optional keeps a single
 * shape that a caller can render whichever the store filled in, instead of two
 * incompatible readings of the same URL.
 *
 * A field is optional when the store may legitimately not have it: an unpaired
 * execution has no exit, and a partially reviewed row has no tags.
 */
export interface TradeLogEntry {
  trade_id?: string;
  round_trip_id?: string;
  account_id?: string;
  symbol: string;
  name?: string;
  side?: string;
  entry_time?: string;
  exit_time?: string;
  entry_price?: number;
  exit_price?: number;
  trade_date?: string;
  trade_time?: string;
  price?: number;
  quantity: number;
  net_pnl?: number;
  return_pct?: number;
  fee?: number;
  fees?: number;
  holding_days?: number;
  regime?: string;
  tags?: string[];
  thesis?: string;
  created_at?: string;
  mae?: number | null;
  mfe?: number | null;
  /** The journal's detail route carries the buy lots a close was matched against. */
  matched_lots?: { entry_time: string; entry_price: number; quantity: number; buy_fee: number }[];
}

export interface TraderTrades extends SafetyEnvelope {
  trades: TradeLogEntry[];
  count: number;
  limit?: number;
  offset?: number;
  /**
   * The route returns the page's ledger beside the round trips: the fills
   * behind the matched trades, the executions that are still open, and the
   * review issues that touch them. Optional because a caller that only reads
   * the closed trades does not need them.
   */
  fills?: TradeLogEntry[];
  open_positions?: OpenPosition[];
  issues?: Issue[];
  ledger_status?: string;
}

/** The journal's import acknowledgement. It reports what was written rather than
 *  echoing the ledger, so a caller cannot mistake it for a trade list. */
export interface TraderImportResult extends SafetyEnvelope {
  format: string;
  submitted_count: number;
  inserted: string[];
  updated: string[];
  inserted_count: number;
  updated_count: number;
}

/** The highest precision the detail route returns for one journal row. */
export interface TradeLogDetail extends SafetyEnvelope {
  trade: TradeLogEntry;
  matched_lots?: { entry_time: string; entry_price: number; quantity: number; buy_fee: number }[];
}

export interface TraderAccount {
  account_id: string;
  name: string;
  broker: string;
  currency: string;
  initial_balance: number;
  created_at: string;
  updated_at: string;
}

export interface TraderAccounts extends SafetyEnvelope {
  accounts: TraderAccount[];
}

export interface TraderSummary extends SafetyEnvelope {
  trade_count: number;
  win_count: number;
  loss_count: number;
  flat_count: number;
  win_rate: number;
  profit_factor: number | null;
  profit_factor_note: string;
  total_net_pnl: number;
  total_fees: number;
  gross_profit?: number;
  gross_loss?: number;
  avg_return_pct: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  avg_holding_days: number;
  max_drawdown: number;
  open_position_count: number;
  sample_note: string;
  equity_curve: { exit_time: string; symbol: string; net_pnl: number; cumulative_pnl: number }[];
  /**
   * The ledger counts the summary route returns beside the metrics. The api
   * adapter lifts them onto the metrics it hands back, so the shell can report
   * how many executions the journal holds without a second request. Optional
   * because the metrics are what every other caller reads.
   */
  counts?: TraderLedgerCounts;
}

/** How many rows the summary route found behind one request. */
export interface TraderLedgerCounts {
  fills: number;
  round_trips: number;
  open_positions: number;
  errors: number;
  warnings: number;
}

/**
 * The body of GET /api/trader/analytics/summary as the server sends it.
 *
 * The metrics are nested under `summary`, beside the ledger counts and status.
 * The api adapter unwraps the nested object for callers (see `trader.summary`
 * in api.ts), which is why the interface is named for the envelope rather than
 * for the metrics a view reads.
 */
export interface TraderSummaryEnvelope extends SafetyEnvelope {
  status: string;
  summary: TraderSummary;
  counts: TraderLedgerCounts;
  ledger_status: string;
}

export interface BreakdownRow {
  key: string;
  name?: string;
  is_st?: boolean;
  trade_count: number;
  win_rate: number;
  net_pnl: number;
  avg_return_pct: number;
  profit_factor: number | null;
  small_sample: boolean;
}

export interface TraderBreakdown extends SafetyEnvelope {
  dimension: string;
  rows: BreakdownRow[];
}

/**
 * The body of GET /api/trader/analytics/breakdown when no dimension is named.
 *
 * The same route answers in two shapes depending on its argument: one named
 * dimension returns a flat `rows` list (see TraderBreakdown), while an unnamed
 * request groups every dimension at once under `breakdown`. A caller that shows
 * all the groups asks once here instead of one single-dimension request per
 * group, which is what the view this replaced used to do against the workbench.
 */
export interface TraderBreakdownMap extends SafetyEnvelope {
  dimension: string;
  breakdown: Record<string, BreakdownRow[]>;
  dimensions: string[];
}

export interface TraderCalendarDay {
  date: string;
  trade_count: number;
  net_pnl: number;
  win_count: number;
  trades: { round_trip_id: string; symbol: string; name?: string; net_pnl: number; return_pct: number }[];
}

export interface TraderCalendar extends SafetyEnvelope {
  year: number;
  month: number;
  days: TraderCalendarDay[];
}

export interface Playbook {
  playbook_id: string;
  name: string;
  description: string;
  setup: string;
  entry_rules: string[];
  exit_rules: string[];
  risk_rules: string[];
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface Playbooks extends SafetyEnvelope {
  playbooks: Playbook[];
  stats: Record<string, PlaybookStats>;
}

/** Per-playbook outcome, keyed by playbook name in Playbooks.stats. */
export interface PlaybookStats {
  trade_count: number;
  win_rate: number;
  net_pnl: number;
  avg_return_pct: number;
  profit_factor: number | null;
  small_sample: boolean;
}

export interface BacktestRunSummary {
  run_id: string;
  strategy_name: string;
  symbol: string;
  interval: string;
  started_at: string;
  created_at: string;
  metrics: Record<string, number | string | null>;
}

export interface BacktestRuns extends SafetyEnvelope {
  runs: BacktestRunSummary[];
}

export interface BacktestEquityPoint {
  index: number;
  open_time: string;
  equity: number;
  cash?: number;
  position?: number;
}

export interface BacktestTrade {
  symbol: string;
  side: string;
  quantity: number;
  entry_time: string;
  exit_time: string;
  entry_price: number;
  exit_price: number;
  pnl: number;
  return_pct?: number;
  exit_reason?: string;
  hold_bars?: number;
}

export interface BacktestRunDetail extends SafetyEnvelope {
  run_id: string;
  strategy_name: string;
  symbol: string;
  interval: string;
  started_at: string;
  spec: Record<string, unknown>;
  metrics: Record<string, number | string | null>;
  equity_curve: BacktestEquityPoint[];
  trades: BacktestTrade[];
  bar_count?: number;
  initial_cash?: number;
  final_equity?: number;
}

export interface ReplaySession extends SafetyEnvelope {
  session_id: string;
  symbol: string;
  interval: string;
  provider: string;
  start_time: string;
  end_time: string;
  cursor: number;
  bar_count: number;
  bars: MarketBar[];
  markers: ReplayMarker[];
  notes: string;
  created_at: string;
}

/** A trade annotation drawn on the replay chart. */
export interface ReplayMarker {
  marker_id?: string;
  time: string;
  price: number;
  kind: string;
  label?: string;
}

export interface ReplaySessions extends SafetyEnvelope {
  sessions: ReplaySession[];
}

/* ---- plugins & agent presets (DSH alignment) ------------------------ */

export interface PluginItem {
  plugin_id: string;
  name?: string;
  version: string;
  state: string;
  capabilities: string[];
  isolation: string;
  enabled?: boolean;
  required_services?: string[];
  optional_services?: string[];
  missing_services?: string[];
  last_error?: string | null;
  health?: Record<string, any> | null;
  manifest?: Record<string, any>;
}

export interface PluginDetailResponse extends SafetyEnvelope {
  status: string;
  plugin_id: string;
  plugin: PluginItem;
  manifest: Record<string, any>;
  config: Record<string, any>;
  events: {
    id: number;
    plugin_id: string;
    from_state: string | null;
    to_state: string;
    detail: string;
    created_at: string;
    safety?: string;
  }[];
}

export interface PluginCatalogEntry {
  project: string;
  repo: string;
  level: string;
  capabilities: string[];
  license: string;
  maintained: string;
  boundary: string;
  network_required: boolean;
  execution_risk: string;
}

export interface PluginCatalogResponse extends SafetyEnvelope {
  schema: string;
  levels: string[];
  entries: PluginCatalogEntry[];
  by_level: Record<string, PluginCatalogEntry[]>;
  counts: Record<string, number>;
  policy: string;
  curated_finance?: {
    schema: string;
    plugins: CuratedFinancePlugin[];
    safety: string;
  };
}

export interface CuratedFinancePlugin {
  id: string;
  name: string;
  version: string;
  source: string;
  commit: string;
  license: string;
  declared_network: boolean;
  capabilities: string[];
  permissions: string[];
  installed: boolean;
  enabled: boolean;
  update: Record<string, any>;
  health: Record<string, any>;
  profile_reload: Record<string, any>;
  safety: string;
}

export interface AgentPresets {
  system_prompt: string;
  default_effort: string;
  context_strategy: string;
}


// ==================== Jev Reasoning Engine Types ====================

export interface JevBackendHealth {
  status: string;
  available: boolean;
  backend_id: string;
  provider_id: string;
  model_requested: string;
  model_resolved: string | null;
  reason?: string;
  safety: string;
}

export interface JevStatusResponse extends SafetyEnvelope {
  engine: string;
  provider_id: string;
  model_requested: string;
  model_resolved: string | null;
  available: boolean;
  reason?: string | null;
  detail?: any;
  backends?: Record<string, JevBackendHealth>;
}

export interface JevQuestionDef {
  question_id: string;
  kind: 'choice' | 'scale' | string;
  prompt: string;
  choices?: string[];
  scale_min?: number | null;
  scale_max?: number | null;
}

export interface JevTrackInfo {
  track: string;
  question_count: number;
  case_count: number;
  questions?: JevQuestionDef[];
}

export interface JevTracksResponse extends SafetyEnvelope {
  tracks: JevTrackInfo[];
}

// ==================== Agent Integration Types ====================

export type AgentStatus = 'not_found' | 'detected' | 'configured' | 'healthy' | 'unavailable' | 'unsupported';

export interface AgentIntegration {
  agent_id: string;
  label: string;
  status: AgentStatus;
  config_path: string | null;
  detected_version: string | null;
  detail: string;
  owned_keys: string[];
}

export interface AgentsResponse extends SafetyEnvelope {
  agents: AgentIntegration[];
}

export interface AgentActionResponse extends SafetyEnvelope {
  agent: AgentIntegration;
}

// ==================== Benchmark Engine Types ====================

export interface BenchmarkMetric {
  schema_valid_rate: number;
  accuracy: number;
  macro_f1: number;
  recall: number;
  fpr: number;
  brier: number;
  ece: number;
  coverage: number;
  abstention_rate: number;
  selective_risk: number;
  stability: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  p99_latency_ms: number;
  cost_per_case: number;
  retry_rate: number;
  confidence_interval_95?: [number, number];
  mcnemar_against_baseline?: {
    statistic: number;
    p_value: number;
    b: number;
    c: number;
  };
}

export interface BenchmarkSystem {
  system_id: string;
  status: 'completed' | 'not_run' | string;
  model_requested?: string;
  model_resolved?: string | null;
  cost_usd?: number;
  latency_p50_ms?: number;
  reason?: string;
  metrics?: BenchmarkMetric | null;
  track_metrics?: Record<string, BenchmarkMetric>;
}

export interface BenchmarkImageItem {
  name: string;
  url: string;
}

export interface BenchmarkLatestResponse extends SafetyEnvelope {
  run_id: string | null;
  source?: 'local' | 'bundled';
  generated_at?: string;
  run_date?: string;
  benchmark_id?: string;
  mode?: string;
  sample_count?: number;
  git_sha?: string;
  run_hash?: string;
  tracks?: string[];
  systems?: BenchmarkSystem[];
  images?: BenchmarkImageItem[];
  image_urls?: Record<string, string>;
}
