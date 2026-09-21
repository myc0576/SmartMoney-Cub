import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { AgentIntegration, JevConnection } from '../types';
import { Badge, Empty, Panel } from '../components/common';

export function JevConnectionSettings() {
  const [connection, setConnection] = useState<JevConnection | null>(null);
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [confirmClear, setConfirmClear] = useState(false);
  const pending = useRef(false);
  useEffect(() => {
    let alive = true;
    void api.jevConnection().then(value => { if (alive) setConnection(value); })
      .catch(() => { if (alive) setError('JEV 设置读取失败，请重新打开此页重试。'); });
    return () => { alive = false; };
  }, []);

  async function act(action: 'save' | 'clear' | 'test') {
    if (pending.current) return;
    pending.current = true;
    setBusy(action); setError(''); setNotice('');
    try {
      const result = action === 'test' ? await api.testJevConnection()
        : await api.saveJevConnection(action === 'clear' ? { clear_key: true } : { api_key: key });
      setConnection(result);
      if (action !== 'test') { setKey(''); setConfirmClear(false); }
      if (result.error) setError(result.error);
      else setNotice(action === 'test' ? '连接测试通过 · ' + (result.model_resolved || result.model)
        : action === 'clear' ? (result.has_key ? '本地密钥已清除；启动环境凭据仍可用。' : '本地密钥已清除。') : '密钥已保存，尚未验证连接。');
    } catch {
      // Never interpolate a server/transport exception that might echo the draft.
      setError('操作失败，请检查密钥格式、本地服务和目录权限后重试。');
    } finally { pending.current = false; setBusy(''); }
  }

  return <Panel title="JEV 连接">
    <div className="connection-settings">
      <p className="muted">将 JEV 作为可选的结构化判断服务连接。它不是聊天模型，不会改变复盘助手当前的模型选择。</p>
      <div className="row"><strong>TypeSafe · {connection?.model || 'jev-latest'}</strong>
        <Badge kind={connection?.has_key ? 'ok' : 'warn'}>{connection ? (connection.has_key ? '已配置密钥' : '未配置') : '读取中'}</Badge>
      </div>
      <label className="field" htmlFor="jev-api-key"><span>JEV API 密钥</span>
        <input id="jev-api-key" type="password" autoComplete="new-password" spellCheck={false} value={key}
          disabled={Boolean(busy) || !connection} placeholder={connection?.has_key ? '留空保留已保存的密钥' : '粘贴 TypeSafe API 密钥'}
          onChange={event => { setKey(event.target.value); setError(''); setNotice(''); }} />
      </label>
      <p className="muted">密钥仅保存在本机凭据文件，不写入浏览器存储，也不会回显。{connection?.key_source === 'environment' ? '当前使用启动环境中的凭据；清除本地密钥不会删除环境变量。' : ''}</p>
      <div className="row connection-actions">
        <button className="primary" disabled={Boolean(busy) || !key.trim() || !connection} onClick={() => void act('save')}>{busy === 'save' ? '保存中…' : '保存密钥'}</button>
        <button className="ghost" disabled={Boolean(busy) || !connection?.has_key || Boolean(key)} onClick={() => void act('test')}>{busy === 'test' ? '测试中…' : '测试连接'}</button>
        <button className="ghost" disabled={Boolean(busy) || !connection?.has_local_key} onClick={() => setConfirmClear(true)}>清除本地密钥</button>
      </div>
      {confirmClear ? <div className="notice">确认清除本地 JEV 密钥？其他模型凭据不会改变。
        <div className="row"><button className="ghost" disabled={Boolean(busy)} onClick={() => void act('clear')}>确认清除</button><button className="ghost" disabled={Boolean(busy)} onClick={() => setConfirmClear(false)}>取消</button></div>
      </div> : null}
      <small className="muted">测试连接只发送固定示例，不读取交易数据；将产生一次 API 推理请求，可能计费。请先保存修改再测试。</small>
      {notice ? <div className="notice" role="status">{notice}</div> : null}
      {error ? <div className="notice" role="alert">{error}</div> : null}
    </div>
  </Panel>;
}

