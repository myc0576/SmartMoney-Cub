import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { AgentIntegration } from '../types';
import { Panel } from './common';

const labels: Record<string, string> = { healthy: '运行正常', configured: '已配置', detected: '已检测到', not_found: '未安装', unavailable: '不可用', unsupported: '暂不支持' };
type Action = 'preview' | 'apply' | 'disable' | 'restore';

export function AgentIntegrationsSettings() {
  const [agents, setAgents] = useState<AgentIntegration[]>([]);
  const [pending, setPending] = useState('scan');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const locked = useRef(false);
  const alive = useRef(true);
  async function scan() {
    const response = await api.agents();
    if (alive.current) setAgents(response.agents);
  }
  useEffect(() => {
    alive.current = true;
    scan().catch(e => { if (alive.current) setError(e instanceof Error ? e.message : '扫描失败'); })
      .finally(() => { if (alive.current) setPending(''); });
    return () => { alive.current = false; };
  }, []);

  async function act(id: string, action: Action | 'scan') {
    if (locked.current || pending) return;
    if (action === 'restore' && !window.confirm('恢复该 Agent 已备份的配置？请先确认没有需要保留的新修改。')) return;
    locked.current = true; setPending(id + ':' + action); setNotice(''); setError('');
    try {
      if (action !== 'scan') {
        const response = action === 'preview' ? await api.agentApply(id, true)
          : action === 'apply' ? await api.agentApply(id, false)
          : action === 'disable' ? await api.agentDisable(id) : await api.agentRestore(id);
        if (alive.current) setNotice(response.agent.detail || (action === 'preview' ? '预览完成，未写入配置。' : '操作完成。'));
      }
      await scan();
    } catch (e) { if (alive.current) setError(e instanceof Error ? e.message : '操作失败，请重试'); }
    finally { locked.current = false; if (alive.current) setPending(''); }
  }

  return <Panel title="Agent 集成中心">
    <div className="integration-intro"><p>连接本机编程 Agent。先预览配置，再决定是否应用；交易执行权限始终关闭。</p>
      <button className="ghost" disabled={Boolean(pending)} onClick={() => void act('', 'scan')}>{pending === 'scan' ? '扫描中…' : '重新扫描'}</button>
    </div>
    {error ? <div className="notice" role="alert">{error}</div> : null}
    {notice ? <div className="notice" role="status">{notice}</div> : null}
    {!pending && !error && agents.length === 0 ? <p className="muted">尚未检测到可管理的 Agent。安装后可重新扫描。</p> : null}
    <div className="integration-grid">
      {agents.map(agent => <section className="integration-card" key={agent.agent_id} aria-label={agent.label}>
        <div className="integration-card-head"><strong>{agent.label}</strong><span className="tag">{labels[agent.status] || agent.status}</span></div>
        <p className="muted">{agent.detail}</p>
        {agent.config_path ? <details><summary>配置位置</summary><code>{agent.config_path}</code></details> : null}
        <div className="row integration-actions">
          <button className="ghost" disabled={Boolean(pending)} onClick={() => void act(agent.agent_id, 'preview')}>预览</button>
          <button className="primary" disabled={Boolean(pending)} onClick={() => void act(agent.agent_id, 'apply')}>应用</button>
          <button className="ghost" disabled={Boolean(pending)} onClick={() => void act(agent.agent_id, 'disable')}>停用</button>
          <button className="ghost" disabled={Boolean(pending)} onClick={() => void act(agent.agent_id, 'restore')}>恢复</button>
        </div>
        {pending.startsWith(agent.agent_id + ':') ? <small role="status">正在处理…</small> : null}
      </section>)}
    </div>
  </Panel>;
}
