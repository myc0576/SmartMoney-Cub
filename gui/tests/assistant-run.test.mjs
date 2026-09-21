import test from 'node:test';
import assert from 'node:assert/strict';
import { shouldSendOnEnter, shouldFollowOutput, describeRun } from '../src/components/assistantRun.ts';

test('Chinese IME confirmation is not a send', () => {
  assert.equal(shouldSendOnEnter('Enter', false, true, 13), false);
  assert.equal(shouldSendOnEnter('Enter', false, false, 229), false);
  assert.equal(shouldSendOnEnter('Enter', true, false, 13), false);
  assert.equal(shouldSendOnEnter('Enter', false, false, 13), true);
});
test('reading earlier messages opts out of automatic scroll', () => {
  assert.equal(shouldFollowOutput(1000, 400, 0), false);
  assert.equal(shouldFollowOutput(1000, 400, 580), true);
});
test('feedback reflects events, not an invented percent or reasoning trace', () => {
  assert.equal(describeRun('connecting', 0, 0), '正在连接模型');
  assert.equal(describeRun('tools', 2, 1), '正在处理工具 · 已返回 1 / 2');
  assert.equal(describeRun('writing', 2, 2), '正在生成回复');
  assert.equal(describeRun('stopped', 2, 1), '已停止接收 · 保留本轮内容');
  assert.equal(describeRun('error', 0, 0), '本轮未完成');
});
