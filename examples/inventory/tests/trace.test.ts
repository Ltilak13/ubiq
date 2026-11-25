import assert from 'node:assert/strict';
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import type { Envelope } from '@cucumber/messages';
import { loadTrace, scenarios, verifyRun, type Scenario } from '../scripts/trace.js';

function fixture(change: () => void) {
  const original = process.cwd();
  const folder = mkdtempSync(join(tmpdir(), 'inventory-trace-'));
  cpSync('.ubiq', join(folder, '.ubiq'), { recursive: true });
  cpSync('features', join(folder, 'features'), { recursive: true });
  process.chdir(folder);
  try { change(); } finally { process.chdir(original); rmSync(folder, { recursive: true, force: true }); }
}
function replace(path: string, before: string, after: string) {
  const text = readFileSync(path, 'utf8');
  assert(text.includes(before));
  writeFileSync(path, text.replace(before, after));
}
test('traceability rejects missing, unknown, duplicate and uncovered scenarios', () => {
  assert.equal(scenarios().length, 11);
  for (const [before, after, error] of [
    ['@SCN-RESERVE', '', /one SCN/],
    ['@REQ-RESERVE', '@REQ-UNKNOWN', /unknown requirement/],
    ['@SCN-INSUFFICIENT', '@SCN-RESERVE', /Duplicate scenario/],
  ] as const) fixture(() => {
    replace('features/reserve.feature', before, after);
    assert.throws(() => scenarios(), error);
  });
  fixture(() => {
    writeFileSync('features/reserve.feature', '@REQ-RESERVE\nFeature: Empty\n');
    assert.throws(() => scenarios(), /Uncovered requirement/);
  });
  fixture(() => {
    replace('features/reserve.feature', 'Scenario: Reserve part of the available stock', 'Scenario Outline: Reserve part of the available stock');
    replace('features/reserve.feature', '  @SCN-INSUFFICIENT', '    Examples:\n      | unused |\n      | value |\n\n  @SCN-INSUFFICIENT');
    assert.throws(() => scenarios(), /outlines are unsupported/);
  });
  fixture(() => {
    writeFileSync('features/reserve.feature', '@REQ-RESERVE\nFeature: Empty\n  @SCN-EMPTY\n  Scenario: No behavior\n');
    assert.throws(() => scenarios(), /must contain steps/);
  });
  fixture(() => {
    rmSync('features/reserve.feature');
    assert.throws(() => scenarios(), /Feature files must match/);
  });
  fixture(() => {
    const trace = loadTrace();
    trace.requirements[0].acceptance = 'release-feature';
    assert.throws(() => scenarios(trace), /does not match/);
  });
});

const expected: Scenario[] = [{ id: '@SCN-ONE', requirement: 'REQ-ONE', uri: 'features/one.feature', name: 'One' }];
function report(status = 'PASSED'): Envelope[] {
  return [
    { pickle: { id: 'p', uri: expected[0].uri, name: 'One', tags: [{ name: '@SCN-ONE' }] } },
    { testCase: { id: 'c', pickleId: 'p', testSteps: [{ id: 's' }] } },
    { testCaseStarted: { id: 'start', testCaseId: 'c' } },
    { testStepFinished: { testCaseStartedId: 'start', testStepId: 's', testStepResult: { status } } },
    { testCaseFinished: { testCaseStartedId: 'start' } },
    { testRunFinished: { success: true } },
  ] as unknown as Envelope[];
}
test('execution gate rejects skipped, failed, missing, repeated and unfinished results', () => {
  verifyRun(expected, report());
  for (const status of ['SKIPPED', 'PENDING', 'UNDEFINED', 'AMBIGUOUS', 'FAILED', 'UNKNOWN'])
    assert.throws(() => verifyRun(expected, report(status)), /must pass/);
  assert.throws(() => verifyRun(expected, [{ testRunFinished: { success: true } }] as Envelope[]), /must run exactly once/);
  assert.throws(() => verifyRun(expected, report().filter((message) => !message.testCaseFinished)), /did not finish/);
  assert.throws(() => verifyRun(expected, report().filter((message) => !message.testStepFinished)), /Missing or duplicate/);
  assert.throws(() => verifyRun(expected, [...report(), report()[2]]), /must run exactly once/);
  assert.throws(() => verifyRun(expected, report().filter((message) => !message.testRunFinished)), /finish successfully/);
});
