import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
const source = readFileSync(new URL('../src/stream.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText;
const { consumeStream } = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));

async function run(chunks, options = {}) {
  const events = [], errors = []; let done = 0;
  const original = globalThis.fetch;
  globalThis.fetch = async () => options.response || new Response(new ReadableStream({
    start(controller) { for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk)); controller.close(); },
  }), { headers: { 'content-type': 'text/event-stream' } });
  try { await consumeStream('http://localhost/test', {}, {
    onEvent: e => events.push(e), onError: e => errors.push(e), onDone: () => done++, ...options.handlers,
  }); } finally { globalThis.fetch = original; }
  return { events, errors, done };
}

test('handles CRLF, chunk boundaries, and final done frame without a trailing newline', async () => {
  const result = await run(['data: {"kind":"del', 'ta","text":"证据"}\r', '\n\r\ndata: {"kind":"done"}']);
  assert.equal(result.events[0].text, '证据'); assert.equal(result.done, 1); assert.deepEqual(result.errors, []);
});
test('HTTP failure is surfaced once, never marked complete', async () => {
  const r = await run([], { response: new Response('{"error":"unavailable"}', { status: 503 }) });
  assert.equal(r.errors.length, 1); assert.equal(r.done, 0);
});
test('EOF before done retains partial output and reports interruption', async () => {
  const r = await run(['data: {"kind":"delta","text":"partial"}\n\n']);
  assert.equal(r.events[0].text, 'partial'); assert.equal(r.errors.length, 1); assert.equal(r.done, 0);
});
test('malformed complete frame is not silently discarded', async () => {
  const r = await run(['data: {broken}\n\ndata: {"kind":"done"}\n\n']);
  assert.equal(r.errors.length, 1); assert.equal(r.done, 0);
});
test('AbortError does not become a fake success', async () => {
  const controller = new AbortController(); controller.abort();
  const r = await run([], { handlers: { signal: controller.signal } });
  assert.equal(r.done, 0); assert.equal(r.errors.length, 0);
});
