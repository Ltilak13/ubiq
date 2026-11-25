import { spawnSync } from 'node:child_process';
import { mkdirSync, readFileSync, rmSync } from 'node:fs';
import { scenarios, verifyRun } from './trace.js';

function run(command: string, args: string[]) {
  const result = spawnSync(command, args, { stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} failed: ${result.status}`);
}
const expected = scenarios();
rmSync('reports', { recursive: true, force: true });
mkdirSync('reports');
run(process.execPath, ['--import', 'tsx', '--test', 'tests/inventory.test.ts', 'tests/trace.test.ts']);
run(process.execPath, ['--import', 'tsx', 'node_modules/@cucumber/cucumber/bin/cucumber.js',
  '--import', 'features/steps/*.ts', '--format', 'progress', '--format', 'message:reports/cucumber.ndjson', 'features/*.feature']);
verifyRun(expected, readFileSync('reports/cucumber.ndjson', 'utf8').trim().split('\n').map((line) => JSON.parse(line)));
console.log(`Traceability passed: ${expected.length} scenarios executed for all declared requirements.`);
