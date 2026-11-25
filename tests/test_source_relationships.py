"""Frontmatter is the sole declaration of source-derived relationships."""

import copy
import hashlib
import json

import pytest
from test_query import run

from ubiq.integrity import assess_integrity, assess_model, validate_spec
from ubiq.records import Glossary


@pytest.fixture
def model(tmp_path):
    (tmp_path / 'goal.md').write_text(
        '---\ngoverned_by: policy\n---\n# Goal\n\n## Governing policy\n'
        '[Policy](policy.md)\n\n## Other\nOther content.\n')
    (tmp_path / 'policy.md').write_text('# Policy\n')

    def record(ident, kind):
        source = f'{ident}.md'
        return {'id': ident, 'kind': kind, 'domain': 'd', 'source': source,
                    'evidence': [{'path': source, 'sha256': hashlib.sha256(
                        (tmp_path / source).read_bytes()).hexdigest(), 'anchor': '#'}]}

    goal, policy = record('goal', 'goal'), record('policy', 'policy')
    data = {'goals': [goal], 'policies': [policy], 'domains': [{'id': 'd', 'evidence': policy['evidence']}],
                'relationships': [], 'interactions': []}
    spec = {'collections': {'goals': 'goal', 'policies': 'policy'}, 'domains': 'domains',
                'relationships': 'relationships', 'interactions': 'interactions',
                'roles': {'governs': {'from': ['policy'], 'to': ['goal']}}, 'references': [],
                'coverage': {'glossary': True, 'exclude': []}, 'evidence': True,
                'source_references': [{'kind': 'goal', 'field': 'governed_by', 'target_kind': 'policy',
                                        'relationship': 'governs', 'direction': 'incoming',
                                        'body_section': 'Governing policy'}]}
    return data, spec


def test_source_reference_contract(model, tmp_path):
    data, spec = model
    validate_spec(spec)
    assert assess_integrity(data, spec, tmp_path, Glossary([])) == []


@pytest.mark.parametrize('before,after', [
    ('governed_by: policy', 'governed_by: missing'),
    ('governed_by: policy', 'governed_by: goal'),
    ('governed_by: policy', 'governed_by: [policy]'),
    ('governed_by: policy', 'other: policy'),
    ('[Policy](policy.md)', '[Policy](goal.md)'),
    ('[Policy](policy.md)', '`[Policy](policy.md)`'),
    ('## Governing policy', '## Other policy'),
    ('[Policy](policy.md)', '<!-- [Policy](policy.md) -->'),
    ('[Policy](policy.md)', '![Policy](policy.md)'),
    ('[Policy](policy.md)', '[Policy](policy.md) [Other](missing.md)'),
    ('## Governing policy', '<!--\n## Governing policy\n-->'),
    ('governed_by: policy', 'governed_by: {bad yaml'),
])
def test_source_reference_rejects_drift(model, tmp_path, before, after):
    data, spec = model
    path = tmp_path / 'goal.md'
    path.write_text(path.read_text().replace(before, after))
    # Accept new bytes deliberately: these assertions test semantics, not stale hashes.
    data['goals'][0]['evidence'][0]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    findings = assess_integrity(data, spec, tmp_path, Glossary([]))
    assert any(f.category == 'relationship' for f in findings)


def test_source_edges_are_derived_without_mutation(model, tmp_path):
    data, spec = model
    original = copy.deepcopy(data)
    effective, findings = assess_model(data, spec, tmp_path, Glossary([]))
    assert findings == [] and data == original
    edge, = effective['relationships']
    assert (edge['from'], edge['kind'], edge['to']) == ('policy', 'governs', 'goal')
    assert edge['derived_from'] == {'file': 'goal.md', 'field': 'governed_by', 'record': 'goal'}
    assert edge['evidence'] == data['goals'][0]['evidence'][0]
    edge['evidence'].update(anchor='changed')
    assert data == original


@pytest.mark.parametrize('case', ['edge', 'field', 'forged-origin', 'ambiguous-id'])
def test_reject_duplicate_or_forged_declarations(model, tmp_path, case):
    data, spec = model
    if case in ('edge', 'forged-origin'):
        effective, _ = assess_model(data, spec, tmp_path, Glossary([]))
        data['relationships'] = effective['relationships']
        if case == 'edge':
            data['relationships'][0].pop('derived_from')
        else:
            data['relationships'][0]['derived_from'] = 42
    elif case == 'field':
        data['goals'][0]['governed_by'] = 'policy'
    else:
        data['policies'].append(copy.deepcopy(data['policies'][0]))
    assert assess_integrity(data, spec, tmp_path, Glossary([]))


