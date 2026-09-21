import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { JevConnection, JevConnectionTest } from '../types';
import { Panel } from './common';

export function JevConnectionSettings() {
  const [config, setConfig] = useState<JevConnection | null>(null);
  const [key, setKey] = useState('');
  const [pending, setPending] = useState('加载');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [result, setResult] = useState<JevConnectionTest | null>(null);
  const locked = useRef(false);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    api.jevConnection().then(value => { if (alive.current) setConfig(value); })
      .catch(e => { if (alive.current) setError(e instanceof Error ? e.message : '读取连接设置失败'); })
      .finally(() => { if (alive.current) setPending(''); });
    return () => { alive.current = false; };
  }, []);

  async function act(action: '保存' | '清除' | '测试') {
    if (locked.current || pending) return;
    if (action === '清除' && !window.confirm('清除本机保存的 JEV 密钥？环境变量中的密钥不会被删除。')) return;
    locked.current = true; setPending(action); setError(''); setNotice(''); setResult(null);
    try {
      if (action === '测试') {
        const tested = await api.testJevConnection();
        if (!alive.current) return;
        setResult(tested);
        if (!tested.connected) setError(tested.error || '连接测试未通过');
      } else {
        const updated = await api.saveJevConnection(action === '清除' ? { clear_key: true } : { api_key: key });
        if (!alive.current) return;
        setConfig(updated); setKey('');
        setNotice(action === '保存' ? '密钥已保存，尚未验证连接。' : updated.has_key ? '本机密钥已清除；仍在使用环境变量中的密钥。' : '本机密钥已清除。');
      }
    } catch (e) { if (alive.current) setError(e instanceof Error ? e.message : '操作失败，请重试'); }
    finally { locked.current = false; if (alive.current) setPending(''); }
  }

  return <Panel title="JEV 连接">
    <div className="integration-intro">
      <p>将 JEV 作为可选的结构化判断服务连接。不改变复盘助手的聊天模型，也不会自动发送交易记录。</p>
      <span className="tag">TypeSafe · {config?.model_requested || 'jev-latest'}</span>
      <span className="tag">{config?.has_key ? '已配置 · 待按需测试' : '未配置'}</span>
    </div>
    {error ? <div className="notice" role="alert">{error}</div> : null}
    {notice ? <div className="notice" role="status">{notice}</div> : null}
    {result?.connected ? <div className="notice" role="status">连接测试成功 · {result.model_resolved || 'JEV'}<br /><small>测试时间：{new Date(result.checked_at).toLocaleString()}。这是本次请求的结果，不代表服务持续在线。</small></div> : null}
    <div className="field integration-key-field">
      <label htmlFor="jev-api-key">JEV API 密钥</label>
      <input id="jev-api-key" type="password" autoComplete="new-password" autoCapitalize="off" spellCheck={false}
        value={key} disabled={Boolean(pending) || !config}
        placeholder={config?.has_key ? '已保存的密钥不回显；输入新密钥可替换' : '仅输入密钥本身'}
        onChange={e => { setKey(e.target.value); setResult(null); setNotice(''); }} />
      <small className="muted">{config?.key_source === 'environment' ? '当前使用 TYPESAFE_API_KEY 环境变量。' : '密钥仅保存在本机状态目录，不写入浏览器持久存储。'}</small>
    </div>
    <div className="row integration-actions">
      <button className="primary" disabled={Boolean(pending) || !config || !key.trim()} onClick={() => void act('保存')}>{pending === '保存' ? '保存中…' : '保存密钥'}</button>
      <button className="ghost" disabled={Boolean(pending) || !config?.has_key || Boolean(key)} onClick={() => void act('测试')}>{pending === '测试' ? '测试中…' : '测试连接'}</button>
      <button className="ghost" disabled={Boolean(pending) || !config?.has_local_key} onClick={() => void act('清除')}>清除本机密钥</button>
    </div>
    <p className="muted integration-help">保存后才能测试连接。测试会向 TypeSafe 发送一个不含交易数据的固定问题，可能消耗少量 API 额度；不会自动重试。</p>
  </Panel>;
}
