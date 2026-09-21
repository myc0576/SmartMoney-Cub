import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/api.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { streamTurn } = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));
globalThis.document = { baseURI: 'http://localhost/trader/' };

async function run(response) {
  const events = [], errors = [];
  let done = 0;
  globalThis.fetch = async () => { if (response instanceof Error) throw response; return response; };
  await streamTurn('toy-session', 'toy message', {
    onEvent: e => events.push(e), onError: e => errors.push(e), onDone: () => done++,
  });
  return { events, errors, done };
}

test('HTTP failure reports error and terminates exactly once', async () => {
  const result = await run(new Response('{"error":"Unavailable"}', { status: 503 }));
  assert.equal(result.errors.length, 1);
  assert.equal(result.done, 1);
});

test('network rejection does not escape and always finalizes', async () => {
  const result = await run(new Error('offline'));
  assert.equal(result.errors.length, 1);
  assert.equal(result.done, 1);
});

test('handles CRLF frames, multi-line data and UTF-8 split across chunks', async () => {
  const bytes = new TextEncoder().encode('data: {"kind":"delta",\r\ndata: "text":"你好"}\r\n\r\ndata: {"kind":"done"}\r\n\r\n');
  const body = new ReadableStream({ start(controller) {
    for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
    controller.close();
  }});
  const result = await run(new Response(body));
  assert.deepEqual(result.events.map(e => e.kind), ['delta', 'done']);
  assert.equal(result.events[0].text, '你好');
  assert.deepEqual(result.errors, []);
  assert.equal(result.done, 1);
});

test('abrupt EOF and malformed complete frames are reported, not silent success', async () => {
  for (const data of ['data: {"kind":"delta","text":"partial"}\n\n', 'data: bad json\n\n']) {
    const result = await run(new Response(data));
    assert.equal(result.errors.length, 1);
    assert.equal(result.done, 1);
  }
});

test('normal done and server errors both settle exactly once', async () => {
  const done = await run(new Response('data: {"kind":"done"}\n\n'));
  assert.deepEqual(done.errors, []);
  assert.equal(done.done, 1);
  const fail = await run(new Response('data: {"kind":"error","error":"toy failure"}\n\n'));
  assert.equal(fail.events[0].kind, 'error');
  assert.equal(fail.done, 1);
});
