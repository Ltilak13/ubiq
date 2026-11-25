"""One-hop queries follow only edges in the configured relationship collection."""

import copy
import json

import pytest
import yaml
from test_query import run, save, setup

from ubiq.cli import main


def test_outgoing_and_incoming_return_neighbors_and_declared_edge(tmp_path, capsys):
    data, _, _ = setup(tmp_path)
    for seed, direction, expected in [('h', '--outgoing', 's'), ('s', '--incoming', 'h')]:
        code, result = run(tmp_path, capsys, '--id', seed, direction)
        assert code == 0 and result['complete'] and result['version'] == 1
        neighbor, = result['results']
        assert neighbor['identity']['id'] == expected
        edge, = result['relationships']
        assert edge['record'] == data['relationships'][0]
        assert edge['metadata'] == {'file': 'model.json', 'pointer': '/relationships/0'}
        assert edge['resolution'] == 'resolved' and edge['evidence_status'] == 'fresh'
        assert edge['evidence_scope'] == 'source_record'
        for end, ident in [('from', 'h'), ('to', 's')]:
            assert edge['endpoints'][end]['status'] == 'resolved'
            assert edge['endpoints'][end]['identity'] == {
                'repository': str(tmp_path), 'document': 'model.json', 'id': ident}
        assert result['selection']['seed']['identity']['id'] == seed


def test_relation_implies_outgoing_and_filters_neighbors(tmp_path, capsys):
    setup(tmp_path)
    code, result = run(tmp_path, capsys, '--id', 'h', '--relation', 'invokes',
                       '--kind', 'script', '--domain', 'delivery')
    assert code == 0 and result['selection']['direction'] == 'outgoing'
    assert len(result['results']) == len(result['relationships']) == 1
    for filters in [('--relation', 'unknown'), ('--kind', 'hook'), ('--domain', 'other')]:
        code, result = run(tmp_path, capsys, '--id', 'h', '--outgoing', *filters)
        assert code == 0 and result['results'] == result['relationships'] == []


def test_plain_identity_has_no_traversal(tmp_path, capsys):
    setup(tmp_path)
    code, result = run(tmp_path, capsys, '--id', 'h')
    assert code == 0 and result['results'][0]['identity']['id'] == 'h'
    assert 'relationships' not in result


@pytest.mark.parametrize('args', [('--incoming',), ('--outgoing',), ('--relation', 'invokes'),
                                  ('--id', 'h', '--incoming', '--outgoing')])
