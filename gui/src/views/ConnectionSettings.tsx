import { useEffect, useRef, useState, type ComponentProps } from 'react';
import { api } from '../api';
import type { AgentIntegration } from '../types';
import { SettingsView } from './SettingsView';
import './connectionSettings.css';

type Section = 'general' | 'jev' | 'agents';
type Connection = { configured: boolean; key_source: string; connection: string; model: string; checked_at?: string };

async function jevRequest(path = '', body?: Record<string, unknown>): Promise<Connection> {
  const url = new URL('api/settings/jev' + path, document.baseURI || window.location.href);
  const response = await fetch(url, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok || result.status === 'error') throw new Error(result.error || 'JEV 设置请求失败');
  return result;
}

export function ConnectionSettings(props: ComponentProps<typeof SettingsView>) {
  const [section, setSection] = useState<Section>('general');
  const [visited, setVisited] = useState<Set<Section>>(() => new Set(['general']));
  const sections: [Section, string][] = [['general', '模型与偏好'], ['jev', 'JEV 连接'], ['agents', 'Agent 集成']];
  return (
    <div className="connection-settings">
      <div className="settings-sections" role="group" aria-label="设置分类">
        {sections.map(([id, label]) => <button key={id} aria-pressed={section === id}
          className={section === id ? 'primary' : 'ghost'} onClick={() => {
            setSection(id); setVisited(prev => new Set([...prev, id]));
          }}>{label}</button>)}
      </div>
      <div hidden={section !== 'general'}><SettingsView {...props} /></div>
      {visited.has('jev') ? <div hidden={section !== 'jev'}><JevConnection /></div> : null}
      {visited.has('agents') ? <div hidden={section !== 'agents'}><AgentConnections /></div> : null}
    </div>
  );
}

export function JevConnection() {
  const [connection, setConnection] = useState<Connection | null>(null);
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const lock = useRef(false);
  useEffect(() => {
    let live = true;
    jevRequest().then(value => { if (live) setConnection(value); })
      .catch(() => { if (live) setError('无法读取 JEV 设置，请检查本地服务后重试。'); });
    return () => { live = false; };
  }, []);
  const act = async (action: 'save' | 'test' | 'clear' | 'refresh') => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError(''); setNotice('');
    try {
      const value = action === 'refresh' ? await jevRequest()
        : action === 'test' ? await jevRequest('/test', {})
        : await jevRequest('', action === 'clear' ? { clear_key: true } : { api_key: key });
      setConnection(value);
      if (action === 'save' || action === 'clear') setKey('');
      setNotice(action === 'test' ? '连接测试成功；仅代表本次请求成功。'
        : action === 'save' ? '密钥已保存在本机，尚未测试连接。'
        : action === 'clear' ? (value.key_source === 'environment' ? '本机密钥已清除；启动环境中的密钥仍然有效。' : '本机密钥已清除。') : '设置已刷新。');
    } catch (failure) {
      if (action === 'test') setConnection(prev => prev ? { ...prev, connection: 'failed' } : prev);
      setError(failure instanceof Error ? failure.message : '请求失败，请重试。');
    } finally { lock.current = false; setBusy(false); }
  };
  return (
    <section className="connection-card" aria-labelledby="jev-connection-title">
      <div className="connection-heading"><div><h2 id="jev-connection-title">JEV 连接</h2>
        <p>可选的结构化判断服务，不是聊天模型。不配置也可以继续使用本地复盘功能。</p></div>
        <span className="tag">{connection?.connection === 'connected' ? '本次测试通过'
          : connection?.connection === 'failed' ? '测试未通过'
          : connection?.configured ? '已配置 · 未测试' : connection ? '未配置' : '状态未知'}</span></div>
      <p>连接 TypeSafe 官方服务。密钥仅保存在本机凭据文件中，不回显、不写入浏览器存储。</p>
      {connection?.key_source === 'environment' ? <p className="muted">当前使用启动环境中的 TYPESAFE_API_KEY；保存本机密钥后将优先使用本机配置。</p> : null}
      <form onSubmit={event => { event.preventDefault(); void act('save'); }}>
        <label htmlFor="jev-key">JEV API 密钥</label>
        <input id="jev-key" type="password" autoComplete="new-password" spellCheck={false}
          value={key} onChange={event => { setKey(event.target.value); setNotice(''); }}
          placeholder={connection?.configured ? '留空保留已保存密钥' : '粘贴密钥本身'} disabled={busy} />
        <div className="connection-actions">
          <button type="submit" className="primary" disabled={busy || !key.trim()}>保存密钥</button>
          <button type="button" className="ghost" disabled={busy || !connection?.configured || Boolean(key)} onClick={() => void act('test')}>测试连接</button>
          <button type="button" className="ghost" disabled={busy || connection?.key_source !== 'local'} onClick={() => {
            if (window.confirm('清除本机保存的 JEV 密钥？不会删除启动环境中的密钥。')) void act('clear');
          }}>清除本机密钥</button>
          <button type="button" className="ghost" disabled={busy} onClick={() => void act('refresh')}>刷新</button>
        </div>
      </form>
      <p className="muted">测试会向官方 API 发送一条固定的合成问题，可能产生少量调用费用；不会发送交易记录。修改密钥后请先保存再测试。</p>
      {busy ? <p role="status">正在处理请求…</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      {error ? <p role="alert" className="connection-error">{error}</p> : null}
    </section>
  );
}