const labels: Record<string, string> = { healthy: '就绪', configured: '已配置', detected: '已检测到', not_found: '未安装', unavailable: '不可用', unsupported: '不支持' };
type AgentAction = 'apply' | 'dry-run' | 'disable' | 'restore';
const actionLabels: Record<AgentAction, string> = { apply: '应用', 'dry-run': '预览', disable: '停用', restore: '恢复' };

export function AgentIntegrationSettings() {
  const [agents, setAgents] = useState<AgentIntegration[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [confirmation, setConfirmation] = useState<{ agent: AgentIntegration; action: AgentAction } | null>(null);
  const pending = useRef(false);
  async function load() {
    setLoading(true); setError('');
    try { setAgents((await api.agents()).agents); }
    catch { setError('Agent 列表读取失败，请重试。'); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);

  async function act(agent: AgentIntegration, action: AgentAction) {
    if (pending.current) return;
    pending.current = true;
    setBusy(agent.agent_id); setError(''); setNotice('');
    try {
      const result = action === 'disable' ? await api.agentDisable(agent.agent_id)
        : action === 'restore' ? await api.agentRestore(agent.agent_id)
        : await api.agentApply(agent.agent_id, action === 'dry-run');
      setConfirmation(null);
      setNotice(action === 'dry-run' ? `预览完成：${result.agent.label}。尚未写入配置。${result.agent.detail || ''}`
        : `${result.agent.label}：${actionLabels[action]}完成。`);
      // A dry run describes a proposed configuration, not the current status.
      if (action !== 'dry-run') {
        setAgents(previous => previous.map(item => item.agent_id === agent.agent_id ? result.agent : item));
      }
    } catch { setError('操作失败，配置状态尚未确认。请刷新后检查，不要重复应用。'); }
    finally { pending.current = false; setBusy(''); }
  }

  return <Panel title="Agent 集成中心" actions={<button className="ghost" disabled={loading || Boolean(busy)} onClick={() => void load()}>刷新列表</button>}>
    <div className="connection-settings">
      <p className="muted">管理本机编程 Agent 的复盘工具接入。先预览，再确认写入；不会授予下单或撤单权限。</p>
      {loading ? <div role="status">正在读取本机集成…</div> : null}
      {notice ? <div className="notice" role="status">{notice}</div> : null}
      {error ? <div className="notice" role="alert">{error}</div> : null}
      {!loading && !agents.length && !error ? <Empty text="暂无可管理的 Agent" /> : null}
      {agents.map(agent => <section className="integration-card" key={agent.agent_id}>
        <div className="row"><strong>{agent.label}</strong><Badge kind={['healthy', 'configured'].includes(agent.status) ? 'ok' : 'warn'}>{labels[agent.status] || agent.status}</Badge></div>
        <p className="muted">{agent.detail}</p>
        <details><summary>配置位置与管理范围</summary><p className="muted">{agent.config_path || '未检测到配置文件'}</p><code>{(agent.owned_keys || []).join(', ') || '由集成适配器管理'}</code></details>
        <div className="row connection-actions">
          {(Object.keys(actionLabels) as AgentAction[]).map(action => <button key={action} className="ghost"
            disabled={Boolean(busy) || loading || agent.status === 'unsupported'}
            onClick={() => action === 'dry-run' ? void act(agent, action) : setConfirmation({ agent, action })}>{actionLabels[action]}</button>)}
          {busy === agent.agent_id ? <span role="status" className="muted">处理中…</span> : null}
        </div>
        {confirmation?.agent.agent_id === agent.agent_id ? <div className="notice">确认对 {agent.label} 执行{actionLabels[confirmation.action]}？这会修改本机集成配置。
          <div className="row"><button className="primary" disabled={Boolean(busy)} onClick={() => void act(agent, confirmation.action)}>确认{actionLabels[confirmation.action]}</button><button className="ghost" disabled={Boolean(busy)} onClick={() => setConfirmation(null)}>取消</button></div>
        </div> : null}
      </section>)}
    </div>
  </Panel>;
}
