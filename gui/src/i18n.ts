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
  'nav.review': '复盘', 'nav.research': '研究', 'nav.strategy': '策略', 'nav.data': '数据',
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
  'overview.onboarding.kicker': '首次使用 · 3 步开启复盘闭环',
  'overview.onboarding.title': '台账暂无已确认成交，先用离线示例或交割单跑通一次复盘',
  'overview.onboarding.body': 'SmartMoney-Cub 对市场和执行只读、对你自己的台账可写。原文件只在本机解析，永不上传。',
  'overview.onboarding.step1': '1. 导入交割单或载入离线 Toy 示例',
  'overview.onboarding.step2': '2. 核对总览指标与每笔交易的失效条件',
  'overview.onboarding.step3': '3. 在「洞察」确认重复模式与规则候选',
  'overview.onboarding.ctaImport': '导入成交 / 试玩 Toy 示例',
  'overview.onboarding.ctaAssistant': '打开复盘助手',
  'overview.needsReview': '台账中有 {count} 条需要先确认的问题，未确认前这些成交不会进入统计。',
  'overview.resolve': '去处理',
  'overview.today.title': '今天你需要关注什么',
  'overview.today.empty': '今天还没有平仓交易。',
  'overview.today.emptyLedger': ' 台账里还没有已确认的平仓，先导入成交或载入离线示例。',
  'overview.today.summary': '今天完成 {count} 笔，净收益 ',
  'overview.today.planCheck': '对照了计划的 {assessed} 笔中 {deviations} 笔平仓价越过失效价',
  'overview.today.unrecorded': '其中 {count} 笔没有记录失效价，无法判断是否遵守计划。',
  'overview.card.worst.kicker': '今日最重要问题',
  'overview.card.worst.title': '{name} 亏了 {amount}',
  'overview.card.worst.mixedTitle': '币种不同或未知，无法比较最大亏损',
  'overview.card.worst.noneTitle': '今天没有亏损平仓',
  'overview.card.worst.body': '今天最大的一笔亏损来自 {symbol}，平仓于 {time}。',
  'overview.card.worst.mixedBody': '请选择同一已知币种的账户查看，不进行未经汇率换算的金额比较。',
  'overview.card.worst.noneBody': '今天平仓的交易里没有亏损，或者今天还没有平仓。这一格不是表扬，只是事实。',
  'overview.card.worst.emptyBody': '导入成交或载入离线 Toy 示例后，这里会自动标出最值得先复盘的一笔亏损。',
  'overview.card.worst.action': '打开这一笔',
  'overview.card.pattern.kicker': '正在形成的模式',
  'overview.card.pattern.title': '{symbol} 反复出现',
  'overview.card.pattern.noneTitle': '还没有形成重复的模式',
  'overview.card.pattern.body': '最近载入的 {total} 笔平仓里，{symbol} 出现 {count} 次，合计净盈亏 {pnl}。次数不算多，先看是什么模式。',
  'overview.card.pattern.noneBody': '最近载入的平仓里没有任何标的重合到 3 笔以上。样本不够就不叫模式。',
  'overview.card.pattern.action': '交给洞察分析',
  'overview.card.review.kicker': '今日待复盘',
  'overview.card.review.noneTitle': '今天没有需要复盘的交易',
  'overview.card.review.countTitle': '{count} 笔今日交易可复盘',
  'overview.card.review.emptyBody': '还没有平仓记录。先到「数据导入」上传交割单或一键载入 Toy 示例。',
  'overview.card.review.noneBody': '等今天有平仓之后，这里会列出可以复盘的对象。',
  'overview.card.review.body': '复盘助手会读这些交易的成交、台账问题与 Champion 规则，在右侧给出结论并引用证据。',
  'overview.card.review.action': '打开复盘助手',
  'overview.card.review.importAction': '去导入数据',
  'overview.kpi.netPnl': '净盈亏合计',
  'overview.kpi.closedCount': '已确认平仓 {count} 笔',
  'overview.kpi.winRate': '胜率',
  'overview.kpi.winLoss': '{wins} 胜 / {losses} 负',
  'overview.kpi.profitFactor': '盈亏比',
  'overview.kpi.pfFormula': '总盈利 / 总亏损绝对值',
  'overview.kpi.maxDrawdown': '最大回撤',
  'overview.kpi.closeOrder': '按平仓顺序累计',
  'overview.kpi.avgHolding': '平均持有',
  'overview.kpi.daysUnit': '{days} 天',
  'overview.kpi.avgReturn': '平均收益 {pct}',
  'overview.kpi.fees': '手续费合计',
  'overview.kpi.openCount': '仍未配对持仓 {count} 个',
  'overview.curve.title': '累计盈亏曲线',
  'overview.recent.title': '最近平仓',
  'overview.recent.viewAll': '查看全部',
  'overview.recent.empty': '还没有已确认的平仓交易。上传交割单、手工补录，或载入离线 Toy 示例即可开始复盘。',
  'overview.recent.openHint': '打开这一笔的复盘工作台',
  'overview.recent.logHint': '在交易日志中查看',
  'overview.col.symbol': '标的',
  'overview.col.exitTime': '平仓时间',
  'overview.col.return': '收益',
  'overview.col.netPnl': '净盈亏',
  'overview.col.qty': '数量',
  'overview.col.avgCost': '均价',
  'overview.col.openedAt': '开仓时间',
  'overview.openPositions.title': '未配对持仓',
  'overview.openPositions.empty': '没有未配对持仓。',
  'overview.issues.title': '待复盘清单',
  'overview.issues.empty': '台账没有发现问题。',
  'overview.issues.severity': '级别',
  'overview.issues.code': '代码',
  'overview.issues.detail': '说明',
  'overview.issues.error': '阻断',
  'overview.issues.warn': '提示',
  'overview.unrecorded': '未记录',
  'import.toy.cta': '载入离线 Toy 示例（4 笔完整闭环）',
  'import.toy.hint': '仅使用虚构标的（TOY.CUB / TOY.ALPHA / TOY.BETA），100% 离线；载入后可逐行核对再写入。',
  'import.toy.loaded': '已载入 {count} 行离线 Toy 示例成交（虚构标的）。核对无误后点击「确认导入」即可体验总览与洞察。',
  'import.next.title': '台账已更新，接下来可以：',
  'import.next.overview': '查看总览仪表盘',
  'import.next.insight': '查看洞察与模式',
  'import.confidence.high': '高',
  'import.confidence.medium': '中',
  'import.confidence.low': '低',
  'import.validation.required': '请填写日期、标的代码，以及大于 0 的价格与数量后再补录。',
  'chart.sparklineEmpty': '至少需要 2 笔平仓交易才能绘制曲线',
  'chart.barsEmpty': '暂无可归因的样本',
  'chart.tradeUnit': '{count} 笔',
  'insight.goImport': '去导入成交或示例',
  'insight.playbookError': '交易计划读取失败：{error}',
  'insight.noLinkedDetail': '{count} {unit}；暂无关联交易详情。',
  'insight.checksRun': '已执行 {count} 项检查：',
  'insight.avgReturnLine': '{count} 笔 · 平均收益 ',
} as const;