const STATUS: Record<string, string> = {
  healthy: '正常就绪', configured: '已配置', detected: '已检测到',
  not_found: '未安装', unavailable: '不可用', unsupported: '不支持',
};

export function AgentConnections() {
  const [agents, setAgents] = useState<AgentIntegration[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const lock = useRef(false);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    api.agents().then(value => { if (mounted.current) setAgents(value.agents); })
      .catch(() => { if (mounted.current) setError('无法读取 Agent 列表，请重试。'); })
      .finally(() => { if (mounted.current) setLoading(false); });
    return () => { mounted.current = false; };
  }, []);
  const refresh = async () => {
    if (lock.current) return;
    lock.current = true; setLoading(true); setError('');
    try { setAgents((await api.agents()).agents); }
    catch { setError('无法读取 Agent 列表，请重试。'); }
    finally { lock.current = false; setLoading(false); }
  };
  const act = async (id: string, action: 'preview' | 'apply' | 'disable' | 'restore') => {
    if (lock.current) return;
    if (action === 'restore' && !window.confirm('移除本产品管理的 Agent 配置片段并恢复原配置？')) return;
    lock.current = true; setBusy(id); setError(''); setNotice('');
    try {
      const result = action === 'disable' ? await api.agentDisable(id)
        : action === 'restore' ? await api.agentRestore(id) : await api.agentApply(id, action === 'preview');
      setNotice(`${result.agent.label}：${action === 'preview' ? '试运行完成，未写入配置' : action === 'apply' ? '已应用配置' : action === 'disable' ? '已停用' : '已恢复'}。`);
      if (action !== 'preview') {
        try { setAgents((await api.agents()).agents); }
        catch { setError('操作已完成，但列表刷新失败；请刷新查看状态。'); }
      }
    } catch { setError('Agent 操作失败，请检查本机配置权限后重试。'); }
    finally { lock.current = false; setBusy(''); }
  };
  return <section className="connection-card" aria-labelledby="agent-connections-title">
    <div className="connection-heading"><div><h2 id="agent-connections-title">Agent 集成中心</h2>
      <p>集中管理外部 Agent 的接入，仅修改本产品管理的配置片段。</p></div>
      <button className="ghost" onClick={() => void refresh()} disabled={loading || Boolean(busy)}>刷新列表</button></div>
    {loading ? <p role="status">正在读取 Agent 配置…</p> : null}
    {notice ? <p role="status">{notice}</p> : null}
    {error ? <p role="alert" className="connection-error">{error}</p> : null}
    {!loading && !error && !agents.length ? <p className="muted">暂无可用的 Agent 集成。</p> : null}
    <div className="agent-connections-grid">{agents.map(agent => <article key={agent.agent_id} className="agent-connection">
      <div className="connection-heading"><strong>{agent.label}</strong><span className="tag">{STATUS[agent.status] || agent.status}</span></div>
      <p>{agent.detail}</p><small className="muted">{agent.config_path || '尚无配置路径'}</small>
      <div className="connection-actions">{(['preview', 'apply', 'disable', 'restore'] as const).map((action, index) =>
        <button className="ghost" key={action} disabled={loading || Boolean(busy)} onClick={() => void act(agent.agent_id, action)}>
          {['试运行', '应用', '停用', '恢复'][index]}</button>)}</div>
      {busy === agent.agent_id ? <p role="status">正在处理…</p> : null}
    </article>)}</div>
    <p className="muted">READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE</p>
  </section>;
}
