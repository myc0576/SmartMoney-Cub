import { LOCALES, useLocale } from '../i18n';
type Copy = readonly [string, string, string, string, string, string, string, string, string];
const messages = {
  closedAt: ['平仓时间','Closed at','平倉時間','決済時刻','청산 시각','Hora de cierre','Hora de fechamento','Geschlossen am','Heure de clôture'],
  openedAt: ['开仓时间','Opened at','開倉時間','建玉日時','진입 시각','Hora de apertura','Hora de abertura','Eröffnet am','Heure d’ouverture'],
  quantity: ['数量','Quantity','數量','数量','수량','Cantidad','Quantidade','Menge','Quantité'],
  holding: ['持有','Holding','持有','保有期間','보유 기간','Tenencia','Permanência','Haltedauer','Détention'],
  symbolFilter: ['按标的筛选','Filter by symbol','依標的篩選','銘柄で絞り込み','종목 필터','Filtrar por instrumento','Filtrar por ativo','Nach Instrument filtern','Filtrer par instrument'],
  symbolPlaceholder: ['精确标的代码','Exact symbol','完整標的代碼','正確な銘柄コード','정확한 종목 코드','Símbolo exacto','Símbolo exato','Exaktes Symbol','Symbole exact'],
  start: ['开始日期','Start date','開始日期','開始日','시작일','Fecha inicial','Data inicial','Startdatum','Date de début'],
  end: ['结束日期','End date','結束日期','終了日','종료일','Fecha final','Data final','Enddatum','Date de fin'],
  accountFilter: ['按账户筛选','Filter by account','依帳戶篩選','口座で絞り込み','계좌 필터','Filtrar por cuenta','Filtrar por conta','Nach Konto filtern','Filtrer par compte'],
  query: ['查询','Apply filters','查詢','検索','조회','Aplicar filtros','Aplicar filtros','Filter anwenden','Appliquer les filtres'],
  clear: ['清除','Clear','清除','クリア','초기화','Limpiar','Limpar','Zurücksetzen','Effacer'],
  total: ['本页合计','Page total','本頁合計','このページの合計','현재 페이지 합계','Total de la página','Total da página','Seitensumme','Total de la page'],
  sortHint: ['本页排序；金额仅在同币种内比较','Sort this page; monetary values compare only within a currency','本頁排序；金額僅在同幣別內比較','ページ内で並べ替え。金額比較は同じ通貨内のみ','현재 페이지 정렬, 금액은 동일 통화 내에서만 비교','Ordenar esta página; importes comparables solo en la misma moneda','Ordenar esta página; valores comparáveis somente na mesma moeda','Seite sortieren; Geldbeträge nur innerhalb einer Währung vergleichen','Tri de cette page ; montants comparables uniquement dans une même devise'],
  empty: ['没有已配对平仓的交易。可调整筛选或导入成交记录。','No matched closed trades. Adjust filters or import executions.','沒有已配對平倉交易。可調整篩選或匯入成交紀錄。','対応する決済済み取引がありません。条件を変更するか約定を取り込んでください。','매칭된 청산 거래가 없습니다. 필터를 변경하거나 체결을 가져오세요.','Sin operaciones cerradas emparejadas. Ajuste filtros o importe ejecuciones.','Nenhuma operação encerrada pareada. Ajuste filtros ou importe execuções.','Keine zugeordneten abgeschlossenen Trades. Filter ändern oder Ausführungen importieren.','Aucune opération clôturée appariée. Ajustez les filtres ou importez des exécutions.'],
  import: ['去导入成交','Import executions','匯入成交','約定を取り込む','체결 가져오기','Importar ejecuciones','Importar execuções','Ausführungen importieren','Importer des exécutions'],
  openTrade: ['查看这笔交易的证据','View this trade’s evidence','檢視此交易的證據','この取引の根拠を表示','이 거래의 근거 보기','Ver pruebas de esta operación','Ver evidências desta operação','Belege dieses Trades anzeigen','Voir les preuves de cette opération'],
  noPositions: ['没有未配对持仓。','No unmatched positions.','沒有未配對持倉。','未対応の建玉はありません。','미매칭 포지션이 없습니다.','Sin posiciones sin emparejar.','Nenhuma posição não pareada.','Keine nicht zugeordneten Positionen.','Aucune position non appariée.'],
  averageCost: ['单位成本','Unit cost','單位成本','単位原価','단위 원가','Coste unitario','Custo unitário','Stückkosten','Coût unitaire'],
  previous: ['上一页','Previous page','上一頁','前のページ','이전 페이지','Página anterior','Página anterior','Vorherige Seite','Page précédente'],
  next: ['下一页','Next page','下一頁','次のページ','다음 페이지','Página siguiente','Próxima página','Nächste Seite','Page suivante'],
  invalidRange: ['开始日期不能晚于结束日期','Start date must not be after end date','開始日期不能晚於結束日期','開始日は終了日以前にしてください','시작일은 종료일보다 늦을 수 없습니다','La fecha inicial no puede ser posterior a la final','A data inicial não pode ser posterior à final','Startdatum darf nicht nach dem Enddatum liegen','La date de début ne peut pas dépasser la date de fin'],
} satisfies Record<string, Copy>;
export function useJournalCopy() {
  const [locale] = useLocale();
  return (key: keyof typeof messages) => messages[key][LOCALES.indexOf(locale)];
}
