export type ColorScheme = 'cn' | 'intl';
export type TabKey = 'workbench' | 'trades' | 'regime' | 'rules' | 'plugins' | 'workspace';

export interface TradeAnalysis {
  trade_id: string;
  symbol: string;
  name: string;
  regime: string;
  entry_time: string;
  entry_price: number;
  exit_time: string;
  exit_price: number;
  volume: number;
  return_pct: number;
  pnl_amount: number;
  max_adverse_excursion_pct: number;
  thesis: string;
  invalidation_price: number | null;
  discipline_score: number;
  health_grade: string;
  badge_color: string;
  violations: string[];
  critiques: string[];
  safety: string;
  holding_days?: number;
  cost_basis_assumed?: boolean;
}

export interface PortfolioSummary {
  total_trades: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  total_profit: number;
  total_loss: number;
  profit_loss_ratio: number;
  avg_discipline_score: number;
  total_violations: number;
  violation_categories: Record<string, number>;
  grade_tag: string;
  overall_grade: string;
}

export interface RegimeInfo {
  key: string;
  name: string;
  title: string;
  stage_order: number;
  sentiment_score: number;
  description: string;
  ladder_height_range: string;
  recommended_position: string;
  action_stance: string;
  maxims: string[];
  allowed_setups: string[];
  forbidden_actions: string[];
  color: string;
  badge_class: string;
}

export interface ChallengerReview {
  trade_id: string;
  persona: {
    name: string;
    motto: string;
    style: string;
  };
  critique_quote: string;
  verdict: string;
  cross_examination_questions: string[];
  proposed_rule?: {
    rule_id: string;
    family: string;
    title: string;
    condition: string;
    source_trade: string;
    status: string;
    tested_samples: number;
    target_samples: number;
  } | null;
  safety: string;
}

export interface RuleItem {
  rule_id: string;
  title: string;
  family?: string;
  description?: string;
  condition?: string;
  status: 'champion' | 'challenger';
  sample_count?: number;
  tested_samples?: number;
  target_samples?: number;
  win_rate_impact?: string;
  violation_rate?: string;
  promoted_at?: string;
  promotion_note?: string;
  avoided_loss_est?: string;
  created_at?: string;
  source_trade?: string;
}

export interface AppDataResponse {
  safety: string;
  data_origin: 'demo_fixture' | 'user_csv';
  needs_review: Array<{
    code: string;
    severity: string;
    symbol: string;
    fill_id: string;
    detail: string;
  }>;
  active_regime: string;
  active_profile?: string;
  regime_info: RegimeInfo;
  regime_phases: Record<string, RegimeInfo>;
  report: {
    summary: PortfolioSummary;
    analyzed_trades: TradeAnalysis[];
    data_origin: string;
    ledger_status: string;
    needs_review: any[];
    safety: string;
  };
  challenger_reviews: ChallengerReview[];
  rules: {
    champions: RuleItem[];
    challengers: RuleItem[];
    safety: string;
  };
}

export interface PluginItem {
  plugin_id: string;
  version: string;
  state: 'ACTIVE' | 'DISABLED' | 'PENDING' | 'FAILED' | 'BLOCKED' | 'REVOKED' | 'DISCOVERED';
  capabilities: string[];
  required_services: string[];
  optional_services: string[];
  missing_services: string[];
  isolation: string;
  blockers: string[];
  health?: any;
  last_error?: string | null;
  generation?: number;
  safety: string;
}

export interface PluginCatalogEntry {
  project: string;
  repo: string;
  level: 'companion' | 'adapter' | 'runtime-plugin';
  capabilities: string[];
  license: string;
  maintained: string;
  boundary: string;
  network_required: boolean;
  execution_risk: string;
  safety: string;
}

export interface ProfileItem {
  name: string;
  description: string;
  allow_network: boolean;
  allow_external_llm: boolean;
  allow_credentials: boolean;
  bundles: Array<{
    name: string;
    description: string;
    entries: any[];
  }>;
  entries: Array<{
    id: string;
    name: string;
    enabled: boolean;
    group: string;
    config: Record<string, any>;
    disabled_reason?: string | null;
  }>;
}
