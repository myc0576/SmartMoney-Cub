import { shellCopy } from './locales/shell';
import { useCallback, useSyncExternalStore } from 'react';

export const LOCALES = ['zh-CN', 'en-US', 'zh-TW', 'ja-JP', 'ko-KR', 'es-ES', 'pt-BR', 'de-DE', 'fr-FR'] as const;
export type Locale = typeof LOCALES[number];

export const LOCALE_LABELS: Record<Locale, string> = {
  'zh-CN': '简体中文', 'en-US': 'English', 'zh-TW': '繁體中文', 'ja-JP': '日本語',
  'ko-KR': '한국어', 'es-ES': 'Español', 'pt-BR': 'Português', 'de-DE': 'Deutsch', 'fr-FR': 'Français',
};

type Params = Record<string, string | number>;

const zh = {
  'nav.review': '复盘', 'nav.research': '研究', 'nav.strategy': '策略',
  'nav.overview': '总览', 'nav.trades': '交易日志', 'nav.calendar': '复盘日历',
  'nav.reports': '报告', 'nav.insight': '洞察', 'nav.lab': '策略实验室',
  'nav.drill': '演练', 'nav.settings': '设置', 'nav.connections': '连接',
  'nav.import': '数据导入',
  'hint.overview': '今天要关注什么', 'hint.trades': '平仓交易与未配对持仓',
  'hint.calendar': '按日查看盈亏', 'hint.reports': '绩效、风险、标的与归因',
  'hint.insight': '证据支持的重复模式', 'hint.lab': 'Playbook、规则库与回测',
  'hint.drill': '真实成交回放与模拟训练', 'hint.settings': '模型、插件、诊断与隐私',
  'hint.connections': '只读同步外部成交与持仓', 'hint.import': 'Excel / CSV / PDF / 截图',
  'app.local': '本地复盘工作台', 'app.localLedger': '本地账本', 'app.offline': '全部数据离线保存',
  'top.account': '账户范围', 'top.allAccounts': '全部账户', 'top.sync': '同步',
  'top.import': '导入', 'top.preferences': '偏好', 'top.assistant.open': '打开助手',
  'top.assistant.close': '收起助手', 'top.lastSync': '仅本地台账',
  'prefs.title': '显示偏好', 'prefs.locale': '语言', 'prefs.timezone': '时区',
  'prefs.theme': '主题', 'prefs.theme.dark': '深色', 'prefs.theme.light': '浅色',
  'prefs.scheme': '涨跌配色', 'prefs.scheme.cn': '红涨绿跌', 'prefs.scheme.intl': '绿涨红跌',
  'prefs.currency': '显示币种', 'prefs.save': '应用', 'prefs.close': '关闭',
  'state.loading': '加载中…', 'state.retry': '重试', 'state.unavailable': '当前环境未开放该服务',
  'state.empty': '暂无数据', 'state.forbidden': '当前环境未开放此服务（403）',
  'connection.title': '只读连接', 'connection.subtitle': '同步你已有的成交与持仓，不获取下单或改账户权限。',
  'connection.available': '可配置', 'connection.connected': '已连接', 'connection.unknown': '权限未知',
  'connection.readOnly': '只读', 'connection.openOfficial': '打开官方设置',
  'connection.refresh': '刷新', 'connection.noRoutes': '连接服务尚未启用。核心离线台账仍可正常使用。',
  'replay.review': '真实交易回放', 'replay.training': '模拟训练',
  'replay.start': '开始回放', 'replay.step': '下一根', 'replay.back': '回退分支',
  'replay.play': '播放', 'replay.pause': '暂停', 'replay.history': '历史会话',
  'replay.simulated': '仅模拟，不会发送到任何交易通道',
  'insight.patterns': '模式画像', 'insight.mistakes': '重复错误', 'insight.edges': 'Edge 库',
  'insight.confirm': '确认', 'insight.reject': '否决', 'insight.rename': '重命名',
  'insight.evidence': '证据', 'insight.limitations': '数据限制', 'insight.unknown': '未知',
  'action.cancel': '取消', 'action.save': '保存', 'action.close': '关闭',
  'error.service': '无法连接本地复盘服务', 'error.read': '读取失败',
} as const;

