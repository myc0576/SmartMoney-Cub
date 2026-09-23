import { LOCALES, useLocale } from '../i18n';

// Explicit native copy in the same order as LOCALES. No cross-language fallback.
type Copy = readonly [string, string, string, string, string, string, string, string, string];
const messages = {
  connect: ['连接','Connect','連線','接続','연결','Conectar','Conectar','Verbinden','Connecter'],
  configure: ['重新配置','Reconfigure','重新設定','再設定','다시 설정','Reconfigurar','Reconfigurar','Neu konfigurieren','Reconfigurer'],
  sync: ['同步','Sync','同步','同期','동기화','Sincronizar','Sincronizar','Synchronisieren','Synchroniser'],
  disconnect: ['断开','Disconnect','中斷連線','切断','연결 해제','Desconectar','Desconectar','Trennen','Déconnecter'],
  confirmDisconnect: ['确认断开此连接吗？已导入的本地复盘记录会保留。','Disconnect? Imported journal records will be preserved.','確定中斷連線？已匯入的複盤紀錄會保留。','切断しますか？取込済みの取引記録は保持されます。','연결을 해제할까요? 가져온 거래 기록은 유지됩니다.','¿Desconectar? Se conservarán los registros importados.','Desconectar? Os registros importados serão preservados.','Verbindung trennen? Importierte Journaldaten bleiben erhalten.','Déconnecter ? Les opérations importées seront conservées.'],
  required: ['请填写：','Required: ','請填寫：','必須項目：','필수 항목: ','Campos obligatorios: ','Campos obrigatórios: ','Erforderlich: ','Champs obligatoires : '],
  denied: ['只读权限校验未通过','Read-only access could not be verified','唯讀權限驗證未通過','読み取り専用権限を確認できません','읽기 전용 권한을 확인할 수 없습니다','No se pudo verificar el acceso de solo lectura','Não foi possível verificar o acesso somente leitura','Lesezugriff konnte nicht bestätigt werden','Impossible de vérifier l’accès en lecture seule'],
  partial: ['同步未完整完成，请检查以下问题','Sync incomplete; review the issues below','同步未完整完成，請檢查以下問題','同期が未完了です。次の問題を確認してください','동기화가 완료되지 않았습니다. 아래 문제를 확인하세요','Sincronización incompleta; revise los problemas','Sincronização incompleta; verifique os problemas','Synchronisierung unvollständig; Hinweise prüfen','Synchronisation incomplète ; vérifiez les problèmes'],
  success: ['同步完成；新增 / 更新','Sync complete; inserted / updated','同步完成；新增 / 更新','同期完了：追加 / 更新','동기화 완료: 추가 / 갱신','Sincronización completada; añadidos / actualizados','Sincronização concluída; inseridos / atualizados','Synchronisiert; hinzugefügt / aktualisiert','Synchronisation terminée ; ajouts / mises à jour'],
  save: ['验证并保存只读连接','Verify and save read-only connection','驗證並儲存唯讀連線','読み取り専用接続を検証して保存','읽기 전용 연결 확인 및 저장','Verificar y guardar conexión de solo lectura','Verificar e salvar conexão somente leitura','Leseverbindung prüfen und speichern','Vérifier et enregistrer la connexion en lecture seule'],
  watch: ['自动导入此目录（程序运行时每 30 秒）','Auto-import this directory every 30 seconds while the app is running','自動匯入此目錄（程式執行時每 30 秒）','アプリ起動中、30 秒ごとにこのフォルダーを自動取込','앱 실행 중 이 폴더를 30초마다 자동으로 가져오기','Importar esta carpeta cada 30 segundos mientras la aplicación esté abierta','Importar esta pasta a cada 30 segundos enquanto o aplicativo estiver aberto','Ordner bei laufender Anwendung alle 30 Sekunden importieren','Importer ce dossier toutes les 30 secondes pendant l’exécution'],
  watching: ['目录自动导入已开启','Directory auto-import is active','目錄自動匯入已開啟','フォルダーの自動取込が有効です','폴더 자동 가져오기가 켜져 있습니다','Importación automática de carpeta activada','Importação automática da pasta ativada','Automatischer Ordnerimport aktiv','Importation automatique du dossier active'],
  oauth: ['使用官方 OAuth 授权','Authorize with official OAuth','使用官方 OAuth 授權','公式 OAuth で認証','공식 OAuth로 인증','Autorizar con OAuth oficial','Autorizar com OAuth oficial','Mit offiziellem OAuth autorisieren','Autoriser avec OAuth officiel'],
  oauthContinue: ['继续授权；完成后返回并刷新','Continue authorization; return and refresh when done','繼續授權；完成後返回並重新整理','認証を続行し、完了後に戻って更新','인증을 완료한 후 돌아와 새로고침하세요','Continuar autorización; vuelva y actualice al terminar','Continuar autorização; volte e atualize ao concluir','Autorisierung fortsetzen; danach zurückkehren und aktualisieren','Poursuivre l’autorisation, puis revenir et actualiser'],
  oauthInvalid: ['授权链接不属于官方站点，已阻止','Non-official authorization URL blocked','非官方授權連結已封鎖','公式以外の認証 URL をブロックしました','비공식 인증 URL이 차단되었습니다','Enlace de autorización no oficial bloqueado','URL de autorização não oficial bloqueada','Nicht offizielle Autorisierungsadresse blockiert','Lien d’autorisation non officiel bloqué'],
  auth: ['认证','Authentication','驗證','認証','인증','Autenticación','Autenticação','Authentifizierung','Authentification'],
  history: ['历史精度','History precision','歷史精度','履歴の精度','기록 정밀도','Precisión histórica','Precisão do histórico','Historiengenauigkeit','Précision de l’historique'],
  validation: ['校验','Validation','驗證','検証','검증','Validación','Validação','Prüfung','Validation'],
  source: ['来源','Source','來源','ソース','출처','Fuente','Fonte','Quelle','Source'],
  asset: ['资产','Asset','資產','資産','자산','Activo','Ativo','Anlage','Actif'],
  currency: ['币种','Currency','幣別','通貨','통화','Moneda','Moeda','Währung','Devise'],
  status: ['状态','Status','狀態','状態','상태','Estado','Estado','Status','État'],
  blocked: ['权限未知，同步已阻止','Permissions unknown; sync blocked','權限未知，同步已封鎖','権限不明のため同期をブロック','권한을 확인할 수 없어 동기화가 차단되었습니다','Permisos desconocidos; sincronización bloqueada','Permissões desconhecidas; sincronização bloqueada','Berechtigungen unbekannt; Synchronisierung gesperrt','Droits inconnus ; synchronisation bloquée'],
  checkpoint: ['同步断点','Checkpoint','同步檢查點','同期チェックポイント','동기화 체크포인트','Punto de control','Ponto de controle','Synchronisierungsstand','Point de reprise'],
  revocation: ['本地凭据已清除；请在服务商设置中确认撤销授权','Local credentials cleared; confirm revocation in provider settings','本地憑證已清除；請至服務商設定確認撤銷授權','ローカル認証情報を削除しました。提供元の設定で認可の取消を確認してください','로컬 인증 정보를 삭제했습니다. 제공업체 설정에서 권한 취소를 확인하세요','Credenciales locales eliminadas; confirme la revocación con el proveedor','Credenciais locais removidas; confirme a revogação no provedor','Lokale Zugangsdaten entfernt; Widerruf beim Anbieter bestätigen','Identifiants locaux effacés ; confirmez la révocation chez le fournisseur'],
} satisfies Record<string, Copy>;

export function useConnectionCopy() {
  const [locale] = useLocale();
  const index = LOCALES.indexOf(locale);
  return (key: keyof typeof messages) => messages[key][index];
}
