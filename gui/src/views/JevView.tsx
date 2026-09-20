import { useEffect, useState } from 'react';
import { api } from '../api';
import type { AgentIntegration, JevStatusResponse, JevTrackInfo } from '../types';
import { Badge, Empty, Kpi, Panel } from '../components/common';

const TRACK_LABELS: Record<string, string> = {
  'trading-review': '交易复盘 (Trading Review)',
  'financial-filings': '财务财报 (Financial Filings)',
  'industry-events': '行业事件 (Industry Events)',
  'macro-policy': '宏观政策 (Macro Policy)',
};

const AGENT_STATUS_LABELS: Record<string, { label: string; kind: 'ok' | 'warn' | 'error' }> = {
  healthy: { label: '正常就绪 (healthy)', kind: 'ok' },
  configured: { label: '已配置 (configured)', kind: 'ok' },
  detected: { label: '已检测到 (detected)', kind: 'warn' },
  not_found: { label: '未安装 (not_found)', kind: 'warn' },
  unavailable: { label: '不可用 (unavailable)', kind: 'error' },
  unsupported: { label: '不支持 (unsupported)', kind: 'error' },
};

export function JevView() {
  const [status, setStatus] = useState<JevStatusResponse | null>(null);
  const [tracks, setTracks] = useState<JevTrackInfo[]>([]);
  const [agents, setAgents] = useState<AgentIntegration[]>([]);
  const [selectedTrack, setSelectedTrack] = useState<string>('trading-review');
  const [loading, setLoading] = useState(false);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setActionError(null);
    try {
      const [statusRes, tracksRes, agentsRes] = await Promise.all([
        api.jevStatus().catch((e) => {
          console.error('Failed to load jev status', e);
          return null;
        }),
        api.jevTracks().catch((e) => {
          console.error('Failed to load jev tracks', e);
          return null;
        }),
        api.agents().catch((e) => {
          console.error('Failed to load agents', e);
          return null;
        }),
      ]);

      if (statusRes) setStatus(statusRes);
      if (tracksRes?.tracks) setTracks(tracksRes.tracks);
      if (agentsRes?.agents) setAgents(agentsRes.agents);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const handleAgentAction = async (agentId: string, action: 'apply' | 'dry-run' | 'disable' | 'restore') => {
    setActionNotice(null);
    setActionError(null);
    try {
      let res;
      if (action === 'apply') {
        res = await api.agentApply(agentId, false);
        setActionNotice(`已成功应用 Agent 集成配置: ${res.agent.label}`);
      } else if (action === 'dry-run') {
        res = await api.agentApply(agentId, true);
        setActionNotice(`[试运行] 模拟应用配置成功: ${res.agent.label}`);
      } else if (action === 'disable') {
        res = await api.agentDisable(agentId);
        setActionNotice(`已停用 Agent 集成: ${res.agent.label}`);
      } else if (action === 'restore') {
        res = await api.agentRestore(agentId);
        setActionNotice(`已恢复 Agent 原始配置: ${res.agent.label}`);
      }
      const fresh = await api.agents();
      setAgents(fresh.agents);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  };

  const currentTrack = tracks.find((t) => t.track === selectedTrack) || tracks[0];

  return (
    <div className="jev-view" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Top Banner with Safety Declaration */}
      <div className="banner" style={{ background: 'var(--panel)', border: '1px solid var(--border)', padding: '10px 14px', borderRadius: 'var(--radius)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <div>
            <strong style={{ fontSize: 13 }}>Jev 审方与多 Agent 集成中心</strong>
            <span className="muted" style={{ marginLeft: 12, fontSize: 11 }}>四赛道审方问题包 · 离线语义评测 · 只读审计安全门禁</span>
          </div>
          <Badge kind="ok">{status?.safety || 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE'}</Badge>
        </div>
      </div>

      {actionNotice ? (
        <div className="banner" style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)', padding: '8px 12px', borderRadius: 'var(--radius)', color: 'var(--text)' }}>
          {actionNotice}
        </div>
      ) : null}

      {actionError ? (
        <div className="banner" style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', padding: '8px 12px', borderRadius: 'var(--radius)', color: 'var(--text)' }}>
          {actionError}
        </div>
      ) : null}

      {/* KPI Cards */}
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
        <Kpi
          label="引擎身份 (Engine)"
          value={status?.engine || 'jev'}
          note="Jev 审方语义推理引擎"
        />
        <Kpi
          label="后端服务商 (Provider)"
          value={status?.provider_id || '—'}
          note={status?.available ? '服务商连接就绪' : '当前无可用凭据'}
        />
        <Kpi
          label="请求模型 (Model Requested)"
          value={status?.model_requested || '—'}
          note="配置的推理模型名称"
        />
        <Kpi
          label="解析模型 (Model Resolved)"
          value={status?.model_resolved || '— (未就绪)'}
          note={status?.available ? '经底层健康探测确认' : status?.reason || '无解析实例'}
          tone={status?.available ? 'ok' : 'warn'}
        />
      </div>

      {/* Engine Status & Backends Panel */}
      <Panel
        title="后端诊断与模型真实性 (Engine & Backends)"
        actions={
          <button className="ghost" onClick={() => void loadData()} disabled={loading}>
            {loading ? '检查中...' : '刷新状态'}
          </button>
        }
      >
        <div style={{ marginBottom: 12, color: 'var(--muted)', fontSize: 12 }}>
          本产品严格遵守透明原则：界面绝不伪装 Jev 为活跃状态。实际推理后端必须如实呈现所请求及解析出的真实模型与供应商。
        </div>

        {status?.backends ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>后端通道</th>
                  <th>提供方 (Provider)</th>
                  <th>请求模型</th>
                  <th>解析模型</th>
                  <th>可用状态</th>
                  <th>诊断原因 / 备注</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(status.backends).map(([key, backend]) => (
                  <tr key={key}>
                    <td><code>{backend.backend_id}</code></td>
                    <td>{backend.provider_id}</td>
                    <td><code>{backend.model_requested}</code></td>
                    <td>{backend.model_resolved ? <code>{backend.model_resolved}</code> : <span className="muted">—</span>}</td>
                    <td>
                      <Badge kind={backend.available ? 'ok' : 'warn'}>
                        {backend.available ? '可用 (available)' : '不可用 (unavailable)'}
                      </Badge>
                    </td>
                    <td>
                      {backend.reason ? (
                        <span style={{ color: backend.available ? 'var(--text)' : 'var(--muted)' }}>
                          {backend.reason === 'missing_credential' ? '缺少 API 密钥 (missing_credential)' : backend.reason}
                        </span>
                      ) : (
                        <span className="muted">就绪</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty text="未获取到底层后端诊断信息" />
        )}
      </Panel>

      {/* Four Track Question Packs Panel */}
      <Panel title="四赛道离线审方问题包 (Track Question Packs)">
        <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
          {tracks.map((t) => (
            <button
              key={t.track}
              className={selectedTrack === t.track ? 'primary' : 'ghost'}
              onClick={() => setSelectedTrack(t.track)}
            >
              {TRACK_LABELS[t.track] || t.track} ({t.question_count} 问 · {t.case_count} 例)
            </button>
          ))}
        </div>

        {currentTrack ? (
          <div>
            <div style={{ display: 'flex', gap: 16, marginBottom: 12, fontSize: 12, color: 'var(--muted)' }}>
              <span>赛道 ID: <code>{currentTrack.track}</code></span>
              <span>结构化问题数: <strong>{currentTrack.question_count}</strong></span>
              <span>离线评测样本量: <strong>{currentTrack.case_count}</strong></span>
            </div>

            {currentTrack.questions && currentTrack.questions.length > 0 ? (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th style={{ width: '22%' }}>问题 ID</th>
                      <th style={{ width: '12%' }}>评估类型</th>
                      <th>提示词 (Prompt)</th>
                      <th style={{ width: '30%' }}>判定选项 / 取值范围</th>
                    </tr>
                  </thead>
                  <tbody>
                    {currentTrack.questions.map((q) => (
                      <tr key={q.question_id}>
                        <td><code>{q.question_id}</code></td>
                        <td>
                          <Badge kind="ok">{q.kind}</Badge>
                        </td>
                        <td>{q.prompt}</td>
                        <td>
                          {q.choices ? (
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                              {q.choices.map((c) => (
                                <code key={c} style={{ fontSize: 11 }}>{c}</code>
                              ))}
                            </div>
                          ) : q.scale_min !== null && q.scale_min !== undefined ? (
                            <span>[{q.scale_min}, {q.scale_max}]</span>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty text="该赛道暂无问题包定义" />
            )}
          </div>
        ) : (
          <Empty text="加载赛道信息中..." />
        )}
      </Panel>

      {/* Agent Integration Center Panel */}
      <Panel title="Agent 集成中心 (Agent Integration Center)">
        <div style={{ marginBottom: 12, color: 'var(--muted)', fontSize: 12 }}>
          支持与常用 AI 编程 Agent (Codex CLI, Claude Code, DeepSeek Harness, OpenCode, Gemini CLI, Pi) 的配置管理与双向桥接。系统仅管理自身配置片段，不影响用户原有配置。
        </div>

        {agents.length > 0 ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Agent 名称</th>
                  <th>集成标识</th>
                  <th>当前状态</th>
                  <th>配置文件路径</th>
                  <th>详情说明</th>
                  <th style={{ textAlign: 'right' }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {agents.map((agent) => {
                  const statusInfo = AGENT_STATUS_LABELS[agent.status] || { label: agent.status, kind: 'warn' };
                  return (
                    <tr key={agent.agent_id}>
                      <td><strong>{agent.label}</strong></td>
                      <td><code>{agent.agent_id}</code></td>
                      <td>
                        <Badge kind={statusInfo.kind}>{statusInfo.label}</Badge>
                      </td>
                      <td>
                        <small className="muted" style={{ wordBreak: 'break-all' }}>
                          {agent.config_path || '—'}
                        </small>
                      </td>
                      <td>
                        <span style={{ fontSize: 12 }}>{agent.detail}</span>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                          <button
                            className="ghost"
                            style={{ fontSize: 11, padding: '3px 6px' }}
                            onClick={() => void handleAgentAction(agent.agent_id, 'dry-run')}
                            title="试运行，预览配置变化"
                          >
                            试运行
                          </button>
                          <button
                            className="ghost"
                            style={{ fontSize: 11, padding: '3px 6px' }}
                            onClick={() => void handleAgentAction(agent.agent_id, 'apply')}
                            title="注入 SmartMoney-Cub 审方配置"
                          >
                            应用
                          </button>
                          <button
                            className="ghost"
                            style={{ fontSize: 11, padding: '3px 6px' }}
                            onClick={() => void handleAgentAction(agent.agent_id, 'disable')}
                            title="临时停用集成配置"
                          >
                            停用
                          </button>
                          <button
                            className="ghost"
                            style={{ fontSize: 11, padding: '3px 6px' }}
                            onClick={() => void handleAgentAction(agent.agent_id, 'restore')}
                            title="完全移除配置片段，恢复原始设置"
                          >
                            恢复
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty text="未扫描到已安装或支持的 Agent 环境" />
        )}
      </Panel>
    </div>
  );
}
