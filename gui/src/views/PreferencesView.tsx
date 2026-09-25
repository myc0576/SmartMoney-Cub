import { useEffect, useRef, useState } from 'react';
import { LOCALES, useI18n } from '../i18n';

interface PreferencesViewProps {
  scheme: 'cn' | 'intl';
  theme: 'light' | 'dark';
  onToggleScheme: () => void;
  onToggleTheme: () => void;
  onClose: () => void;
}

const TIMEZONES = ['local', 'UTC', 'Asia/Shanghai', 'Asia/Tokyo', 'Asia/Seoul', 'America/New_York', 'Europe/London'];
const ORIGINAL_CURRENCY = [
  '金额保留原始币种；不同币种分别展示，不进行未经验证的汇率换算。',
  'Amounts retain their source currency. Different currencies are shown separately; no unverified FX conversion is applied.',
  '金額保留原始幣別；不同幣別分別顯示，不進行未經驗證的匯率換算。',
  '金額は元の通貨で表示します。異なる通貨は分けて表示し、未検証の為替換算は行いません。',
  '금액은 원래 통화로 표시됩니다. 서로 다른 통화는 별도로 표시하며 검증되지 않은 환율로 환산하지 않습니다.',
  'Los importes conservan su moneda original. Las monedas se muestran por separado, sin conversiones de divisas no verificadas.',
  'Os valores mantêm a moeda original. Moedas diferentes são exibidas separadamente, sem conversões cambiais não verificadas.',
  'Beträge behalten ihre Originalwährung. Verschiedene Währungen werden getrennt angezeigt, ohne ungeprüfte Umrechnung.',
  'Les montants conservent leur devise d’origine. Les devises sont affichées séparément, sans conversion non vérifiée.',
];
const DEVICE_TIME = ['设备时区', 'Device time zone', '裝置時區', '端末のタイムゾーン', '기기 시간대', 'Zona horaria del dispositivo', 'Fuso horário do dispositivo', 'Gerätezeitzone', 'Fuseau horaire de l’appareil'];

export function PreferencesView({ scheme, theme, onToggleScheme, onToggleTheme, onClose }: PreferencesViewProps) {
  const { locale, t } = useI18n();
  const [timezone, setTimezone] = useState(() => readStored('smcub.timezone', 'local'));
  const dialog = useRef<HTMLElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const localeIndex = LOCALES.indexOf(locale);

  useEffect(() => {
    try { window.localStorage.setItem('smcub.timezone', timezone); } catch { /* optional preference */ }
  }, [timezone]);
  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const controls = () => Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not([disabled]), select:not([disabled]), input:not([disabled]), [tabindex="0"]') || []);
    controls()[0]?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); onCloseRef.current(); }
      if (event.key !== 'Tab') return;
      const items = controls();
      const first = items[0], last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('keydown', handleKey);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, []);

  return (
    <div className="preferences-backdrop" role="presentation" onClick={onClose}>
      <section ref={dialog} className="preferences-drawer" role="dialog" aria-modal="true" aria-labelledby="preferences-title" onClick={(event) => event.stopPropagation()}>
        <div className="preferences-head">
          <div><h2 id="preferences-title">{t('prefs.title')}</h2><span className="muted">{t('connection.readOnly')}</span></div>
          <button className="ghost" onClick={onClose} aria-label={t('action.close')}>×</button>
        </div>
        <div className="preferences-body">
          <div className="field"><label htmlFor="preference-timezone">{t('prefs.timezone')}</label><select id="preference-timezone" value={timezone} onChange={(event) => setTimezone(event.target.value)}>{TIMEZONES.map((item) => <option key={item} value={item}>{item === 'local' ? DEVICE_TIME[localeIndex] : item}</option>)}</select></div>
          <p className="notice">{ORIGINAL_CURRENCY[localeIndex]}</p>
          <div className="field"><label>{t('prefs.theme')}</label><div className="row"><button className={theme === 'dark' ? 'primary' : 'ghost'} onClick={() => theme !== 'dark' && onToggleTheme()}>{t('prefs.theme.dark')}</button><button className={theme === 'light' ? 'primary' : 'ghost'} onClick={() => theme !== 'light' && onToggleTheme()}>{t('prefs.theme.light')}</button></div></div>
          <div className="field"><label>{t('prefs.scheme')}</label><div className="row"><button className={scheme === 'cn' ? 'primary' : 'ghost'} onClick={() => scheme !== 'cn' && onToggleScheme()}>{t('prefs.scheme.cn')}</button><button className={scheme === 'intl' ? 'primary' : 'ghost'} onClick={() => scheme !== 'intl' && onToggleScheme()}>{t('prefs.scheme.intl')}</button></div></div>
          <div className="notice" style={{ marginTop: 4 }}><code>READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE</code></div>
        </div>
        <div className="preferences-foot"><button className="primary" onClick={onClose}>{t('prefs.close')}</button></div>
      </section>
    </div>
  );
}

function readStored(key: string, fallback: string): string {
  try { return window.localStorage.getItem(key) || fallback; } catch { return fallback; }
}
