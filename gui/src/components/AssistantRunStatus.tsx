import { useEffect, useState } from 'react';
import { describeRun, type RunPhase } from './assistantRun';
import './assistantRun.css';

export function AssistantRunStatus({ phase, startedAt, endedAt, calls, returned }: {
  phase: RunPhase; startedAt: number; endedAt: number | null; calls: number; returned: number;
}) {
  const [now, setNow] = useState(Date.now());
  const running = phase === 'connecting' || phase === 'tools' || phase === 'writing';
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running]);
  const elapsed = Math.max(0, Math.floor(((endedAt ?? now) - startedAt) / 1000));
  return (
    <div className={'assistant-run-status ' + (running ? 'running' : phase)}>
      <div className="assistant-run-title" role="status" aria-live="polite" aria-atomic="true">
        <span className="assistant-run-indicator" aria-hidden="true">{running ? '' : phase === 'error' ? '!' : '—'}</span>
        <strong>{describeRun(phase, calls, returned)}</strong>
      </div>
      <div className="assistant-run-meta">
        <span aria-label={`已用时 ${elapsed} 秒`}>{elapsed} 秒</span>
        <span>{running ? '可随时停止' : '可展开工具卡查看本轮记录'}</span>
      </div>
      {phase === 'connecting' && calls === 0 ? <p>等待模型响应；此处仅展示运行状态，不模拟分析过程。</p> : null}
    </div>
  );
}