def test_relationship_flags_require_an_unambiguous_direction_and_seed(tmp_path, capsys, args):
    setup(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(['query', '--root', str(tmp_path), *args])
    assert exc.value.code == 2


def test_seed_resolution_precedes_neighbor_filters(tmp_path, capsys):
    data, _, _ = setup(tmp_path)
    code, result = run(tmp_path, capsys, '--id', 'absent', '--outgoing')
    assert code == 3 and result['status'] == 'not_found' and not result['relationships']
    save(tmp_path, data, 'model-other.json')
    code, result = run(tmp_path, capsys, '--id', 'h', '--outgoing', '--kind', 'script')
    assert code == 4 and result['status'] == 'ambiguous' and not result['relationships']
    code, result = run(tmp_path, capsys, '--id', 'h', '--outgoing', '--document', 'model.json')
    assert code == 0 and len(result['results']) == len(result['relationships']) == 1
    assert result['results'][0]['identity']['document'] == 'model.json'


def test_missing_endpoint_does_not_resolve_in_another_document(tmp_path, capsys):
    data, _, _ = setup(tmp_path)
    save(tmp_path, data, 'model-other.json')
    data['scripts'] = []
    save(tmp_path, data)
    code, result = run(tmp_path, capsys, '--id', 'h', '--outgoing', '--document', 'model.json',
                       '--kind', 'anything')
    assert code == 1 and not result['complete'] and result['status'] == 'partial'
    assert result['results'] == []
    edge, = result['relationships']
    assert edge['resolution'] == 'missing' and edge['endpoints']['to']['status'] == 'missing'
    assert edge['endpoints']['to']['declared_id'] == 's'
    assert result['diagnostics']


def test_ambiguous_endpoint_is_retained_without_choosing_a_record(tmp_path, capsys):
    data, _, _ = setup(tmp_path)
    data['scripts'].append(copy.deepcopy(data['scripts'][0]))
    save(tmp_path, data)
    code, result = run(tmp_path, capsys, '--id', 'h', '--outgoing')
    assert code == 1 and not result['complete'] and result['results'] == []
    edge, = result['relationships']
    assert edge['resolution'] == 'ambiguous'
    endpoint = edge['endpoints']['to']
    assert endpoint['status'] == 'ambiguous' and len(endpoint['candidates']) == 2


def test_no_edges_are_inferred_from_reference_fields_or_prose(tmp_path, capsys):
    data, _, _ = setup(tmp_path)
    data['relationships'] = []
    save(tmp_path, data)
    (tmp_path / 'h.md').write_text('h invokes s: [[s]]')
    code, result = run(tmp_path, capsys, '--id', 'h', '--outgoing')
    assert code == 0 and result['relationships'] == result['results'] == []
    assert result['diagnostics']  # Missing declared handler edge remains an integrity finding.


def test_stale_edge_snapshot_is_not_fresh(tmp_path, capsys):
    data, _, _ = setup(tmp_path)
    data['relationships'][0]['evidence']['sha256'] = '0' * 64
    save(tmp_path, data)
    code, result = run(tmp_path, capsys, '--id', 'h', '--outgoing')
    assert code == 0 and result['complete']
    edge, = result['relationships']
    assert edge['evidence_status'] == 'stale' and edge['evidence_scope'] == 'source_record'


def test_owner_evidence_status_is_explicitly_conservative(tmp_path, capsys):
    data, _, _ = setup(tmp_path)
    data['hooks'][0]['evidence'][0]['sha256'] = '0' * 64
    save(tmp_path, data)
    code, result = run(tmp_path, capsys, '--id', 's', '--incoming')
    assert code == 0
    edge, = result['relationships']
    assert edge['evidence_status'] == 'stale' and edge['evidence_scope'] == 'source_record'


@pytest.mark.parametrize('field', ['evidence', 'to'])
def test_invalid_matching_edges_remain_visible(tmp_path, capsys, field):
    data, _, _ = setup(tmp_path)
    del data['relationships'][0][field]
    save(tmp_path, data)
    code, result = run(tmp_path, capsys, '--id', 'h', '--outgoing')
    assert code == 1 and not result['complete']
    edge, = result['relationships']
    assert edge['conformance'] == 'invalid' and edge['evidence_status'] == 'not_assessed'
    assert edge['resolution'] == 'invalid'


def test_incompatible_edge_types_are_partial(tmp_path, capsys):
    data, _, _ = setup(tmp_path)
    data['relationships'][0]['kind'] = 'undeclared'
    save(tmp_path, data)
    code, result = run(tmp_path, capsys, '--id', 'h', '--outgoing')
    assert code == 1 and result['relationships'][0]['resolution'] == 'invalid'


def test_overlap_deduplicates_edges_and_preserves_binding_boundaries(tmp_path, capsys):
    _, schema, config = setup(tmp_path)
    config['schemas'].append(config['schemas'][0].copy())
    (tmp_path / 'ubiq.yaml').write_text(yaml.safe_dump(config))
    code, result = run(tmp_path, capsys, '--id', 'h', '--outgoing')
    assert code == 0 and len(result['relationships']) == 1
    assert len(result['relationships'][0]['assessments']) == 2
    schema['x-ubiq']['collections'] = {'hooks': 'hook'}
    schema['x-ubiq']['roles'] = {'invokes': {'from': ['hook'], 'to': ['hook']}}
    schema['x-ubiq']['references'] = []
    (tmp_path / 'narrow.json').write_text(json.dumps(schema))
    config['schemas'][1]['schema'] = 'narrow.json'
    (tmp_path / 'ubiq.yaml').write_text(yaml.safe_dump(config))
    code, result = run(tmp_path, capsys, '--id', 'h', '--outgoing')
    assert code == 1 and result['results'] == []
    assert result['relationships'][0]['endpoints']['to']['status'] == 'missing'


def test_cycles_and_self_edges_are_only_one_hop(tmp_path, capsys):
    data, schema, _ = setup(tmp_path)
    schema['x-ubiq']['roles']['connects'] = {'from': ['hook', 'script'], 'to': ['hook', 'script']}
    for ident, source, target in [('back', 's', 'h'), ('self', 'h', 'h')]:
        data['relationships'].append({'id': ident, 'from': source, 'to': target, 'kind': 'connects',
                                      'evidence': copy.deepcopy(data['relationships'][0]['evidence'])})
    save(tmp_path, data)
    (tmp_path / 'schema.json').write_text(json.dumps(schema))
    code, result = run(tmp_path, capsys, '--id', 'h', '--outgoing')
    assert code == 0 and len(result['results']) == 2
    assert {e['record']['id'] for e in result['relationships']} == {'calls', 'self'}


def test_deterministic_relationship_output_includes_provenance(tmp_path, capsys):
    setup(tmp_path)
    args = ['query', '--root', str(tmp_path), '--id', 'h', '--outgoing']
    assert main([*args, '--json']) == 0
    first = capsys.readouterr().out
    assert main([*args, '--json']) == 0
    assert capsys.readouterr().out == first
    assert main(args) == 0
    text = capsys.readouterr().out
    for expected in ('/relationships/0', 'endpoints', 'sha256', 'calls'):
        assert expected in text


def test_role_checks_use_endpoint_selected_by_declaring_binding(tmp_path, capsys):
    data, schema, config = setup(tmp_path)
    alternate = copy.deepcopy(data['scripts'][0])
    alternate.update(kind='rule', source='alternate.md')
    (tmp_path / 'alternate.md').write_bytes((tmp_path / 's.md').read_bytes())
    alternate['evidence'][0]['path'] = 'alternate.md'
    data['alternatives'] = [alternate]  # Same ID, but outside the edge's declared graph.
    data['other_edges'] = []
    save(tmp_path, data)
    schema['x-ubiq'].update(collections={'alternatives': 'rule'}, relationships='other_edges',
                           roles={}, references=[])
    (tmp_path / 'other.json').write_text(json.dumps(schema))
    config['schemas'].append({'schema': 'other.json', 'files': ['model.json']})
    (tmp_path / 'ubiq.yaml').write_text(yaml.safe_dump(config))
    code, result = run(tmp_path, capsys, '--id', 'h', '--outgoing')
    assert code == 0 and result['complete']
    neighbor, = result['results']
    assert neighbor['record']['kind'] == 'script' and neighbor['metadata']['pointer'] == '/scripts/0'
    assert result['relationships'][0]['resolution'] == 'resolved'


def test_relationship_selector_escapes_pointer_tokens(tmp_path, capsys):
    data, schema, _ = setup(tmp_path)
    data['edges/~'] = data.pop('relationships')
    schema['x-ubiq']['relationships'] = 'edges/~'
    save(tmp_path, data)
    (tmp_path / 'schema.json').write_text(json.dumps(schema))
    code, result = run(tmp_path, capsys, '--id', 'h', '--outgoing')
    assert code == 0 and result['relationships'][0]['metadata']['pointer'] == '/edges~1~0/0'


def test_unavailable_relationship_query_has_relationship_array(tmp_path, capsys):
    (tmp_path / 'ubiq.yaml').write_text('schemas: invalid')
    code, result = run(tmp_path, capsys, '--id', 'h', '--outgoing')
    assert code == 1 and result['status'] == 'unavailable' and result['relationships'] == []