type FullMessages = Record<keyof typeof zh, string>;

const translations: { 'zh-CN': FullMessages; 'en-US': FullMessages } & Record<Exclude<Locale, 'zh-CN' | 'en-US'>, Partial<FullMessages>> = {
  'zh-CN': zh,
  'en-US': {
    'nav.review':'Review','nav.research':'Research','nav.strategy':'Strategy','nav.data':'Data','nav.overview':'Overview','nav.trades':'Trade log','nav.calendar':'Calendar','nav.reports':'Reports','nav.insight':'Insights','nav.lab':'Strategy lab','nav.drill':'Replay','nav.settings':'Settings','nav.connections':'Connections','nav.import':'Import',
    'hint.overview':'What needs attention today','hint.trades':'Closed trades and open lots','hint.calendar':'Review P&L by day','hint.reports':'Performance, risk and attribution','hint.insight':'Evidence-backed recurring patterns','hint.lab':'Playbooks, rules and backtests','hint.drill':'Actual-trade replay and simulation','hint.settings':'Models, plugins, diagnostics and privacy','hint.connections':'Read-only sync of executions and positions','hint.import':'Excel / CSV / PDF / screenshot',
    'app.local':'Local review workspace','app.localLedger':'Local ledger','app.offline':'All data stays offline','top.account':'Account scope','top.allAccounts':'All accounts','top.sync':'Sync','top.import':'Import','top.preferences':'Preferences','top.assistant.open':'Open assistant','top.assistant.close':'Hide assistant','top.lastSync':'Local ledger only',
    'prefs.title':'Display preferences','prefs.locale':'Language','prefs.timezone':'Time zone','prefs.theme':'Theme','prefs.theme.dark':'Dark','prefs.theme.light':'Light','prefs.scheme':'Gain/loss colors','prefs.scheme.cn':'Red gains','prefs.scheme.intl':'Green gains','prefs.currency':'Display currency','prefs.save':'Apply','prefs.close':'Close',
    'state.loading':'Loading…','state.retry':'Retry','state.unavailable':'This service is unavailable in this environment','state.empty':'No data','state.forbidden':'This service is unavailable here (403)',
    'connection.title':'Read-only connections','connection.subtitle':'Sync existing executions and positions without order or account permissions.','connection.available':'Available','connection.connected':'Connected','connection.unknown':'Permissions unknown','connection.readOnly':'Read only','connection.openOfficial':'Open official setup','connection.refresh':'Refresh','connection.noRoutes':'Connections are not enabled. The offline journal remains available.',
    'replay.review':'Actual-trade replay','replay.training':'Simulation training','replay.start':'Start replay','replay.step':'Next bar','replay.back':'Rewind branch','replay.play':'Play','replay.pause':'Pause','replay.history':'Session history','replay.simulated':'Simulation only; nothing is sent to a trading venue',
    'insight.patterns':'Pattern profile','insight.mistakes':'Repeated mistakes','insight.edges':'Edge library','insight.confirm':'Confirm','insight.reject':'Reject','insight.rename':'Rename','insight.evidence':'Evidence','insight.limitations':'Data limitations','insight.unknown':'Unknown',
    'action.cancel':'Cancel','action.save':'Save','action.close':'Close','error.service':'Cannot reach the local review service','error.read':'Read failed',
    'overview.onboarding.kicker': 'First run · 3-step review loop',
    'overview.onboarding.title': 'No confirmed trades yet — start with toy data or your statement',
    'overview.onboarding.body': 'Read-only over markets and execution, writable over your local journal. Source files are parsed locally and never uploaded.',
    'overview.onboarding.step1': '1. Import a statement or load the offline toy sample',
    'overview.onboarding.step2': '2. Review KPIs and each trade’s invalidation boundary',
    'overview.onboarding.step3': '3. Confirm recurring patterns & rule candidates in Insights',
    'overview.onboarding.ctaImport': 'Import trades / Try toy sample',
    'overview.onboarding.ctaAssistant': 'Open review assistant',
    'overview.needsReview': '{count} blocking ledger issue(s) need review before those fills enter statistics.',
    'overview.resolve': 'Resolve',
    'overview.today.title': 'What needs attention today',
    'overview.today.empty': 'No closed trades today.',
    'overview.today.emptyLedger': ' Your ledger has no confirmed closes yet — import executions or load the offline toy sample.',
    'overview.today.summary': '{count} closed today, net P&L ',
    'overview.today.planCheck': '{deviations} of {assessed} planned trades exited past invalidation',
    'overview.today.unrecorded': '{count} trade(s) have no recorded invalidation price, so plan adherence cannot be judged.',
    'overview.card.worst.kicker': 'Top loss today',
    'overview.card.worst.title': '{name} lost {amount}',
    'overview.card.worst.mixedTitle': 'Mixed or unknown currencies — cannot compare max loss',
    'overview.card.worst.noneTitle': 'No losing closes today',
    'overview.card.worst.body': 'Largest loss today came from {symbol}, closed at {time}.',
    'overview.card.worst.mixedBody': 'Select a single known-currency account to compare amounts without unverified FX conversion.',
    'overview.card.worst.noneBody': 'No losing trades closed today, or no closes yet. This is a neutral fact, not praise.',
    'overview.card.worst.emptyBody': 'After importing fills or loading the offline toy sample, the top losing trade surfaces here first.',
    'overview.card.worst.action': 'Open this trade',
    'overview.card.pattern.kicker': 'Emerging pattern',
    'overview.card.pattern.title': '{symbol} recurring',
    'overview.card.pattern.noneTitle': 'No recurring pattern yet',
    'overview.card.pattern.body': 'Across the latest {total} closes, {symbol} appeared {count} times (net P&L {pnl}). Inspect before treating as a pattern.',
    'overview.card.pattern.noneBody': 'No symbol appears 3+ times in recent closes. Insufficient sample is never labeled a pattern.',
    'overview.card.pattern.action': 'Inspect in Insights',
    'overview.card.review.kicker': 'Ready to review',
    'overview.card.review.noneTitle': 'No trades to review today',
    'overview.card.review.countTitle': '{count} trade(s) ready for review',
    'overview.card.review.emptyBody': 'No closed trades yet. Open Import to upload a statement or load the one-click toy sample.',
    'overview.card.review.noneBody': 'Once today has closed trades, they will appear here for review.',
    'overview.card.review.body': 'The review assistant reads these fills, ledger issues, and champion rules to cite evidence on the right.',
    'overview.card.review.action': 'Open review assistant',
    'overview.card.review.importAction': 'Go to Import',
    'overview.kpi.netPnl': 'Total Net P&L',
    'overview.kpi.closedCount': '{count} confirmed closes',
    'overview.kpi.winRate': 'Win Rate',
    'overview.kpi.winLoss': '{wins} W / {losses} L',
    'overview.kpi.profitFactor': 'Profit Factor',
    'overview.kpi.pfFormula': 'Gross profit / |gross loss|',
    'overview.kpi.maxDrawdown': 'Max Drawdown',
    'overview.kpi.closeOrder': 'Cumulative by close order',
    'overview.kpi.avgHolding': 'Avg Holding',
    'overview.kpi.daysUnit': '{days} d',
    'overview.kpi.avgReturn': 'Avg return {pct}',
    'overview.kpi.fees': 'Total Fees',
    'overview.kpi.openCount': '{count} open position(s)',
    'overview.curve.title': 'Cumulative P&L Curve',
    'overview.recent.title': 'Recent Closes',
    'overview.recent.viewAll': 'View all',
    'overview.recent.empty': 'No confirmed closed trades yet. Upload a statement, enter a fill manually, or load the offline toy sample.',
    'overview.recent.openHint': 'Open trade review drawer',
    'overview.recent.logHint': 'View in Trade Log',
    'overview.col.symbol': 'Symbol',
    'overview.col.exitTime': 'Exit time',
    'overview.col.return': 'Return',
    'overview.col.netPnl': 'Net P&L',
    'overview.col.qty': 'Qty',
    'overview.col.avgCost': 'Avg cost',
    'overview.col.openedAt': 'Opened at',
    'overview.openPositions.title': 'Open Positions',
    'overview.openPositions.empty': 'No open positions.',
    'overview.issues.title': 'Ledger Review Queue',
    'overview.issues.empty': 'No issues found in the ledger.',
    'overview.issues.severity': 'Severity',
    'overview.issues.code': 'Code',
    'overview.issues.detail': 'Detail',
    'overview.issues.error': 'Blocking',
    'overview.issues.warn': 'Notice',
    'overview.unrecorded': 'Unrecorded',
    'import.toy.cta': 'Load offline toy sample (4 round-trips)',
    'import.toy.hint': 'Uses synthetic symbols only (TOY.CUB / TOY.ALPHA / TOY.BETA), 100% offline. Inspect rows below before confirming.',
    'import.toy.loaded': 'Loaded {count} offline toy fills (synthetic symbols). Review below and click Confirm Import to explore Overview & Insights.',
    'import.next.title': 'Ledger updated — next steps:',
    'import.next.overview': 'Open Overview',
    'import.next.insight': 'Open Insights',
    'import.confidence.high': 'High',
    'import.confidence.medium': 'Med',
    'import.confidence.low': 'Low',
    'import.validation.required': 'Enter date, symbol, price > 0, and quantity > 0 before adding.',
    'chart.sparklineEmpty': 'At least 2 closed trades are needed to plot the cumulative P&L curve',
    'chart.barsEmpty': 'No attribution samples yet',
    'chart.tradeUnit': '{count} trades',
    'insight.goImport': 'Import trades or toy sample',
    'insight.playbookError': 'Could not read playbooks: {error}',
    'insight.noLinkedDetail': '{count} {unit}; no linked trade detail is available.',
    'insight.checksRun': 'Ran {count} deterministic checks:',
    'insight.avgReturnLine': '{count} trades · Avg return ',
  },
  'zh-TW': {
    ...shellCopy['zh-TW'], 'nav.research':'研究', 'nav.strategy':'策略', 'nav.data':'資料', 'nav.overview':'總覽',
  'nav.review':'複盤','nav.trades':'交易日誌','nav.calendar':'複盤日曆','nav.reports':'報告','nav.insight':'洞察','nav.lab':'策略實驗室','nav.drill':'演練','nav.settings':'設定','nav.connections':'連線','nav.import':'資料匯入','app.local':'本地複盤工作台','app.localLedger':'本地帳本','top.account':'帳戶範圍','top.allAccounts':'全部帳戶','top.sync':'同步','top.import':'匯入','top.preferences':'偏好','top.assistant.open':'開啟助手','top.assistant.close':'收起助手','prefs.title':'顯示偏好','prefs.locale':'語言','prefs.timezone':'時區','prefs.theme':'主題','prefs.scheme':'漲跌配色','state.loading':'載入中…','state.retry':'重試','state.empty':'暫無資料','connection.title':'唯讀連線','connection.subtitle':'同步既有成交與持倉，不取得下單或修改帳戶權限。','connection.openOfficial':'開啟官方設定','replay.review':'真實交易回放','replay.training':'模擬訓練','insight.patterns':'模式畫像','insight.mistakes':'重複錯誤','action.save':'儲存','error.service':'無法連線本地複盤服務',
  },
  'ja-JP': {
    ...shellCopy['ja-JP'], 'nav.review':'レビュー','nav.research':'分析','nav.strategy':'戦略','nav.data':'データ','nav.overview':'概要','nav.trades':'取引履歴','nav.calendar':'カレンダー','nav.reports':'レポート','nav.insight':'インサイト','nav.lab':'戦略ラボ','nav.drill':'リプレイ','nav.settings':'設定','nav.connections':'接続','nav.import':'インポート','app.local':'ローカル取引レビュー','app.localLedger':'ローカル台帳','top.account':'口座範囲','top.allAccounts':'すべての口座','top.sync':'同期','top.import':'取込','top.preferences':'表示設定','top.assistant.open':'アシスタントを開く','top.assistant.close':'アシスタントを閉じる','prefs.title':'表示設定','prefs.locale':'言語','prefs.timezone':'タイムゾーン','prefs.theme':'テーマ','prefs.scheme':'騰落色','state.loading':'読み込み中…','state.retry':'再試行','state.empty':'データなし','connection.title':'読み取り専用接続','connection.subtitle':'注文・口座変更権限なしで既存の約定とポジションを同期します。','connection.openOfficial':'公式設定を開く','replay.review':'実取引リプレイ','replay.training':'シミュレーション','insight.patterns':'パターン分析','insight.mistakes':'反復ミス','action.save':'保存','error.service':'ローカルサービスに接続できません',
  },
  'ko-KR': {
    ...shellCopy['ko-KR'], 'nav.review':'복기','nav.research':'분석','nav.strategy':'전략','nav.data':'데이터','nav.overview':'개요','nav.trades':'거래 일지','nav.calendar':'캘린더','nav.reports':'보고서','nav.insight':'인사이트','nav.lab':'전략 연구실','nav.drill':'리플레이','nav.settings':'설정','nav.connections':'연결','nav.import':'가져오기','app.local':'로컬 거래 복기','app.localLedger':'로컬 원장','top.account':'계좌 범위','top.allAccounts':'모든 계좌','top.sync':'동기화','top.import':'가져오기','top.preferences':'환경설정','top.assistant.open':'도우미 열기','top.assistant.close':'도우미 닫기','prefs.title':'표시 환경설정','prefs.locale':'언어','prefs.timezone':'시간대','prefs.theme':'테마','prefs.scheme':'상승/하락 색상','state.loading':'불러오는 중…','state.retry':'다시 시도','state.empty':'데이터 없음','connection.title':'읽기 전용 연결','connection.subtitle':'주문 또는 계좌 변경 권한 없이 기존 거래와 포지션을 동기화합니다.','connection.openOfficial':'공식 설정 열기','replay.review':'실거래 리플레이','replay.training':'모의 훈련','insight.patterns':'패턴 프로필','insight.mistakes':'반복 실수','action.save':'저장','error.service':'로컬 서비스에 연결할 수 없습니다',
  },
  'es-ES': {
    ...shellCopy['es-ES'], 'nav.review':'Revisión','nav.research':'Análisis','nav.strategy':'Estrategia','nav.data':'Datos','nav.overview':'Resumen','nav.trades':'Diario','nav.calendar':'Calendario','nav.reports':'Informes','nav.insight':'Patrones','nav.lab':'Laboratorio','nav.drill':'Repetición','nav.settings':'Ajustes','nav.connections':'Conexiones','nav.import':'Importar','app.local':'Diario local','app.localLedger':'Libro local','top.account':'Ámbito de cuenta','top.allAccounts':'Todas las cuentas','top.sync':'Sincronizar','top.import':'Importar','top.preferences':'Preferencias','top.assistant.open':'Abrir asistente','top.assistant.close':'Ocultar asistente','prefs.title':'Preferencias de pantalla','prefs.locale':'Idioma','prefs.timezone':'Zona horaria','prefs.theme':'Tema','prefs.scheme':'Colores de ganancias','state.loading':'Cargando…','state.retry':'Reintentar','state.empty':'Sin datos','connection.title':'Conexiones de solo lectura','connection.subtitle':'Sincroniza operaciones y posiciones sin permisos de órdenes ni cambios de cuenta.','connection.openOfficial':'Abrir configuración oficial','replay.review':'Repetición real','replay.training':'Simulación','insight.patterns':'Perfil de patrones','insight.mistakes':'Errores repetidos','action.save':'Guardar','error.service':'No se puede conectar al servicio local',
  },
  'pt-BR': {
    ...shellCopy['pt-BR'], 'nav.review':'Revisão','nav.research':'Análise','nav.strategy':'Estratégia','nav.data':'Dados','nav.overview':'Visão geral','nav.trades':'Diário','nav.calendar':'Calendário','nav.reports':'Relatórios','nav.insight':'Padrões','nav.lab':'Laboratório','nav.drill':'Replay','nav.settings':'Configurações','nav.connections':'Conexões','nav.import':'Importar','app.local':'Diário local','app.localLedger':'Livro local','top.account':'Escopo da conta','top.allAccounts':'Todas as contas','top.sync':'Sincronizar','top.import':'Importar','top.preferences':'Preferências','top.assistant.open':'Abrir assistente','top.assistant.close':'Ocultar assistente','prefs.title':'Preferências de exibição','prefs.locale':'Idioma','prefs.timezone':'Fuso horário','prefs.theme':'Tema','prefs.scheme':'Cores de ganhos','state.loading':'Carregando…','state.retry':'Tentar novamente','state.empty':'Sem dados','connection.title':'Conexões somente leitura','connection.subtitle':'Sincronize execuções e posições sem permissão para ordens ou alterações de conta.','connection.openOfficial':'Abrir configuração oficial','replay.review':'Replay real','replay.training':'Simulação','insight.patterns':'Perfil de padrões','insight.mistakes':'Erros repetidos','action.save':'Salvar','error.service':'Não foi possível conectar ao serviço local',
  },
  'de-DE': {
    ...shellCopy['de-DE'], 'nav.review':'Auswertung','nav.research':'Analyse','nav.strategy':'Strategie','nav.data':'Daten','nav.overview':'Übersicht','nav.trades':'Handelsjournal','nav.calendar':'Kalender','nav.reports':'Berichte','nav.insight':'Muster','nav.lab':'Strategielabor','nav.drill':'Replay','nav.settings':'Einstellungen','nav.connections':'Verbindungen','nav.import':'Import','app.local':'Lokales Handelsjournal','app.localLedger':'Lokales Journal','top.account':'Kontoumfang','top.allAccounts':'Alle Konten','top.sync':'Synchronisieren','top.import':'Import','top.preferences':'Darstellung','top.assistant.open':'Assistent öffnen','top.assistant.close':'Assistent schließen','prefs.title':'Anzeigeeinstellungen','prefs.locale':'Sprache','prefs.timezone':'Zeitzone','prefs.theme':'Design','prefs.scheme':'Gewinnfarben','state.loading':'Wird geladen…','state.retry':'Erneut versuchen','state.empty':'Keine Daten','connection.title':'Schreibgeschützte Verbindungen','connection.subtitle':'Ausführungen und Positionen ohne Order- oder Kontorechte synchronisieren.','connection.openOfficial':'Offizielle Einrichtung öffnen','replay.review':'Echter Handels-Replay','replay.training':'Simulation','insight.patterns':'Musterprofil','insight.mistakes':'Wiederholte Fehler','action.save':'Speichern','error.service':'Lokaler Dienst nicht erreichbar',
  },
  'fr-FR': {
    ...shellCopy['fr-FR'], 'nav.review':'Revue','nav.research':'Analyse','nav.strategy':'Stratégie','nav.data':'Données','nav.overview':'Vue d’ensemble','nav.trades':'Journal','nav.calendar':'Calendrier','nav.reports':'Rapports','nav.insight':'Schémas','nav.lab':'Laboratoire','nav.drill':'Relecture','nav.settings':'Réglages','nav.connections':'Connexions','nav.import':'Importer','app.local':'Journal local','app.localLedger':'Registre local','top.account':'Périmètre du compte','top.allAccounts':'Tous les comptes','top.sync':'Synchroniser','top.import':'Importer','top.preferences':'Préférences','top.assistant.open':'Ouvrir l’assistant','top.assistant.close':'Masquer l’assistant','prefs.title':'Préférences d’affichage','prefs.locale':'Langue','prefs.timezone':'Fuseau horaire','prefs.theme':'Thème','prefs.scheme':'Couleurs des gains','state.loading':'Chargement…','state.retry':'Réessayer','state.empty':'Aucune donnée','connection.title':'Connexions en lecture seule','connection.subtitle':'Synchronisez exécutions et positions sans droit d’ordre ni de modification de compte.','connection.openOfficial':'Ouvrir la configuration officielle','replay.review':'Relecture réelle','replay.training':'Simulation','insight.patterns':'Profil de schémas','insight.mistakes':'Erreurs répétées','action.save':'Enregistrer','error.service':'Impossible de joindre le service local',
  },
};

