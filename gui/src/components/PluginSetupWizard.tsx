import { useState } from 'react';
import { api } from '../api';
import type { PluginInstallResponse, PluginInstallStep, PluginMarketEntry } from '../types';

interface PluginSetupWizardProps {
  entry: PluginMarketEntry;
  onClose: () => void;
  onSuccess: () => void;
}

type WizardStep = 'permissions' | 'credentials' | 'installing' | 'done' | 'error';

export function PluginSetupWizard({ entry, onClose, onSuccess }: PluginSetupWizardProps) {
  const [step, setStep] = useState<WizardStep>('permissions');
  const [permissionsConfirmed, setPermissionsConfirmed] = useState(false);
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [installSteps, setInstallSteps] = useState<PluginInstallStep[]>([]);
  const [healthResult, setHealthResult] = useState<{ ok: boolean; detail: string } | null>(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const startInstall = async (credsToUse = credentials) => {
    setStep('installing');
    setSubmitting(true);
    setErrorMessage('');
    try {
      const payload = {
        plugin_id: entry.plugin_id,
        permissions_confirmed: true,
        credentials: entry.requires_credentials && Object.keys(credsToUse).length > 0 ? credsToUse : undefined,
      };
      const res: PluginInstallResponse = await api.pluginInstall(payload);
      setInstallSteps(res.steps || []);
      if (res.status === 'ok') {
        setHealthResult(res.health || { ok: true, detail: '健康检查通过' });
        setStep('done');
      } else {
        setHealthResult(res.health || null);
        setErrorMessage(res.error || '安装或健康检查失败');
        setStep('error');
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err));
      setStep('error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleNextFromPermissions = () => {
    if (!permissionsConfirmed) return;
    if (entry.requires_credentials) {
      setStep('credentials');
    } else {
      void startInstall();
    }
  };

  const handleCredentialChange = (key: string, val: string) => {
    setCredentials((prev) => ({ ...prev, [key]: val }));
  };

  const handleRetry = () => {
    void startInstall();
  };

  // The catalog is the source of truth for names and acquisition URLs.
  const credentialRequirements = entry.requires_credentials
    ? (entry.credential_requirements?.length
      ? entry.credential_requirements
      : [{ name: 'API_KEY', label: 'API key', obtain_url: entry.credential_setup_url || entry.docs_url || entry.repo, help: '', required: true, scopes: [] }])
    : [];
  const credentialsValid = credentialRequirements.every((requirement) =>
    !requirement.required || Boolean(credentials[requirement.name]?.trim()),
  );

  return (
    <div className="dsh-modal-backdrop" onClick={step === 'installing' ? undefined : onClose}>
      <div className="dsh-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 580 }}>
        <div className="dsh-modal-head">
          <div className="row" style={{ gap: 8, alignItems: 'center' }}>
            <span className="provider-title">插件安装向导 · {entry.name || entry.plugin_id}</span>
            <span className="mono muted" style={{ fontSize: 11 }}>{entry.plugin_id}</span>
          </div>
          {step !== 'installing' ? (
            <button className="ghost" onClick={onClose} aria-label="关闭向导">✕</button>
          ) : null}
        </div>

        <div className="dsh-modal-body">
          {step === 'permissions' ? (
            <div className="grid" style={{ gap: 14 }}>
              <div className="notice" style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                <div>
                  <strong>只读安全底线：</strong>
                  <span>{entry.safety || 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE'}</span>
                </div>
              </div>

              <div>
                <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>声明能力</div>
                <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
                  {(entry.capabilities || []).map((cap) => (
                    <span className="dsh-cap-tag" key={cap}>{cap}</span>
                  ))}
                </div>
              </div>

              <div>
                <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>网络访问与行为边界</div>
                <div style={{ fontSize: 12, lineHeight: 1.5 }}>
                  <div>联网需求：<strong>{entry.network_required ? '需要网络访问' : '完全离线运行'}</strong></div>
                  <div style={{ marginTop: 4 }}>安全边界：<span className="muted">{entry.boundary}</span></div>
                </div>
              </div>

              <div className="dsh-field" style={{ marginTop: 6 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={permissionsConfirmed}
                    onChange={(e) => setPermissionsConfirmed(e.target.checked)}
                  />
                  <span style={{ fontSize: 12.5, fontWeight: 500 }}>
                    我已阅读并知晓该插件的能力边界，确认授予只读执行权限
                  </span>
                </label>
              </div>
            </div>
          ) : null}

          {step === 'credentials' ? (
            <div className="grid" style={{ gap: 14 }}>
              <div className="muted" style={{ fontSize: 12, lineHeight: 1.6 }}>
                该插件运行需要第三方服务密钥。填写的密钥仅保存在本机 <code>credentials.json</code> 中，不会随复盘记录导出或上传云端。
              </div>

              <div className="dsh-field-group">
                {credentialRequirements.map((requirement) => (
                  <div className="dsh-field" key={requirement.name}>
                    <label>{requirement.label || requirement.name}（{requirement.name}，不回显明文）</label>
                    {requirement.obtain_url ? (
                      <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
                        <a href={requirement.obtain_url} target="_blank" rel="noreferrer" style={{ color: 'var(--color-accent)', textDecoration: 'underline' }}>
                          前往官方页面获取
                        </a>
                      </div>
                    ) : null}
                    {requirement.help ? <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>{requirement.help}</div> : null}
                    <input
                      type="password"
                      autoComplete="off"
                      placeholder={'请输入 ' + requirement.name}
                      value={credentials[requirement.name] || ''}
                      onChange={(e) => handleCredentialChange(requirement.name, e.target.value)}
                    />
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {step === 'installing' ? (
            <div className="grid" style={{ gap: 14, textAlign: 'center', padding: '20px 0' }}>
              <div style={{ fontSize: 14, fontWeight: 500 }}>正在安装与验证插件...</div>
              <div className="muted" style={{ fontSize: 12 }}>
                正在执行依赖拉取、环境隔离配置与健康检查探针，请稍候。
              </div>
              {installSteps.length > 0 ? (
                <div className="checklist" style={{ textAlign: 'left', marginTop: 10 }}>
                  {installSteps.map((s, idx) => (
                    <div className="checklist-row" key={idx} style={{ fontSize: 12 }}>
                      <span>{s.status === 'ok' ? '✓' : s.status === 'failed' ? '✕' : '○'} {s.step}</span>
                      <span className="muted">{s.detail}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {step === 'done' ? (
            <div className="grid" style={{ gap: 14 }}>
              <div className="notice" style={{ borderLeftColor: 'var(--pos)' }}>
                <strong>安装成功！</strong> 插件已成功注册并在工作台中启用。
              </div>

              {healthResult ? (
                <div style={{ fontSize: 12 }}>
                  <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>健康探针结果</div>
                  <div>{healthResult.detail}</div>
                </div>
              ) : null}

              {installSteps.length > 0 ? (
                <div>
                  <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>安装步骤执行记录</div>
                  <div className="checklist">
                    {installSteps.map((s, idx) => (
                      <div className="checklist-row" key={idx} style={{ fontSize: 11.5 }}>
                        <span>✓ {s.step}</span>
                        <span className="muted">{s.detail}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {step === 'error' ? (
            <div className="grid" style={{ gap: 14 }}>
              <div className="notice" role="alert" style={{ borderLeftColor: 'var(--neg)' }}>
                <strong>安装未完成：</strong>{errorMessage}
              </div>

              {healthResult && !healthResult.ok ? (
                <div style={{ fontSize: 12 }}>
                  <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>健康检查失败信息</div>
                  <div style={{ color: 'var(--neg)' }}>{healthResult.detail}</div>
                </div>
              ) : null}

              {installSteps.length > 0 ? (
                <div>
                  <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>已执行步骤</div>
                  <div className="checklist">
                    {installSteps.map((s, idx) => (
                      <div className="checklist-row" key={idx} style={{ fontSize: 11.5 }}>
                        <span>
                          {s.status === 'ok' ? '✓' : s.status === 'failed' ? '✕' : '○'} {s.step}
                        </span>
                        <span className="muted">{s.detail}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="dsh-modal-actions">
          {step === 'permissions' ? (
            <>
              <button className="ghost" onClick={onClose}>取消</button>
              <button
                className="primary"
                disabled={!permissionsConfirmed}
                onClick={handleNextFromPermissions}
              >
                {entry.requires_credentials ? '下一步：填写密钥' : '下一步：开始安装'}
              </button>
            </>
          ) : null}

          {step === 'credentials' ? (
            <>
              <button className="ghost" onClick={() => setStep('permissions')}>上一步</button>
              <button className="primary" disabled={!credentialsValid || submitting} onClick={() => void startInstall()}>
                开始安装
              </button>
            </>
          ) : null}

          {step === 'installing' ? (
            <button className="primary" disabled>
              正在安装…
            </button>
          ) : null}

          {step === 'done' ? (
            <button
              className="primary"
              onClick={() => {
                onSuccess();
                onClose();
              }}
            >
              完成
            </button>
          ) : null}

          {step === 'error' ? (
            <>
              <button className="ghost" onClick={onClose}>关闭</button>
              <button className="primary" onClick={handleRetry} disabled={submitting}>
                重试安装
              </button>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
