import type { Locale } from '../i18n';

type InsightCopy = {
  tabs: { mistakes: string; edges: string; patterns: string };
  hints: { mistakes: string; edges: string; patterns: string };
  fields: Record<string, string>;
  values: Record<string, string>;
  statuses: Record<string, string>;
  qualities: Record<string, string>;
  evidence: Record<string, string>;
  dimensions: Record<string, string>;
  unknown: string;
  other: string;
  sample: string;
  evidenceCount: string;
  dataLimits: string;
  viewEvidence: string;
  hideEvidence: string;
  viewConditions: string;
  hideConditions: string;
  observations: string;
  confirmNote: string;
  noPatterns: string;
  noMistakes: string;
  noEdges: string;
  readFailed: string;
  retry: string;
  scanning: string;
};

const base: InsightCopy = {
  tabs: { mistakes: 'Repeated mistakes', edges: 'Edge library', patterns: 'Pattern profile' },
  hints: { mistakes: 'Recurring observable behavior, without guessing intent', edges: 'Historical groups are hypotheses to verify', patterns: 'Trading behavior inferred from recorded executions' },
  fields: { holding_horizon: 'Holding period', entry_shape: 'Entry style', sizing: 'Entry batches', tag: 'Tag', regime: 'Market regime', holding: 'Holding period', symbol: 'Instrument', weekday: 'Day of week', status: 'Status', confidence: 'Evidence strength', data_quality: 'Data quality', invalidation: 'Invalidation condition', time_stop: 'Time stop', give_up: 'Give-up condition', data_source: 'Data source', available_at: 'Data available at' },
  values: { overnight_short: 'Overnight short-term', swing: 'Swing hold', brief_intraday: 'Short intraday', intraday: 'Intraday', position: 'Position trade', single_entry_fill: 'Single entry', multiple_entry_fills: 'Staged entry', unknown_entry_shape: 'Entry style unclear', observed: 'Observed', inferred: 'Inferred candidate', confirmed: 'Confirmed label', rejected: 'Rejected', descriptive: 'Descriptive', high: 'High', medium: 'Medium', low: 'Low', unknown: 'Unknown', single_entry: 'Single entry', multiple_entry: 'Staged entry', trend: 'Trend following', breakout: 'Breakout', mean_reversion: 'Mean reversion' },
  statuses: { observed: 'Observed', inferred: 'Inferred candidate', confirmed: 'Confirmed label', rejected: 'Rejected' },
  qualities: { high: 'High', medium: 'Medium', low: 'Low', descriptive: 'Descriptive only', unknown: 'Unknown' },
  evidence: { eq: 'equals', gt: 'above', gte: 'at least', lt: 'below', lte: 'at most', ne: 'not equal to' },
  dimensions: { tag: 'Tag', regime: 'Market regime', holding: 'Holding period', symbol: 'Instrument', weekday: 'Day of week' },
  unknown: 'Unknown', other: 'Other', sample: 'Sample', evidenceCount: 'evidence items', dataLimits: 'Data limits', viewEvidence: 'View evidence', hideEvidence: 'Hide evidence', viewConditions: 'View observation conditions', hideConditions: 'Hide observation conditions', observations: 'Observation conditions', confirmNote: 'Confirmation changes a local label only. It does not turn an inference into a trading recommendation.', noPatterns: 'There are not enough recorded trades to form an interpretable pattern profile.', noMistakes: 'No clustered issues matched these deterministic checks. This does not prove there are no problems.', noEdges: 'No grouped performance patterns are available yet. More confirmed trades are needed.', readFailed: 'Insight data could not be read', retry: 'Retry', scanning: 'Scanning the journal…',
};

