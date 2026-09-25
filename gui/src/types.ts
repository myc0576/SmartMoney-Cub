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
  currency?: string;
  account_id?: string;
  position_side?: 'LONG' | 'SHORT';
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
  agent_id?: string | null;
  agent_preset_id?: string | null;
  agent_adapter?: string | null;
  agent_mode?: string | null;
  agent_version?: string | null;
  status: string;
  forked_from: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReviewFromTradeResponse {
  status: string;
  session: SessionSummary;
  round_trip_id: string;
  prompt: string;
  safety: string;
}

export interface ReviewAgent {
  agent_id: string;
  display_name: string;
  kind: string;
  detected: boolean;
  enabled: boolean;
  status: string;
  version?: string | null;
  detail?: string;
  capabilities?: Record<string, boolean>;
  protocol?: { name?: string; version?: number; compatible?: boolean };
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
  /**
   * Whether this source can actually be reached from here.
   *
   * The catalogue lists sources that are configured, not sources that answer:
   * two of the four built-in ones are unreachable from some networks. A picker
   * that offers them as ordinary choices turns a network fact into a mystery
   * failure, so the state and its reason travel with the entry.
   */
  availability?: 'available' | 'unavailable' | 'restricted' | string;
  availability_reason?: string;
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
  currency?: string;
  instrument_id?: string;
  position_side?: 'LONG' | 'SHORT';
  fees_known?: boolean;
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
  /**
   * The invalidation price the position was opened with.
   *
   * The journal stores it per fill and the round trip carries the first leg's
   * value forward, so it is often null on old rows. A null here is a fact about
   * the record, not a zero: the plan-versus-actual panel says 未记录 rather than
   * printing a stop the trader never set.
   */
  invalidation_price?: number | null;
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
  dimension?: string;
  key?: string;
  defined?: boolean;
  has_journal_data?: boolean;
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
  /** Older persisted runs contain a spec, metrics and curve but no trade ledger. */
  historical_summary?: boolean;
}

export interface ReplaySession extends SafetyEnvelope {
  session_id: string;
  mode: 'review' | 'training';
  parent_session_id?: string | null;
  account_id?: string | null;
  symbol: string;
  interval: string;
  provider: string;
  provider_id?: string;
  source?: string;
  source_quality?: string;
  fetched_at?: string;
  historical_evidence?: string;
  warnings?: string[];
  provenance?: Record<string, unknown>;
  start_time?: string;
  end_time?: string;
  cursor: number;
  bar_count: number;
  bars: MarketBar[];
  markers: ReplayMarker[];
  unmatched_marker_count?: number;
  training?: ReplayTraining | null;
  notes?: string;
  created_at: string;
}

/** A trade annotation drawn on the replay chart. */
export interface ReplayMarker {
  marker_id?: string;
  trade_id?: string;
  index?: number;
  time: string;
  price: number;
  kind: string;
  side?: string;
  quantity?: number;
  account_id?: string;
  time_precision?: string;
  label?: string;
}

export interface ReplayTraining {
  branch_id: string;
  initial_cash: number;
  cash: number;
  position?: number;
  positions: { symbol: string; quantity: number }[];
  orders: {
    order_id: string;
    submitted_index: number;
    side: string;
    quantity: number;
    status: string;
    reason?: string;
  }[];
  fills: {
    order_id: string;
    index: number;
    time: string;
    side: string;
    quantity: number;
    price: number;
    simulated_only: true;
  }[];
  currency: string;
  fill_policy: string;
  cost_model: string;
  simulated_only: true;
}

export interface ReplaySessions extends SafetyEnvelope {
  sessions: ReplaySession[];
}

// ---- read-only connections ----------------------------------------------

export interface ConnectionManifest {
  schema: string;
  provider_id: string;
  name: string;
  description: string;
  official_links: { label: string; url: string }[];
  auth: {
    mode: string;
    fields: Array<string | { name: string; label?: string; required?: boolean; secret?: boolean }>;
    secret_storage: string;
    read_only: boolean;
    scope: string;
    notes?: string;
  };
  supported_assets: string[];
  capabilities: string[];
  history: { start?: string | null; end?: string | null; precision?: string; timezones?: string[] };
  validation: { status: string; checked_at?: string | null; issues: string[] };
  safety: string;
}

export interface ConnectionAccount {
  account_id: string;
  display_name: string;
  provider: string;
  asset_class: string;
  currency: string;
  permissions: string[];
  status: string;
}

