import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { cpSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const cases = [
  { name: 'broken reference', path: '.ubiq/trace.json', before: '"implementation": "inventory-service"', after: '"implementation": "missing"', command: 'python3', args: ['-m', 'ubiq.cli', 'check', '--root', '.'], diagnostic: 'E010' },
  { name: 'stale source', path: 'src/contracts.ts', before: 'const identifier', after: '// changed source\nconst identifier', command: 'python3', args: ['-m', 'ubiq.cli', 'check', '--root', '.'], diagnostic: 'E010' },
  { name: 'removed feature', path: 'features/release.feature', command: process.execPath, args: ['--import', 'tsx', 'scripts/check.ts'], diagnostic: 'Feature files must match' },
  { name: 'double release', path: 'src/inventory.ts', before: "if (reservation.status === 'released') return { ok: true };", after: '// deliberately restore released stock again', command: process.execPath, args: ['--import', 'tsx', 'node_modules/@cucumber/cucumber/bin/cucumber.js', '--import', 'features/steps/*.ts', 'features/release.feature'], diagnostic: '8 !== 5' },
];
for (const mutation of cases) {
  const folder = mkdtempSync(join(tmpdir(), 'inventory-mutation-'));
  try {
    cpSync('.', folder, { recursive: true, filter: (path) => !['node_modules', 'reports'].some((part) => path.split('/').includes(part)) });
    symlinkSync(resolve('node_modules'), join(folder, 'node_modules'), 'dir');
    const path = join(folder, mutation.path);
    if (mutation.before !== undefined) {
      const original = readFileSync(path, 'utf8');
      assert(original.includes(mutation.before), `Mutation target missing: ${mutation.name}`);
      writeFileSync(path, original.replace(mutation.before, mutation.after!));
    } else rmSync(path);
    const result = spawnSync(mutation.command, mutation.args, { cwd: folder, encoding: 'utf8' });
    if (result.error) throw result.error;
    assert(result.status !== null && result.status !== 0, `Mutation survived: ${mutation.name}`);
    assert((result.stdout + result.stderr).includes(mutation.diagnostic), `Wrong failure for ${mutation.name}: ${result.stdout}${result.stderr}`);
    console.log(`Detected: ${mutation.name}`);
  } finally { rmSync(folder, { recursive: true, force: true }); }
}