const localized: Record<Locale, Partial<InsightCopy>> = {
  'en-US': {},
  'zh-CN': { tabs: { mistakes: '重复错误', edges: '优势线索', patterns: '模式画像' }, hints: { mistakes: '只描述重复行为，不猜测情绪或动机', edges: '历史分组只是待验证假设', patterns: '从已记录成交推断交易行为' }, fields: { holding_horizon: '持仓周期', entry_shape: '建仓方式', sizing: '建仓批次', tag: '标签', regime: '市场状态', holding: '持仓周期', symbol: '标的', weekday: '星期', status: '状态', confidence: '证据支持度', data_quality: '数据质量', invalidation: '失效条件', time_stop: '时间止损', give_up: '放弃条件', data_source: '数据来源', available_at: '数据可用时间' }, values: { overnight_short: '隔夜短线', swing: '波段持仓', brief_intraday: '短线日内', intraday: '日内交易', position: '持仓型交易', single_entry_fill: '一次建仓', multiple_entry_fills: '分批建仓', unknown_entry_shape: '暂无法判断', observed: '已观察到', inferred: '推断候选', confirmed: '已确认标签', rejected: '已否决', descriptive: '仅作描述', high: '高', medium: '中', low: '低', unknown: '未知' }, statuses: { observed: '已观察到', inferred: '推断候选', confirmed: '已确认标签', rejected: '已否决' }, qualities: { high: '高', medium: '中', low: '低', descriptive: '仅作描述', unknown: '未知' }, evidence: { eq: '等于', gt: '高于', gte: '至少', lt: '低于', lte: '不超过', ne: '不等于' }, dimensions: { tag: '标签', regime: '市场状态', holding: '持仓周期', symbol: '标的', weekday: '星期' }, unknown: '未知', other: '其他', sample: '样本', evidenceCount: '条证据', dataLimits: '数据限制', viewEvidence: '查看证据', hideEvidence: '收起证据', viewConditions: '查看观察条件', hideConditions: '收起观察条件', observations: '观察条件', confirmNote: '确认只改变本地标签，不会把推断变成交易建议。', noPatterns: '当前成交不足以形成可解释的模式画像。', noMistakes: '确定性检查没有找到成簇问题。这不等于没有问题。', noEdges: '还没有可分组的表现模式，需要更多已确认成交。', readFailed: '洞察数据读取失败', retry: '重试', scanning: '正在扫描台账…' },
  'zh-TW': { tabs: { mistakes: '重複錯誤', edges: '優勢線索', patterns: '模式畫像' }, hints: { mistakes: '只描述重複行為，不猜測情緒或動機', edges: '歷史分組只是待驗證假設', patterns: '從已記錄成交推斷交易行為' } },
  'ja-JP': { tabs: { mistakes: '繰り返すミス', edges: '優位性の手がかり', patterns: 'パターン分析' }, hints: { mistakes: '意図を推測せず、繰り返す行動を記録', edges: '過去の分類は検証前の仮説', patterns: '記録された約定から取引行動を推定' } },
  'ko-KR': { tabs: { mistakes: '반복 실수', edges: '강점 단서', patterns: '패턴 프로필' }, hints: { mistakes: '의도를 추측하지 않고 반복 행동을 기록', edges: '과거 그룹은 검증이 필요한 가설', patterns: '기록된 체결에서 거래 행동을 추정' } },
  'es-ES': { tabs: { mistakes: 'Errores repetidos', edges: 'Pistas de ventaja', patterns: 'Perfil de patrones' } },
  'pt-BR': { tabs: { mistakes: 'Erros repetidos', edges: 'Pistas de vantagem', patterns: 'Perfil de padrões' } },
  'de-DE': { tabs: { mistakes: 'Wiederholte Fehler', edges: 'Hinweise auf Vorteile', patterns: 'Musterprofil' } },
  'fr-FR': { tabs: { mistakes: 'Erreurs répétées', edges: 'Indices de force', patterns: 'Profil des schémas' } },
};

export function insightCopy(locale: Locale): InsightCopy {
  const copy = localized[locale] || {};
  return { ...base, ...copy, tabs: { ...base.tabs, ...copy.tabs }, hints: { ...base.hints, ...copy.hints }, fields: { ...base.fields, ...copy.fields }, values: { ...base.values, ...copy.values }, statuses: { ...base.statuses, ...copy.statuses }, qualities: { ...base.qualities, ...copy.qualities }, evidence: { ...base.evidence, ...copy.evidence }, dimensions: { ...base.dimensions, ...copy.dimensions } };
}

export function localizeInsightValue(value: unknown, copy: InsightCopy): string {
  if (value === null || value === undefined || value === '') return copy.unknown;
  const raw = String(value);
  if (copy.values[raw] || copy.statuses[raw] || copy.qualities[raw] || copy.dimensions[raw]) return copy.values[raw] || copy.statuses[raw] || copy.qualities[raw] || copy.dimensions[raw];
  return raw.includes('_') ? copy.other : raw;
}

export function localizeInsightField(value: unknown, copy: InsightCopy): string {
  if (value === null || value === undefined || value === '') return copy.unknown;
  return copy.fields[String(value)] || copy.dimensions[String(value)] || copy.other;
}

export function localizeEvidenceValue(value: unknown, copy: InsightCopy): string {
  if (value === null || value === undefined || value === '') return copy.unknown;
  return copy.values[String(value)] || copy.other;
}