export interface ConnectionSyncResult {
  provider_id: string;
  cursor?: string | null;
  events: number | NormalizedEvent[];
  positions: number | ConnectionPosition[];
  duplicate_count: number;
  updated_count: number;
  partial: boolean;
  errors: string[];
  attempts: number;
  disconnected: boolean;
  safety: string;
}

export interface NormalizedEvent {
  external_id: string;
  revision?: string | number;
  account_id: string;
  asset: string;
  symbol: string;
  event_type: string;
  side?: string;
  quantity?: number;
  price?: number;
  currency?: string;
  fee?: number;
  occurred_at?: string;
  available_at?: string;
  data_quality: string;
  source: string;
  metadata?: Record<string, unknown>;
  safety: string;
}

export interface ConnectionPosition {
  account_id: string;
  asset: string;
  symbol: string;
  quantity: number;
  average_price?: number;
  market_value?: number;
  currency: string;
  as_of?: string;
  data_quality: string;
  source: string;
  safety: string;
}

export interface ConnectionsResponse extends SafetyEnvelope {
  manifests: ConnectionManifest[];
  accounts: ConnectionAccount[];
  sync?: ConnectionSyncResult[];
  statuses?: ConnectionStatus[];
}

export interface ConnectionStatus {
  partial?: boolean;
  errors?: string[];
  watch_active?: boolean;
  remote_revocation_pending?: boolean;
  provider_id: string;
  connected: boolean;
  revoked: boolean;
  credential_fields: string[];
  credential_values: Record<string, string>;
  cursor?: string | null;
  event_count?: number;
  scope?: {
    allowed?: boolean;
    status?: 'missing' | 'unverified' | 'verified' | 'denied' | string;
    required?: string[];
    granted?: string[];
    missing?: string[];
    issues?: string[];
    safety?: string;
  } | null;
  safety: string;
}

export interface Preferences {
  locale: string;
  timezone: string;
  currency: string;
  number_format: string;
  color_scheme: 'cn' | 'intl';
  theme: 'light' | 'dark';
}

/* ---- plugin marketplace (real install channel) ---------------------- */

/** How a curated project is obtained. The installer switches on this value. */
export interface PluginInstallSpec {
  kind: 'pypi' | 'git' | 'builtin';
  /** pypi: the distribution name to install. */
  package?: string;
  /** pypi/git: the import name the health check verifies. */
  module?: string;
  /** pypi: optional pinned version. */
  version?: string | null;
  /** git: the upstream repository URL. */
  repo?: string;
  /** git: optional branch or tag. */
  tag?: string | null;
  /** builtin: what ships with the harness. */
  note?: string;
}

/**
 * Lifecycle state of a market entry. Only INSTALLED and ENABLED mean code
 * exists on this machine and passed its health check; there is no
 * half-configured state because an interrupted wizard writes nothing.
 */
export type PluginMarketState =
  | 'AVAILABLE'
  | 'INSTALLED'
  | 'ENABLED'
  | 'DISABLED'
  | 'ERROR';

export interface PluginMarketEntry {
  plugin_id: string;
  name: string;
  category: string;
  description: string;
  repo: string;
  docs_url?: string | null;
  install: PluginInstallSpec;
  license: string;
  level: string;
  capabilities: string[];
  requires_credentials: boolean;
  credential_mode?: 'none' | 'managed_local' | 'external_only';
  credential_setup_url?: string | null;
  credential_requirements?: PluginCredentialRequirement[];
  network_required: boolean;
  execution_risk: string;
  boundary: string;
  source: string;
  safety: string;
  /** The command a user would run themselves to install this upstream project. */
  manual_command: string;
  state: PluginMarketState;
  installed: boolean;
  enabled: boolean;
  mounted: boolean;
  health?: string | null;
  last_error?: string | null;
  updated_at?: string | null;
}

export interface PluginCredentialRequirement {
  name: string;
  label: string;
  obtain_url: string;
  help: string;
  required: boolean;
  scopes: string[];
}

export interface PluginMarketResponse extends SafetyEnvelope {
  schema: string;
  source: string;
  categories: string[];
  catalog: PluginMarketEntry[];
  counts: {
    total: number;
    by_category: Record<string, number>;
    by_install_kind: Record<string, number>;
  };
  policy: string;
}

