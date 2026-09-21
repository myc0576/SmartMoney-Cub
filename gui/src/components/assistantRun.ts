/** Observable transport/tool states, not a model's private reasoning. */
export type RunPhase = 'connecting' | 'tools' | 'writing' | 'stopped' | 'error' | 'finished';

export function shouldSendOnEnter(key: string, shift: boolean, composing: boolean, keyCode: number): boolean {
  return key === 'Enter' && !shift && !composing && keyCode !== 229;
}

export function shouldFollowOutput(scrollHeight: number, clientHeight: number, scrollTop: number): boolean {
  return scrollHeight - clientHeight - scrollTop < 64;
}

export function describeRun(phase: RunPhase, calls: number, returned: number): string {
  if (phase === 'tools') return `正在处理工具 · 已返回 ${returned} / ${calls}`;
  if (phase === 'writing') return '正在生成回复';
  if (phase === 'stopped') return '已停止接收 · 保留本轮内容';
  if (phase === 'error') return '本轮未完成';
  if (phase === 'finished') return '本轮连接已结束';
  return '正在连接模型';
}
