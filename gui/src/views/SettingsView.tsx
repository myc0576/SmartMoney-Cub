import { useEffect, useState } from 'react';
import { api } from '../api';
import type { AuditRecord, Meta, ProviderView } from '../types';
import { Badge, Panel } from '../components/common';

export function SettingsView({ meta, onMetaChange }: { meta: Meta | null; onMetaChange: () => void }) {
  const [providers, setProviders] = useState<ProviderView[]>([]);
  const [audits, setAudits] = useState<AuditRecord[]>([]);
  const [doctor, setDoctor] = useState<Record<string, any> | null>(null);
  const [keyInput, setKeyInput] = useState<Record<string, string>>({});
  const [baseInput, setBaseInput] = useState<Record<string, string>>({});
  const [modelInput, setModelInput] = useState<Record<string, string>>({});
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    const settings = await api.settings();
    setProviders(settings.providers as ProviderView[]);
    setAudits((await api.audit()).audits);
    setDoctor(await api.doctor());
  };

  useEffect(() => { void load(); }, []);

  const save = async (providerId: string) => {
    setStatus('');
    setError('');
    try {
      await api.updateSettings({
        providers: {
          [providerId]: {
            api_key: keyInput[providerId] || undefined,
            base_url: baseInput[providerId] ?? undefined,
            default_model: modelInput[providerId] ?? undefined,
          },
        },
      });
      setKeyInput((prev) => ({ ...prev, [providerId]: '' }));
      setStatus('已保存「' + providerId + '」的设置。密钥只写入本机凭据文件，界面不会回显。');
      await load();
      onMetaChange();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : String(saveError));
    }
  };

  const test = async (providerId: string) => {
    setStatus('');
    setError('');
    try {
      const result = await api.testProvider({ provider_id: providerId });
      if (result.status === 'ok') {
        setStatus('「' + providerId + '」连接成功' + (result.models?.length ? '，可用模型 ' + result.models.length + ' 个' : '。'));
      } else {
        setError('「' + providerId + '」连接失败：' + result.error);
      }
    } catch (testError) {
      setError(testError instanceof Error ? testError.message : String(testError));
    }
  };

  return (
    <div className="grid" style={{ gap: 14 }}>
      <Panel title="隐私与脱敏">
        <div className="grid" style={{ gap: 8 }}>
          <div>外发策略：<strong>{(meta?.redaction_policy || 'redaction.v1')}</strong></div>
          <div className="muted">
            发送给模型的字段在离开本机前会被替换：账号与姓名变成别名，证券代码与组合名变成设备内稳定的哈希别名，
            精确数量与金额变成区间，精确时间变成 15 分钟时段。截图、PDF、CSV 原文永远不进入请求。
          </div>
          <div className="muted">
            每次外发都会在本地写入一条审计记录，只记录「发送了哪些字段」和脱敏统计，不记录密钥。
          </div>
          <div className="row">
            <span>本地识别引擎：</span>
            {meta?.engine?.rapidocr ? <Badge kind="ok">已安装</Badge> : <Badge kind="warn">未安装</Badge>}
            <span className="muted">截图与扫描 PDF 需要它，安装命令：pip install "smartmoney-cub-harness[ocr]"</span>
          </div>
        </div>
      </Panel>

      <Panel title="模型 Provider">
        <div className="grid" style={{ gap: 12 }}>
          {providers.map((provider) => (
            <div key={provider.provider_id} className="panel" style={{ background: '#12161d' }}>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <div>
                  <strong>{provider.label}</strong>
                  <span className="muted" style={{ marginLeft: 8, fontSize: 11 }}>{provider.provider_id}</span>
                </div>
                <div className="row">
                  {provider.has_key ? <Badge kind="ok">已配置密钥</Badge> : <Badge kind="warn">未配置密钥</Badge>}
                  <span className="muted" style={{ fontSize: 11 }}>来源 {provider.key_source}</span>
                </div>
              </div>
              <div className="muted" style={{ fontSize: 11, margin: '6px 0' }}>{provider.description}</div>
              {provider.base_url ? <div className="muted" style={{ fontSize: 11 }}>地址：{provider.base_url}</div> : null}
              <div className="row" style={{ marginTop: 8 }}>
                <div className="field">
                  <label>API Key</label>
                  <input
                    type="password"
                    style={{ width: 220 }}
                    value={keyInput[provider.provider_id] || ''}
                    placeholder={provider.has_key ? '已保存（留空表示不修改）' : '粘贴密钥'}
                    onChange={(event) => setKeyInput((prev) => ({ ...prev, [provider.provider_id]: event.target.value }))}
                  />
                </div>
                <div className="field">
                  <label>Base URL</label>
                  <input
                    style={{ width: 260 }}
                    value={baseInput[provider.provider_id] ?? (provider.stored_base_url || provider.base_url)}
                    onChange={(event) => setBaseInput((prev) => ({ ...prev, [provider.provider_id]: event.target.value }))}
                  />
                </div>
                <div className="field">
                  <label>默认模型</label>
                  <input
                    style={{ width: 180 }}
                    value={modelInput[provider.provider_id] ?? (provider.stored_model || provider.default_model)}
                    onChange={(event) => setModelInput((prev) => ({ ...prev, [provider.provider_id]: event.target.value }))}
                  />
                </div>
                <button className="primary" onClick={() => save(provider.provider_id)}>保存</button>
                <button className="ghost" onClick={() => test(provider.provider_id)}>测试连接</button>
                {provider.has_key ? (
                  <button
                    className="ghost"
                    onClick={async () => {
                      await api.updateSettings({ providers: { [provider.provider_id]: { clear_key: true } } });
                      setStatus('已清除「' + provider.provider_id + '」的本地密钥。');
                      await load();
                      onMetaChange();
                    }}
                  >
                    清除密钥
                  </button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
        {status ? <div className="muted" style={{ marginTop: 10 }}>{status}</div> : null}
        {error ? <div className="notice" style={{ marginTop: 10 }}>{error}</div> : null}
      </Panel>

      <Panel title={'外发审计（最近 ' + audits.length + ' 条）'}>
        {audits.length === 0 ? <div className="muted">还没有向外部模型发送过请求。本地离线复盘不会产生外发记录。</div> : (
          <div className="scroll-x">
            <table>
              <thead><tr><th>时间</th><th>Provider</th><th>模型</th><th>字段数</th><th>脱敏</th><th>结果</th></tr></thead>
              <tbody>
                {audits.map((audit) => (
                  <tr key={audit.audit_id}>
                    <td className="muted">{audit.created_at}</td>
                    <td>{audit.provider_id}</td>
                    <td className="muted">{audit.model || '—'}</td>
                    <td className="num">{audit.sent_keys.length}</td>
                    <td className="muted">{String(audit.redaction_summary?.total ?? 0)} 处替换</td>
                    <td>{audit.blocked ? <Badge kind="error">已阻断</Badge> : <Badge kind="ok">已发送</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="本地诊断">
        {doctor ? (
          <table>
            <thead><tr><th>检查项</th><th>状态</th><th>说明</th></tr></thead>
            <tbody>
              {(doctor.checks as { name: string; status: string; detail: string }[]).map((check) => (
                <tr key={check.name}>
                  <td>{check.name}</td>
                  <td>{check.status === 'ok' ? <Badge kind="ok">正常</Badge> : <Badge kind="warn">{check.status}</Badge>}</td>
                  <td className="muted" style={{ whiteSpace: 'normal' }}>{check.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="muted">加载中…</div>}
      </Panel>
    </div>
  );
}