export interface PluginInstallRequest {
  plugin_id: string;
  permissions_confirmed: boolean;
  /** Written to the local credentials file; never returned by the API. */
  credentials?: Record<string, string>;
  config?: Record<string, unknown>;
}

export interface PluginInstallStep {
  step: string;
  status: 'ok' | 'failed' | 'skipped';
  detail: string;
}

export interface PluginInstallResponse extends SafetyEnvelope {
  status: 'ok' | 'error';
  plugin?: PluginMarketEntry;
  steps: PluginInstallStep[];
  health?: { ok: boolean; detail: string };
  error?: string;
}

export interface PluginProbeResponse extends SafetyEnvelope {
  status: string;
  healthy: boolean;
  detail: string;
  module?: string;
  interpreter?: string;
}

export interface PluginUninstallResponse extends SafetyEnvelope {
  status: 'ok' | 'error';
  plugin_id: string;
  removed_path?: string;
  error?: string;
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

// ---- insight: repeated mistakes and the edges that pay ----------------

/** How one mistake cluster was found: the field, the comparison, and the value. */
export interface InsightEvidence {
  field: string;
  comparator: string;
  threshold: string | number;
  observed: string | number;
}

/**
 * The non-silent observation envelope every insight row carries.
 *
 * The repository contract requires an observation to state how it would be
 * invalidated, when it expires, where the data came from, when that data was
 * available, and how good it is. A row that cannot answer one of these says so
 * instead of leaving the field out, because a missing answer reads as "none".
 */
export interface InsightObservation {
  invalidation: string;
  time_stop: string;
  give_up: string;
  data_source: string;
  available_at: string;
  data_quality: string;
}

export interface MistakeCluster extends InsightObservation {
  cluster_id: string;
  kind: string;
  /** The readable name for this trigger. */
  label: string;
  /**
   * The fills that triggered the cluster. These are the evidence: the trigger
   * fires on an execution, so the execution is what proves it fired.
   */
  trade_ids: string[];
  /**
   * The closed round trips those fills belong to.
   *
   * Sent beside the fill ids because the two answer different questions: the
   * fills are why the cluster exists, and the round trip is what the detail
   * route can open. A caller that navigated by fill id would ask for a record
   * the route cannot fetch.
   */
  round_trip_ids?: string[];
  count: number;
  net_pnl: number;
  avg_return_pct: number;
  first_at: string;
  last_at: string;
  evidence: InsightEvidence[];
}

export interface InsightTrigger {
  kind: string;
  label: string;
  matched: number;
  skipped_reason?: string;
}

export interface MistakeResponse extends SafetyEnvelope {
  status: string;
  count: number;
  rows: MistakeCluster[];
  /**
   * Which deterministic triggers were evaluated, including the ones that found
   * nothing. A trigger that produced no cluster is a fact about the journal, and
   * a reader who cannot see it cannot tell a clean book from an unchecked one.
   */
  triggers?: InsightTrigger[];
  clusters?: MistakeCluster[];
}

export interface EdgeRow extends InsightObservation {
  edge_id: string;
  dimension: string;
  key: string;
  name?: string;
  trade_count: number;
  win_rate: number;
  net_pnl: number;
  avg_return_pct: number;
  profit_factor: number | null;
  small_sample: boolean;
}

export interface EdgeResponse extends SafetyEnvelope {
  status: string;
  count: number;
  rows: EdgeRow[];
  dimensions?: string[];
  edges?: EdgeRow[];
}

export interface PatternCandidate extends InsightObservation {
  pattern_id: string;
  round_trip_id?: string;
  account_id?: string;
  axis: string;
  label: string;
  original_label?: string;
  status: 'observed' | 'inferred' | 'confirmed' | 'rejected' | string;
  confidence: string;
  evidence: Array<Record<string, unknown>>;
  trade_ids: string[];
  missing_data: string[];
  version: string;
  decision?: { state?: string; label?: string; playbook_id?: string | null; updated_at?: string };
}

export interface PatternProfile {
  sample_count: number;
  account_count: number;
  axes: Record<string, { counts: Record<string, number>; dominant?: string | null; label?: string }>;
  data_quality: string;
  limitations: string[];
}

export interface InsightPatternsResponse extends SafetyEnvelope {
  status: string;
  profile: PatternProfile;
  candidates: PatternCandidate[];
  version: string;
  filters?: Record<string, unknown>;
  truncated?: boolean;
}
