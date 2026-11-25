import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { generateMessages } from '@cucumber/gherkin';
import { IdGenerator, SourceMediaType, type Envelope } from '@cucumber/messages';

type Evidence = { path: string; sha256: string; anchor: string };
type Record = { id: string; source: string; evidence: Evidence[] };
export type Trace = {
  requirements: (Record & { implementation: string; acceptance: string })[];
  implementations: Record[]; contracts: Record[]; acceptance: Record[]; terms: Record[];
  domains: { id: string; evidence: Evidence[] }[];
  relationships: { from: string; evidence: Evidence }[];
};
export const loadTrace = (): Trace => JSON.parse(readFileSync('.ubiq/trace.json', 'utf8'));
export type Scenario = { id: string; requirement: string; uri: string; name: string };

export function scenarios(trace = loadTrace()): Scenario[] {
  const files = readdirSync('features').filter((file) => file.endsWith('.feature')).sort().map((file) => `features/${file}`);
  assert.deepEqual(files, trace.acceptance.map((record) => record.source).sort(), 'Feature files must match declared acceptance artifacts');
  const result: Scenario[] = [];
  for (const uri of files) {
    const envelopes = generateMessages(readFileSync(uri, 'utf8'), uri,
      SourceMediaType.TEXT_X_CUCUMBER_GHERKIN_PLAIN, { includeGherkinDocument: true, includePickles: true, newId: IdGenerator.incrementing() });
    assert(!envelopes.some((envelope) => envelope.parseError), `Invalid Gherkin: ${uri}`);
    for (const envelope of envelopes) {
      const children = envelope.gherkinDocument?.feature?.children ?? [];
      const declared = children.flatMap((child) => child.rule ? child.rule.children : [child]);
      assert(!declared.some((child) => child.scenario?.examples.length), 'Scenario outlines are unsupported');
      const pickle = envelope.pickle;
      if (!pickle) continue;
      assert(pickle.steps.length > 0, `${uri}: scenario must contain steps`);
      const tags = pickle.tags.map((tag) => tag.name);
      const ids = tags.filter((tag) => tag.startsWith('@SCN-'));
      const requirements = tags.filter((tag) => tag.startsWith('@REQ-'));
      assert.equal(ids.length, 1, `${uri}: each scenario needs one SCN tag`);
      assert.equal(requirements.length, 1, `${uri}: each scenario needs one REQ tag`);
      const requirement = trace.requirements.find((record) => '@' + record.id === requirements[0]);
      assert(requirement, `${uri}: unknown requirement ${requirements[0]}`);
      assert.equal(trace.acceptance.find((record) => record.id === requirement.acceptance)?.source, uri, 'Scenario does not match declared requirement artifact');
      result.push({ id: ids[0], requirement: requirement.id, uri, name: pickle.name });
    }
  }
  assert.equal(new Set(result.map((scenario) => scenario.id)).size, result.length, 'Duplicate scenario ID (outlines are unsupported)');
  for (const requirement of trace.requirements)
    assert(result.some((scenario) => scenario.requirement === requirement.id), `Uncovered requirement: ${requirement.id}`);
  assert(result.length > 0, 'No acceptance scenarios');
  return result;
}

export function verifyRun(expected: Scenario[], messages: Envelope[]) {
  const pickles = new Map(messages.flatMap((message) => message.pickle ? [[message.pickle.id, message.pickle] as const] : []));
  const cases = new Map(messages.flatMap((message) => message.testCase ? [[message.testCase.id, message.testCase] as const] : []));
  const starts = messages.flatMap((message) => message.testCaseStarted ? [message.testCaseStarted] : []);
  const completed: string[] = [];
  assert.equal(messages.filter((message) => message.testRunFinished?.success).length, 1, 'Run must finish successfully');
  for (const start of starts) {
    const testCase = cases.get(start.testCaseId);
    const pickle = testCase && pickles.get(testCase.pickleId);
    assert(testCase && pickle, 'Execution refers to a missing test case or scenario');
    const id = pickle.tags.find((tag) => tag.name.startsWith('@SCN-'))?.name;
    const scenario = expected.find((candidate) => candidate.id === id);
    assert(scenario && scenario.uri === pickle.uri && scenario.name === pickle.name, 'Unexpected executed scenario');
    assert.equal(messages.filter((message) => message.testCaseFinished?.testCaseStartedId === start.id).length, 1, 'Scenario did not finish');
    const steps = messages.flatMap((message) => message.testStepFinished?.testCaseStartedId === start.id ? [message.testStepFinished] : []);
    assert.deepEqual(steps.map((step) => step.testStepId).sort(), testCase.testSteps.map((step) => step.id).sort(), 'Missing or duplicate step results');
    assert(steps.length > 0 && steps.every((step) => step.testStepResult.status === 'PASSED'), 'Every step and hook must pass');
    completed.push(scenario.id);
  }
  assert.deepEqual(completed.sort(), expected.map((scenario) => scenario.id).sort(), 'Every expected scenario must run exactly once');
}
