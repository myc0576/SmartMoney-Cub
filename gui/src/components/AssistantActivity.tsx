import { useEffect, useState } from 'react';
import './assistant-activity.css';

export type ActivityPhase = 'connecting' | 'thinking' | 'tools' | 'responding' | 'complete' | 'error' | 'stopping' | 'stopped';
export interface Activity { phase: ActivityPhase; startedAt: number; finishedAt?: number }
export interface ToolCall { callId: string; name: string; arguments: unknown; result?: unknown }
const titles: Record<ActivityPhase, string> = {
  connecting: '正在连接模型', thinking: '证据已返回，等待回复', tools: '正在读取证据', responding: '正在生成回复',
  complete: '本轮完成', error: '本轮未完成', stopping: '正在停止', stopped: '已停止',
};

export function AssistantActivity({ activity, calls }: { activity: Activity; calls: ToolCall[] }) {
  const [now, setNow] = useState(Date.now());
  const running = activity.finishedAt === undefined;
  useEffect(() => {
    if (!running) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running, activity.startedAt]);
  const seconds = Math.max(0, Math.floor(((activity.finishedAt ?? now) - activity.startedAt) / 1000));
  const finished = calls.filter(call => call.result !== undefined).length;
  return <section className={'assistant-activity ' + activity.phase} aria-label="本轮执行状态">
    <div className="activity-header">
      <span className={'activity-indicator' + (running ? ' running' : '')} aria-hidden="true">{running ? '' : activity.phase === 'complete' ? '✓' : activity.phase === 'error' ? '!' : '■'}</span>
      <strong role="status" aria-live="polite">{titles[activity.phase]}</strong>
      <span className="activity-time" aria-label={'已用时 ' + seconds + ' 秒'}>{seconds}s</span>
    </div>
    <p className="activity-caption">{activity.phase === 'connecting' ? '正在准备连接，等待模型响应。'
      : activity.phase === 'error' ? '已保留收到的内容，请检查错误提示后重试。'
      : activity.phase === 'stopped' ? '已保留本轮内容，可继续提问。'
      : activity.phase === 'complete' ? '本轮响应已结束。'
      : '仅展示实际执行事件，不代表模型内部思维。'}</p>
    {calls.length ? <details className="activity-tools">
      <summary>工具记录 · {finished}/{calls.length} 已返回</summary>
      {calls.map(call => <details className="activity-tool" key={call.callId}>
        <summary><span>{call.name}</span><small>{call.result !== undefined ? '已返回' : running ? '执行中' : '未返回'}</small></summary>
        <pre>{JSON.stringify({ arguments: call.arguments, result: call.result }, null, 2)}</pre>
      </details>)}
    </details> : null}
  </section>;
}
