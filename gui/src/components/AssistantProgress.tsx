import { useEffect, useState } from 'react';

export type RunPhase = 'connecting' | 'tools' | 'writing' | 'completed' | 'stopped' | 'failed';

/** Observable run activity, not a reconstruction of private model reasoning. */
export function AssistantProgress({ phase, label, startedAt, finishedAt, toolCount }: {
  phase: RunPhase; label: string; startedAt: number; finishedAt: number | null; toolCount: number;
}) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (finishedAt !== null) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt, finishedAt]);
  const seconds = Math.max(0, Math.floor(((finishedAt ?? now) - startedAt) / 1000));
  const elapsed = `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`;
  const running = finishedAt === null;
  return <section className={'assistant-run ' + (running ? 'is-running' : '')} data-phase={phase} aria-label="本轮运行状态">
    <div className="assistant-run-heading">
      <span className="run-indicator" aria-hidden="true">{running ? <><i /><i /><i /></> : phase === 'completed' ? '✓' : phase === 'failed' ? '!' : '■'}</span>
      <strong role="status" aria-live="polite">{label}</strong>
      <time className="run-elapsed" aria-label={`已用时 ${seconds} 秒`}>{elapsed}</time>
    </div>
    <div className="run-stages" aria-hidden="true">
      <span className={phase === 'connecting' ? 'active' : ''}>请求</span>
      {toolCount > 0 ? <><span className="run-stage-line" /><span className={phase === 'tools' ? 'active' : ''}>工具 · {toolCount}</span></> : null}
      <span className="run-stage-line" /><span className={phase === 'writing' || phase === 'completed' ? 'active' : ''}>回复</span>
    </div>
    <div className="run-caption">{running ? '仅展示实际运行事件 · 可随时停止' : phase === 'completed' ? '本轮回复已接收' : '已保留收到的内容；停止不代表远端计算立即终止'}</div>
  </section>;
}