const translations: Record<Locale, Record<keyof typeof zh, string>> = {
  'zh-CN': zh,
  'en-US': {
    'nav.review':'Review','nav.research':'Research','nav.strategy':'Strategy','nav.overview':'Overview','nav.trades':'Trade log','nav.calendar':'Calendar','nav.reports':'Reports','nav.insight':'Insights','nav.lab':'Strategy lab','nav.drill':'Replay','nav.settings':'Settings','nav.connections':'Connections','nav.import':'Import',
    'hint.overview':'What needs attention today','hint.trades':'Closed trades and open lots','hint.calendar':'Review P&L by day','hint.reports':'Performance, risk and attribution','hint.insight':'Evidence-backed recurring patterns','hint.lab':'Playbooks, rules and backtests','hint.drill':'Actual-trade replay and simulation','hint.settings':'Models, plugins, diagnostics and privacy','hint.connections':'Read-only sync of executions and positions','hint.import':'Excel / CSV / PDF / screenshot',
    'app.local':'Local review workspace','app.localLedger':'Local ledger','app.offline':'All data stays offline','top.account':'Account scope','top.allAccounts':'All accounts','top.sync':'Sync','top.import':'Import','top.preferences':'Preferences','top.assistant.open':'Open assistant','top.assistant.close':'Hide assistant','top.lastSync':'Local ledger only',
    'prefs.title':'Display preferences','prefs.locale':'Language','prefs.timezone':'Time zone','prefs.theme':'Theme','prefs.theme.dark':'Dark','prefs.theme.light':'Light','prefs.scheme':'Gain/loss colors','prefs.scheme.cn':'Red gains','prefs.scheme.intl':'Green gains','prefs.currency':'Display currency','prefs.save':'Apply','prefs.close':'Close',
    'state.loading':'Loading…','state.retry':'Retry','state.unavailable':'This service is unavailable in this environment','state.empty':'No data','state.forbidden':'This service is unavailable here (403)',
    'connection.title':'Read-only connections','connection.subtitle':'Sync existing executions and positions without order or account permissions.','connection.available':'Available','connection.connected':'Connected','connection.unknown':'Permissions unknown','connection.readOnly':'Read only','connection.openOfficial':'Open official setup','connection.refresh':'Refresh','connection.noRoutes':'Connections are not enabled. The offline journal remains available.',
    'replay.review':'Actual-trade replay','replay.training':'Simulation training','replay.start':'Start replay','replay.step':'Next bar','replay.back':'Rewind branch','replay.play':'Play','replay.pause':'Pause','replay.history':'Session history','replay.simulated':'Simulation only; nothing is sent to a trading venue',
    'insight.patterns':'Pattern profile','insight.mistakes':'Repeated mistakes','insight.edges':'Edge library','insight.confirm':'Confirm','insight.reject':'Reject','insight.rename':'Rename','insight.evidence':'Evidence','insight.limitations':'Data limitations','insight.unknown':'Unknown',
    'action.cancel':'Cancel','action.save':'Save','action.close':'Close','error.service':'Cannot reach the local review service','error.read':'Read failed',
  },
  'zh-TW': {
    ...shellCopy['zh-TW'], 'nav.research':'研究', 'nav.strategy':'策略', 'nav.overview':'總覽', 'nav.review':'複盤','nav.trades':'交易日誌','nav.calendar':'複盤日曆','nav.reports':'報告','nav.insight':'洞察','nav.lab':'策略實驗室','nav.drill':'演練','nav.settings':'設定','nav.connections':'連線','nav.import':'資料匯入','app.local':'本地複盤工作台','app.localLedger':'本地帳本','top.account':'帳戶範圍','top.allAccounts':'全部帳戶','top.sync':'同步','top.import':'匯入','top.preferences':'偏好','top.assistant.open':'開啟助手','top.assistant.close':'收起助手','prefs.title':'顯示偏好','prefs.locale':'語言','prefs.timezone':'時區','prefs.theme':'主題','prefs.scheme':'漲跌配色','state.loading':'載入中…','state.retry':'重試','state.empty':'暫無資料','connection.title':'唯讀連線','connection.subtitle':'同步既有成交與持倉，不取得下單或修改帳戶權限。','connection.openOfficial':'開啟官方設定','replay.review':'真實交易回放','replay.training':'模擬訓練','insight.patterns':'模式畫像','insight.mistakes':'重複錯誤','action.save':'儲存','error.service':'無法連線本地複盤服務',
  },
  'ja-JP': {
    ...shellCopy['ja-JP'], 'nav.review':'レビュー','nav.research':'分析','nav.strategy':'戦略','nav.overview':'概要','nav.trades':'取引履歴','nav.calendar':'カレンダー','nav.reports':'レポート','nav.insight':'インサイト','nav.lab':'戦略ラボ','nav.drill':'リプレイ','nav.settings':'設定','nav.connections':'接続','nav.import':'インポート','app.local':'ローカル取引レビュー','app.localLedger':'ローカル台帳','top.account':'口座範囲','top.allAccounts':'すべての口座','top.sync':'同期','top.import':'取込','top.preferences':'表示設定','top.assistant.open':'アシスタントを開く','top.assistant.close':'アシスタントを閉じる','prefs.title':'表示設定','prefs.locale':'言語','prefs.timezone':'タイムゾーン','prefs.theme':'テーマ','prefs.scheme':'騰落色','state.loading':'読み込み中…','state.retry':'再試行','state.empty':'データなし','connection.title':'読み取り専用接続','connection.subtitle':'注文・口座変更権限なしで既存の約定とポジションを同期します。','connection.openOfficial':'公式設定を開く','replay.review':'実取引リプレイ','replay.training':'シミュレーション','insight.patterns':'パターン分析','insight.mistakes':'反復ミス','action.save':'保存','error.service':'ローカルサービスに接続できません',
  },
  'ko-KR': {
    ...shellCopy['ko-KR'], 'nav.review':'복기','nav.research':'분석','nav.strategy':'전략','nav.overview':'개요','nav.trades':'거래 일지','nav.calendar':'캘린더','nav.reports':'보고서','nav.insight':'인사이트','nav.lab':'전략 연구실','nav.drill':'리플레이','nav.settings':'설정','nav.connections':'연결','nav.import':'가져오기','app.local':'로컬 거래 복기','app.localLedger':'로컬 원장','top.account':'계좌 범위','top.allAccounts':'모든 계좌','top.sync':'동기화','top.import':'가져오기','top.preferences':'환경설정','top.assistant.open':'도우미 열기','top.assistant.close':'도우미 닫기','prefs.title':'표시 환경설정','prefs.locale':'언어','prefs.timezone':'시간대','prefs.theme':'테마','prefs.scheme':'상승/하락 색상','state.loading':'불러오는 중…','state.retry':'다시 시도','state.empty':'데이터 없음','connection.title':'읽기 전용 연결','connection.subtitle':'주문 또는 계좌 변경 권한 없이 기존 거래와 포지션을 동기화합니다.','connection.openOfficial':'공식 설정 열기','replay.review':'실거래 리플레이','replay.training':'모의 훈련','insight.patterns':'패턴 프로필','insight.mistakes':'반복 실수','action.save':'저장','error.service':'로컬 서비스에 연결할 수 없습니다',
  },
  'es-ES': {
    ...shellCopy['es-ES'], 'nav.review':'Revisión','nav.research':'Análisis','nav.strategy':'Estrategia','nav.overview':'Resumen','nav.trades':'Diario','nav.calendar':'Calendario','nav.reports':'Informes','nav.insight':'Patrones','nav.lab':'Laboratorio','nav.drill':'Repetición','nav.settings':'Ajustes','nav.connections':'Conexiones','nav.import':'Importar','app.local':'Diario local','app.localLedger':'Libro local','top.account':'Ámbito de cuenta','top.allAccounts':'Todas las cuentas','top.sync':'Sincronizar','top.import':'Importar','top.preferences':'Preferencias','top.assistant.open':'Abrir asistente','top.assistant.close':'Ocultar asistente','prefs.title':'Preferencias de pantalla','prefs.locale':'Idioma','prefs.timezone':'Zona horaria','prefs.theme':'Tema','prefs.scheme':'Colores de ganancias','state.loading':'Cargando…','state.retry':'Reintentar','state.empty':'Sin datos','connection.title':'Conexiones de solo lectura','connection.subtitle':'Sincroniza operaciones y posiciones sin permisos de órdenes ni cambios de cuenta.','connection.openOfficial':'Abrir configuración oficial','replay.review':'Repetición real','replay.training':'Simulación','insight.patterns':'Perfil de patrones','insight.mistakes':'Errores repetidos','action.save':'Guardar','error.service':'No se puede conectar al servicio local',
  },
  'pt-BR': {
    ...shellCopy['pt-BR'], 'nav.review':'Revisão','nav.research':'Análise','nav.strategy':'Estratégia','nav.overview':'Visão geral','nav.trades':'Diário','nav.calendar':'Calendário','nav.reports':'Relatórios','nav.insight':'Padrões','nav.lab':'Laboratório','nav.drill':'Replay','nav.settings':'Configurações','nav.connections':'Conexões','nav.import':'Importar','app.local':'Diário local','app.localLedger':'Livro local','top.account':'Escopo da conta','top.allAccounts':'Todas as contas','top.sync':'Sincronizar','top.import':'Importar','top.preferences':'Preferências','top.assistant.open':'Abrir assistente','top.assistant.close':'Ocultar assistente','prefs.title':'Preferências de exibição','prefs.locale':'Idioma','prefs.timezone':'Fuso horário','prefs.theme':'Tema','prefs.scheme':'Cores de ganhos','state.loading':'Carregando…','state.retry':'Tentar novamente','state.empty':'Sem dados','connection.title':'Conexões somente leitura','connection.subtitle':'Sincronize execuções e posições sem permissão para ordens ou alterações de conta.','connection.openOfficial':'Abrir configuração oficial','replay.review':'Replay real','replay.training':'Simulação','insight.patterns':'Perfil de padrões','insight.mistakes':'Erros repetidos','action.save':'Salvar','error.service':'Não foi possível conectar ao serviço local',
  },
  'de-DE': {
    ...shellCopy['de-DE'], 'nav.review':'Auswertung','nav.research':'Analyse','nav.strategy':'Strategie','nav.overview':'Übersicht','nav.trades':'Handelsjournal','nav.calendar':'Kalender','nav.reports':'Berichte','nav.insight':'Muster','nav.lab':'Strategielabor','nav.drill':'Replay','nav.settings':'Einstellungen','nav.connections':'Verbindungen','nav.import':'Import','app.local':'Lokales Handelsjournal','app.localLedger':'Lokales Journal','top.account':'Kontoumfang','top.allAccounts':'Alle Konten','top.sync':'Synchronisieren','top.import':'Import','top.preferences':'Darstellung','top.assistant.open':'Assistent öffnen','top.assistant.close':'Assistent schließen','prefs.title':'Anzeigeeinstellungen','prefs.locale':'Sprache','prefs.timezone':'Zeitzone','prefs.theme':'Design','prefs.scheme':'Gewinnfarben','state.loading':'Wird geladen…','state.retry':'Erneut versuchen','state.empty':'Keine Daten','connection.title':'Schreibgeschützte Verbindungen','connection.subtitle':'Ausführungen und Positionen ohne Order- oder Kontorechte synchronisieren.','connection.openOfficial':'Offizielle Einrichtung öffnen','replay.review':'Echter Handels-Replay','replay.training':'Simulation','insight.patterns':'Musterprofil','insight.mistakes':'Wiederholte Fehler','action.save':'Speichern','error.service':'Lokaler Dienst nicht erreichbar',
  },
  'fr-FR': {
    ...shellCopy['fr-FR'], 'nav.review':'Revue','nav.research':'Analyse','nav.strategy':'Stratégie','nav.overview':'Vue d’ensemble','nav.trades':'Journal','nav.calendar':'Calendrier','nav.reports':'Rapports','nav.insight':'Schémas','nav.lab':'Laboratoire','nav.drill':'Relecture','nav.settings':'Réglages','nav.connections':'Connexions','nav.import':'Importer','app.local':'Journal local','app.localLedger':'Registre local','top.account':'Périmètre du compte','top.allAccounts':'Tous les comptes','top.sync':'Synchroniser','top.import':'Importer','top.preferences':'Préférences','top.assistant.open':'Ouvrir l’assistant','top.assistant.close':'Masquer l’assistant','prefs.title':'Préférences d’affichage','prefs.locale':'Langue','prefs.timezone':'Fuseau horaire','prefs.theme':'Thème','prefs.scheme':'Couleurs des gains','state.loading':'Chargement…','state.retry':'Réessayer','state.empty':'Aucune donnée','connection.title':'Connexions en lecture seule','connection.subtitle':'Synchronisez exécutions et positions sans droit d’ordre ni de modification de compte.','connection.openOfficial':'Ouvrir la configuration officielle','replay.review':'Relecture réelle','replay.training':'Simulation','insight.patterns':'Profil de schémas','insight.mistakes':'Erreurs répétées','action.save':'Enregistrer','error.service':'Impossible de joindre le service local',
  },
};