export type MessageKey = keyof typeof zh;

export function translate(key: MessageKey, locale = current, params: Params = {}): string {
  const template = translations[locale]?.[key] || translations['en-US'][key] || zh[key] || key;
  return Object.entries(params).reduce((text, [name, value]) => text.replaceAll('{' + name + '}', String(value)), template);
}

const STORAGE_KEY = 'smcub.locale';
let current: Locale = readLocale();
let currentTimezone = readTimezone();
const listeners = new Set<() => void>();

function readLocale(): Locale {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return LOCALES.includes(value as Locale) ? value as Locale : 'zh-CN';
  } catch {
    return 'zh-CN';
  }
}

function readTimezone(): string {
  try { return window.localStorage.getItem('smcub.timezone') || 'local'; } catch { return 'local'; }
}

export function getLocale(): Locale { return current; }

export function setPreferredTimeZone(timezone: string): void {
  currentTimezone = timezone || 'local';
}

export function setLocale(locale: Locale): void {
  if (current === locale) return;
  current = locale;
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
    const value = currentTimezone;
    if (!value || value === 'local') return undefined;
    new Intl.DateTimeFormat('en-US', { timeZone: value });
    return value;
  } catch { return undefined; }
}

export function localeName(locale: Locale = current): string { return LOCALE_LABELS[locale]; }

document.documentElement.lang = current;
