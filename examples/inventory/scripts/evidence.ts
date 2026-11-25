import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { loadTrace } from './trace.js';

// Run explicitly after reviewing source changes. Checks never refresh evidence.
const trace = loadTrace();
function snapshot(path: string) {
  const source = readFileSync(path, 'utf8');
  return { path, sha256: createHash('sha256').update(source).digest('hex'), anchor: source.trim() };
}
const records = [...trace.requirements, ...trace.implementations, ...trace.contracts, ...trace.acceptance, ...trace.terms];
for (const record of records) record.evidence = [snapshot(record.source)];
for (const domain of trace.domains) domain.evidence = [snapshot('.ubiq/glossary/item.md')];
for (const edge of trace.relationships) edge.evidence = snapshot(records.find((record) => record.id === edge.from)!.source);
writeFileSync('.ubiq/trace.json', JSON.stringify(trace, null, 2) + '\n');