export type MessageKey = keyof typeof zh;

export function translate(key: MessageKey, locale = current, params: Params = {}): string {
  const template = translations[locale]?.[key] || translations['en-US'][key] || zh[key] || key;
  return Object.entries(params).reduce((text, [name, value]) => text.replaceAll('{' + name + '}', String(value)), template);
}

const STORAGE_KEY = 'smcub.locale';
let current: Locale = readLocale();
const listeners = new Set<() => void>();

function readLocale(): Locale {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return LOCALES.includes(value as Locale) ? value as Locale : 'zh-CN';
  } catch {
    return 'zh-CN';
  }
}

export function getLocale(): Locale { return current; }

export function setLocale(locale: Locale): void {
  if (current === locale) return;
  current = locale;
  try { window.localStorage.setItem(STORAGE_KEY, locale); } catch { /* preference is optional */ }
  document.documentElement.lang = locale;
  listeners.forEach((listener) => listener());
}

export function subscribeLocale(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useLocale(): [Locale, (locale: Locale) => void] {
  const locale = useSyncExternalStore(subscribeLocale, getLocale, () => 'zh-CN' as Locale);
  const change = useCallback((next: Locale) => setLocale(next), []);
  return [locale, change];
}

export function useI18n(): { locale: Locale; setLocale: (locale: Locale) => void; t: (key: MessageKey, params?: Params) => string } {
  const [locale, change] = useLocale();
  const t = useCallback((key: MessageKey, params?: Params) => translate(key, locale, params), [locale]);
  return { locale, setLocale: change, t };
}

export function formatter(locale = current): Intl.NumberFormat {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 2 });
}

