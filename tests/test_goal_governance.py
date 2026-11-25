"""Exercise the repository's accepted policy/goal corpus, not a synthetic model."""

import copy
import json
from pathlib import Path

import pytest
from test_query import run

from ubiq.cli import build, main
from ubiq.integrity import assess_integrity
from ubiq.schemas import load_data

ROOT = Path(__file__).resolve().parents[1]
MODEL = '.ubiq/knowledge/goal-governance.yaml'
SCHEMA = '.ubiq/schemas/goal-governance.json'
POLICY = 'ubiq:goal-evidence-policy'
GOAL = 'ubiq:domain-schema-goal'


def test_registered_goal_governance_queries(capsys):
    data = load_data(ROOT / MODEL)
    for kind, ident, collection in [('policy', POLICY, 'policies'), ('goal', GOAL, 'goals')]:
        code, result = run(ROOT, capsys, '--kind', kind, '--domain', 'goal-assessment')
        assert code == 0 and result['complete']
        item, = result['results']
        assert item['record'] == data[collection][0]
        assert item['identity']['id'] == ident
        assert item['conformance'] == 'valid' and item['evidence_status'] == 'fresh'
        assert item['metadata'] == {'file': MODEL, 'pointer': f'/{collection}/0'}
    for ident, direction, neighbor in [(POLICY, '--outgoing', GOAL), (GOAL, '--incoming', POLICY)]:
        code, result = run(ROOT, capsys, '--id', ident, direction, '--relation', 'governs')
        assert code == 0 and result['complete']
        item, = result['results']
        assert item['identity']['id'] == neighbor
        edge, = result['relationships']
        assert edge['record'] == data['relationships'][0]
        assert edge['metadata'] == {'file': MODEL, 'pointer': '/relationships/0'}
        assert edge['resolution'] == 'resolved' and edge['evidence_status'] == 'fresh'
        assert edge['evidence_scope'] == 'source_record'
    assert main(['check', '--root', str(ROOT), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['diagnostics'] == []


@pytest.mark.parametrize('case, expected', [
    ('missing-target', ('relationship', 'unresolved')),
    ('wrong-type', ('relationship', 'incompatible')),
    ('missing-edge', ('relationship', 'undeclared')),
    ('stale-evidence', ('evidence', 'stale')),
    ('missing-anchor', ('evidence', 'stale')),
])
def test_goal_governance_rejects_invalid_declarations(case, expected):
    built = build(ROOT)
    data = load_data(ROOT / MODEL)
    spec = load_data(ROOT / SCHEMA)['x-ubiq']
    assert assess_integrity(data, spec, ROOT, built.glossary) == []
    bad = copy.deepcopy(data)
    if case == 'missing-target':
        bad['relationships'][0]['to'] = 'ubiq:missing-goal'
    elif case == 'wrong-type':
        bad['relationships'][0]['to'] = POLICY
    elif case == 'missing-edge':
        bad['relationships'] = []
    elif case == 'stale-evidence':
        bad['relationships'][0]['evidence']['sha256'] = '0' * 64
    else:
        bad['relationships'][0]['evidence']['anchor'] = 'absent policy claim'
    findings = assess_integrity(bad, spec, ROOT, built.glossary)
    assert expected in {(finding.category, finding.kind) for finding in findings}
