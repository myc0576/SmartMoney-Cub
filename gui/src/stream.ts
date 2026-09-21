export interface StreamHandlers {
  onEvent: (event: Record<string, any>) => void;
  onError: (message: string) => void;
  onDone: () => void;
  signal?: AbortSignal;
}

/** Decode complete SSE frames; transport failure is never completion. */
export async function consumeStream(url: string, payload: Record<string, unknown>, handlers: StreamHandlers): Promise<void> {
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  let completed = false;
  try {
    if (handlers.signal?.aborted) return;
    const response = await fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload), signal: handlers.signal,
    });
    if (!response.ok || !response.body) {
      throw new Error('连接失败（HTTP ' + response.status + '），请检查模型配置或重试。');
    }
    reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    const emit = (frame: string) => {
      const data = frame.split(/\r?\n/).filter(line => line.startsWith('data:'))
        .map(line => line.slice(5).trimStart()).join('\n');
      if (!data) return;
      let event: Record<string, any>;
      try { event = JSON.parse(data); }
      catch { throw new Error('收到无法解析的响应，已保留当前回复。'); }
      if (!event || typeof event !== 'object' || typeof event.kind !== 'string') {
        throw new Error('响应格式不正确，已保留当前回复。');
      }
      handlers.onEvent(event);
      if (event.kind === 'done') completed = true;
    };
    while (!completed) {
      const { value, done } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      let match: RegExpExecArray | null;
      while ((match = /\r?\n\r?\n/.exec(buffer))) {
        const frame = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        emit(frame);
        if (completed) break;
      }
      if (done) {
        if (!completed && buffer.trim()) emit(buffer);
        break;
      }
    }
    if (handlers.signal?.aborted) return;
    if (!completed) throw new Error('连接提前结束，回复可能不完整。已保留收到的内容。');
    handlers.onDone();
  } catch (error) {
    if (!handlers.signal?.aborted) {
      handlers.onError(error instanceof Error ? error.message : '连接中断，已保留当前回复。');
    }
  } finally {
    if (reader) {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
  }
}
