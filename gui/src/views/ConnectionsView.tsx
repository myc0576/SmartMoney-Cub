import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { ConnectionAccount, ConnectionManifest, ConnectionStatus } from '../types';
import { Badge, Banner, Empty, Panel } from '../components/common';
import { useI18n } from '../i18n';
import { useConnectionCopy } from '../locales/connections';

type State = 'loading' | 'ready' | 'empty' | 'error';

export function ConnectionsView() {
  const { t } = useI18n();
  const c = useConnectionCopy();
  const [manifests, setManifests] = useState<ConnectionManifest[]>([]);
  const [accounts, setAccounts] = useState<ConnectionAccount[]>([]);
  const [statuses, setStatuses] = useState<ConnectionStatus[]>([]);
  const [state, setState] = useState<State>('loading');
  const [error, setError] = useState('');
  const [activeProvider, setActiveProvider] = useState<string | null>(null);
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [watchEnabled, setWatchEnabled] = useState(false);
  const [closed, setClosed] = useState(false);
  const [notice, setNotice] = useState('');
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [oauthUrl, setOauthUrl] = useState('');
  const load = useCallback(async () => {
    setState('loading');
    try {
      const result = await api.connections();
      const rawManifests = Array.isArray(result.manifests) ? result.manifests : [];
      const rawAccounts = Array.isArray(result.accounts) ? result.accounts : [];
      const rawStatuses = Array.isArray(result.statuses) ? result.statuses : [];
      // Older connection endpoints returned a cursor string and status scope
      // objects. Normalize at the view boundary so a malformed/legacy payload
      // cannot crash the card render or expose a credential value.
      const normalizedStatuses = rawStatuses.map((status) => ({
        ...status,
        credential_fields: Array.isArray(status.credential_fields) ? status.credential_fields : [],
        credential_values: {},
        cursor: status.cursor && typeof status.cursor === 'object'
          ? String((status.cursor as { checkpoint_cursor?: unknown }).checkpoint_cursor || (status.cursor as { cursor?: unknown }).cursor || '') || null
          : status.cursor || null,
      }));
      setManifests(rawManifests);
      setClosed(false);
      setAccounts(rawAccounts);
      setStatuses(normalizedStatuses);
      setState((rawManifests.length || rawAccounts.length) ? 'ready' : 'empty');
    } catch (failure) {
      if (failure instanceof Error && 'status' in failure && failure.status === 403) setClosed(true);
      setState('error');
      setError(failure instanceof Error ? failure.message : String(failure)); if (failure instanceof Error && 'status' in failure && failure.status === 403) setClosed(true);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!oauthUrl) return;
    const refresh = () => { void load(); };
    window.addEventListener('focus', refresh);
    return () => window.removeEventListener('focus', refresh);
  }, [oauthUrl, load]);
  const statusFor = (providerId: string) => statuses.find((item) => item.provider_id === providerId);
  const fieldsFor = (manifest: ConnectionManifest) => manifest.auth.fields.map((field) => typeof field === 'string' ? { name: field, label: field, secret: /token|secret|key|password|passphrase/i.test(field), required: true } : { name: field.name, label: field.label || field.name, secret: Boolean(field.secret), required: field.required !== false });
  const connect = async (manifest: ConnectionManifest) => {
    setActionBusy(manifest.provider_id);
    setError('');
    try {
      const fields = fieldsFor(manifest);
      const values: Record<string, string> = {};
      fields.forEach((field) => {
        const value = (credentials[field.name] || '').trim();
        if (value) values[field.name] = value;
      });
      const missing = fields.filter((field) => field.required && !values[field.name]);
      if (missing.length) throw new Error(c('required') + missing.map((field) => field.label).join(', '));
      const result = await api.connectAccount(manifest.provider_id, { credentials: values, config: manifest.provider_id === 'local-statement-directory' ? { watch_enabled: watchEnabled } : {} });
      if (result.status !== 'ok') throw new Error(c('denied') + ': ' + (result.scope?.issues?.join(', ') || result.error || ''));
      setActiveProvider(null);
      setCredentials({});
      setWatchEnabled(false);
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure)); if (failure instanceof Error && 'status' in failure && failure.status === 403) setClosed(true);
    } finally {
      setActionBusy(null);
    }
  };
  const startOAuth = async () => {
    setActionBusy('snaptrade-personal-mcp:oauth');
    setError('');
    try {
      const redirectUri = window.location.origin + '/api/trader/connections/snaptrade-personal-mcp/oauth/callback';
      const result = await api.snaptradeOAuthStart(redirectUri);
      const url = new URL(result.authorization_url);
      if (result.status !== 'ok' || url.origin !== 'https://dashboard.snaptrade.com' || url.pathname !== '/oauth/authorize') throw new Error(c('oauthInvalid'));
      setOauthUrl(url.href);
      window.open(url.href, '_blank', 'noopener,noreferrer');
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure)); if (failure instanceof Error && 'status' in failure && failure.status === 403) setClosed(true);
    } finally {
      setActionBusy(null);
    }
  };
  const sync = async (providerId: string) => {
    setActionBusy(providerId + ':sync');
    setError('');
    setNotice('');
    try {
      const result = await api.syncAccount(providerId);
      await load();
      if (result.status !== 'ok' || result.partial || result.errors?.length) throw new Error(c('partial') + ': ' + (result.errors || []).join(', '));
      setNotice(c('success') + ': ' + (result.imported_count || 0) + ' / ' + (result.updated_count || 0));
    } catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); if (failure instanceof Error && 'status' in failure && failure.status === 403) setClosed(true); } finally { setActionBusy(null); }
  };
  const disconnect = async (providerId: string) => {
    if (!window.confirm(c('confirmDisconnect'))) return;
    setActionBusy(providerId + ':disconnect');
    setError('');
    try {
      const result = await api.disconnectAccount(providerId); await load();
      if (result.status !== 'ok') throw new Error(c('denied'));
      if (result.connection?.remote_revocation_pending) setNotice(c('revocation'));
    } catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); if (failure instanceof Error && 'status' in failure && failure.status === 403) setClosed(true); } finally { setActionBusy(null); }
  };
  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="notice"><strong>{t('connection.title')}</strong><div className="muted" style={{ marginTop: 4 }}>{t('connection.subtitle')}</div><div style={{ marginTop: 6 }}><code>READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE</code></div></div>
      <div className="row" style={{ justifyContent: 'space-between' }}><span className="eyebrow">{t('connection.title')}</span><button className="ghost" onClick={() => void load()} disabled={state === 'loading'}>{t('connection.refresh')}</button></div>
      {state === 'loading' ? <Panel><div className="muted">{t('state.loading')}</div></Panel> : null}
      {error && state !== 'error' ? <div role="alert" className="banner">{error}</div> : null}
      {notice ? <div role="status" className="notice">{notice}</div> : null}
      {state === 'error' ? <Panel><Banner>{t('error.read')}: {error}<button className="ghost" style={{ marginLeft: 8 }} onClick={() => void load()}>{t('state.retry')}</button></Banner></Panel> : null}
      {state === 'empty' ? <Panel><Empty text={t('connection.noRoutes')} /></Panel> : null}
      {state === 'ready' ? <>
        <div className="connection-grid">
          {manifests.map((manifest) => {
            const status = statusFor(manifest.provider_id);
            const scopeStatus = status?.scope && typeof status.scope === 'object' ? String((status.scope as { status?: unknown }).status || '') : '';
            const permissionsUnknown = !status || (!status.connected && !status.revoked && (!status.credential_fields.length || scopeStatus === 'unverified'));
            const fields = fieldsFor(manifest);
            const scopeVerified = status?.scope?.status === 'verified' && status?.scope?.allowed === true;
            return <Panel key={manifest.provider_id}>
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}><strong>{manifest.name}</strong><Badge kind={status?.connected ? 'ok' : permissionsUnknown ? 'warn' : 'error'}>{status?.connected ? t('connection.connected') : permissionsUnknown ? t('connection.unknown') : t('connection.available')}</Badge></div>
              <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>{manifest.description}</div>
              <p className="muted">{manifest.auth.notes}</p>
              <div className="row" style={{ marginTop: 8, gap: 4, flexWrap: 'wrap' }}>{manifest.supported_assets.map((asset) => <span className="tag" key={asset}>{asset}</span>)}<span className="tag">{t('connection.readOnly')}</span></div>
              <div className="connection-meta"><span>{c('auth')}: {manifest.auth.mode}</span><span>{c('history')}: {manifest.history.precision || 'unknown'}</span><span>{c('validation')}: {manifest.validation.status}</span></div>
              <div className="row" style={{ marginTop: 10 }}>{manifest.official_links.map((link) => <a className="ghost" href={link.url} target="_blank" rel="noreferrer" key={link.url}>{link.label}</a>)}{manifest.auth.mode === 'dcr_pkce' ? <button className="ghost" disabled={Boolean(actionBusy) || closed} onClick={() => void startOAuth()}>{c('oauth')}</button> : <button className="ghost" disabled={Boolean(actionBusy) || closed} onClick={() => { setActiveProvider(activeProvider === manifest.provider_id ? null : manifest.provider_id); setCredentials({}); setWatchEnabled(Boolean(status?.watch_active)); }}>{status?.connected ? c('configure') : c('connect')}</button>}{status?.connected ? <><button className="ghost" disabled={!scopeVerified || Boolean(actionBusy) || closed} onClick={() => void sync(manifest.provider_id)}>{c('sync')}</button><button className="ghost" disabled={Boolean(actionBusy) || closed} onClick={() => void disconnect(manifest.provider_id)}>{c('disconnect')}</button></> : null}</div>
              {oauthUrl && manifest.auth.mode === 'dcr_pkce' ? <div className="muted" style={{ marginTop: 6, fontSize: 11 }}><a href={oauthUrl} target="_blank" rel="noreferrer" style={{ color: 'var(--color-accent)' }}>{c('oauthContinue')}</a></div> : null}
              {activeProvider === manifest.provider_id ? <div className="panel" style={{ marginTop: 10, background: 'var(--inset)' }}>
                {manifest.auth.mode === 'dcr_pkce' ? <div className="notice" style={{ fontSize: 11, marginBottom: 8 }}>{c('oauthContinue')}</div> : null}
                {manifest.auth.mode !== 'dcr_pkce' ? fields.map((field) => <label className="field" key={field.name}><span>{field.label}{field.required ? ' *' : ''}</span><input aria-label={field.label} autoComplete="off" disabled={Boolean(actionBusy) || closed} type={field.secret ? 'password' : 'text'} value={credentials[field.name] || ''} onChange={(event) => setCredentials((current) => ({ ...current, [field.name]: event.target.value }))} placeholder={field.name} /></label>) : null}
                {manifest.provider_id === 'local-statement-directory' ? <label className="row"><input type="checkbox" style={{ width: 'auto' }} disabled={Boolean(actionBusy) || closed} checked={watchEnabled} onChange={event => setWatchEnabled(event.target.checked)} />{c('watch')}</label> : null}
                <div className="row" style={{ justifyContent: 'flex-end', marginTop: 8 }}><button className="primary" disabled={Boolean(actionBusy) || closed} onClick={() => void connect(manifest)}>{c('save')}</button></div>
              </div> : null}
              {status?.cursor ? <div className="muted" style={{ marginTop: 8, fontSize: 11 }}>{c('checkpoint')}: <code>{status.cursor}</code></div> : null}
              {status?.watch_active ? <p className="notice">{c('watching')}</p> : null}
              {status?.errors?.length ? <p className="notice">{c('partial')}: {status.errors.join(', ')}</p> : null}
              {permissionsUnknown ? <div className="notice" style={{ marginTop: 8, fontSize: 11 }}>{c('blocked')}</div> : null}
            </Panel>;
          })}
        </div>
        {accounts.length ? <Panel title={t('top.account')}><div className="scroll-x"><table><thead><tr><th>{t('top.account')}</th><th>{c('source')}</th><th>{c('asset')}</th><th>{c('currency')}</th><th>{c('status')}</th></tr></thead><tbody>{accounts.map((account) => <tr key={account.account_id}><td>{account.display_name}</td><td>{account.provider}</td><td>{account.asset_class}</td><td>{account.currency}</td><td><span className="badge ok">{account.status}</span></td></tr>)}</tbody></table></div></Panel> : null}
      </> : null}
    </div>
  );
}