export function formatNumber(value: number | null | undefined, locale = current, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  return new Intl.NumberFormat(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(Number(value));
}

export function formatMoney(value: number | null | undefined, locale = current, currency = 'USD', digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  try {
    return new Intl.NumberFormat(locale, { style: 'currency', currency, minimumFractionDigits: digits, maximumFractionDigits: digits }).format(Number(value));
  } catch {
    return formatNumber(value, locale, digits);
  }
}

export function formatPercent(value: number | null | undefined, locale = current, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  return new Intl.NumberFormat(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits, signDisplay: 'exceptZero' }).format(Number(value)) + '%';
}

export function formatDateTime(value: string | Date | null | undefined, locale = current, timeZone?: string): string {
  if (!value) return '—';
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) return formatDate(value, locale);
  const unzoned = typeof value === 'string' && !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  const date = value instanceof Date ? value : new Date(value.replace(' ', 'T') + (unzoned ? 'Z' : ''));
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short', timeZone: unzoned ? 'UTC' : (timeZone || preferredTimeZone()) }).format(date);
}

export function formatDate(value: string | Date | null | undefined, locale = current, timeZone?: string): string {
  if (!value) return '—';
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const date = new Date(value + 'T00:00:00Z');
    return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone: 'UTC' }).format(date);
  }
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone: timeZone || preferredTimeZone() }).format(date);
}

export function preferredTimeZone(): string | undefined {
  try {
    const value = window.localStorage.getItem('smcub.timezone');
    if (!value || value === 'local') return undefined;
    new Intl.DateTimeFormat('en-US', { timeZone: value });
    return value;
  } catch { return undefined; }
}

export function localeName(locale: Locale = current): string { return LOCALE_LABELS[locale]; }

document.documentElement.lang = current;