def test_query_uses_declaring_goal_evidence(model, tmp_path, capsys):
    data, spec = model
    (tmp_path / 'schema.json').write_text(json.dumps({'type': 'object', 'x-ubiq': spec}))
    (tmp_path / 'model.json').write_text(json.dumps(data))
    (tmp_path / 'ubiq.yaml').write_text(json.dumps({'glossary': [], 'docs': [], 'schemas': [
        {'schema': 'schema.json', 'files': ['model.json']}]}))
    code, result = run(tmp_path, capsys, '--id', 'goal', '--incoming', '--relation', 'governs')
    assert code == 0 and result['results'][0]['identity']['id'] == 'policy'
    assert result['relationships'][0]['evidence_status'] == 'fresh'
    path = tmp_path / 'goal.md'
    path.write_text(path.read_text() + '\nchanged bytes\n')
    code, result = run(tmp_path, capsys, '--id', 'goal', '--incoming', '--relation', 'governs')
    assert code == 0 and result['complete']  # Queries report freshness; check is the gate.
    edge, = result['relationships']
    assert edge['evidence_status'] == 'stale' and edge['evidence_scope'] == 'declaring_record'
    assert result['results'][0]['evidence_status'] == 'fresh'


@pytest.mark.parametrize('forged', [False, True])
def test_query_rejects_stored_source_edges(model, tmp_path, capsys, forged):
    data, spec = model
    effective, _ = assess_model(data, spec, tmp_path, Glossary([]))
    data['relationships'] = effective['relationships']
    if not forged:
        data['relationships'][0].pop('derived_from')
    (tmp_path / 'schema.json').write_text(json.dumps({'type': 'object', 'x-ubiq': spec}))
    (tmp_path / 'model.json').write_text(json.dumps(data))
    (tmp_path / 'ubiq.yaml').write_text(json.dumps({'glossary': [], 'docs': [], 'schemas': [
        {'schema': 'schema.json', 'files': ['model.json']}]}))
    code, result = run(tmp_path, capsys, '--id', 'goal', '--incoming')
    assert code == 1 and not result['complete']
    assert all(edge['resolution'] == 'invalid' for edge in result['relationships'])


def test_outgoing_rule_and_role_validation(model, tmp_path):
    data, spec = model
    spec['source_references'][0]['direction'] = 'outgoing'
    with pytest.raises(ValueError, match='reference types'):
        validate_spec(spec)
    spec['roles']['governs'] = {'from': ['goal'], 'to': ['policy']}
    validate_spec(spec)
    effective, findings = assess_model(data, spec, tmp_path, Glossary([]))
    assert not findings
    edge, = effective['relationships']
    assert (edge['from'], edge['to']) == ('goal', 'policy')


def test_overlapping_bindings_preserve_each_derived_graph(model, tmp_path, capsys):
    data, spec = model
    other = copy.deepcopy(spec)
    other['roles'] = {'reviews': {'from': ['policy'], 'to': ['goal']}}
    other['source_references'][0]['relationship'] = 'reviews'
    for name, extension in [('first', spec), ('second', other)]:
        (tmp_path / f'{name}.json').write_text(json.dumps({'type': 'object', 'x-ubiq': extension}))
    (tmp_path / 'model.json').write_text(json.dumps(data))
    (tmp_path / 'ubiq.yaml').write_text(json.dumps({'glossary': [], 'docs': [], 'schemas': [
        {'schema': f'{name}.json', 'files': ['model.json']} for name in ('first', 'second')]}))
    code, result = run(tmp_path, capsys, '--id', 'goal', '--incoming')
    assert code == 0 and result['complete']
    assert {edge['record']['kind'] for edge in result['relationships']} == {'governs', 'reviews'}
    assert len({edge['metadata']['pointer'] for edge in result['relationships']}) == 2
    assert all(edge['resolution'] == 'resolved' for edge in result['relationships'])


def test_invalid_source_declaration_is_reported_by_query_and_coverage(model, tmp_path, capsys):
    from ubiq.cli import main

    data, spec = model
    path = tmp_path / 'goal.md'
    path.write_text(path.read_text().replace('governed_by: policy', 'governed_by: missing'))
    data['goals'][0]['evidence'][0]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / 'schema.json').write_text(json.dumps({'type': 'object', 'x-ubiq': spec}))
    (tmp_path / 'model.json').write_text(json.dumps(data))
    (tmp_path / 'ubiq.yaml').write_text(json.dumps({'glossary': [], 'docs': [],
        'coverage': {'files': ['goal.md', 'policy.md']},
        'schemas': [{'schema': 'schema.json', 'files': ['model.json']}]}))
    _, result = run(tmp_path, capsys, '--id', 'goal', '--incoming')
    assert result['relationships'] == []
    assert any('governed_by must resolve' in d['message'] for d in result['diagnostics'])
    assert main(['check', '--root', str(tmp_path), '--json']) == 1
    assert json.loads(capsys.readouterr().out)['diagnostics']
    main(['coverage', '--root', str(tmp_path), '--json'])
    coverage = json.loads(capsys.readouterr().out)
    goal = next(item for item in coverage['files'] if item['file'] == 'goal.md')
    assert goal['relationships'] == 'invalid'
