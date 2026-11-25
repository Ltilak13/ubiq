"""Local typed selection preserves declarations and reports incomplete evidence."""

import copy
import json
import subprocess

import pytest
import yaml
from test_integrity import example

from ubiq.cli import main


def setup(root):
    data, spec, _ = example(root)
    data['scripts'][0]['inputs'] = ['declared input']
    data['scripts'][0]['contract'] = {'preserve': True}
    schema = {'type': 'object', 'x-ubiq': spec}
    config = {'glossary': [], 'docs': [], 'schemas': [
        {'schema': 'schema.json', 'files': ['model*.json']}]}
    (root / 'schema.json').write_text(json.dumps(schema))
    (root / 'ubiq.yaml').write_text(yaml.safe_dump(config))
    save(root, data)
    return data, schema, config


def save(root, data, name='model.json'):
    (root / name).write_text(json.dumps(data))


def run(root, capsys, *args):
    code = main(['query', '--root', str(root), '--json', *args])
    return code, json.loads(capsys.readouterr().out)


def test_select_complete_record_and_provenance(tmp_path, capsys):
    data, _, _ = setup(tmp_path)
    code, result = run(tmp_path, capsys, '--kind', 'script', '--domain', 'delivery')
    assert code == 0 and result['version'] == 1 and result['complete']
    item, = result['results']
    assert item['record'] == data['scripts'][0]
    assert item['identity'] == {'repository': str(tmp_path), 'document': 'model.json', 'id': 's'}
    assert item['metadata'] == {'file': 'model.json', 'pointer': '/scripts/0'}
    assert item['repository']['revision'] is None
    assert item['repository']['state'] == 'working_tree'
    assert item['conformance'] == 'valid' and item['evidence_status'] == 'fresh'
    assert item['assessments'][0]['schema'] == 'schema.json'


def test_empty_filter_and_missing_identity_are_distinct(tmp_path, capsys):
    setup(tmp_path)
    for args in [('--kind', 'unknown'), ('--domain', 'unknown'),
                 ('--kind', 'hook', '--id', 's')]:
        code, result = run(tmp_path, capsys, *args)
        assert code == 0 and result['status'] == 'ok' and result['results'] == []
    code, result = run(tmp_path, capsys, '--id', 'absent')
    assert code == 3 and result['status'] == 'not_found' and result['complete']


def test_duplicate_ids_across_documents_require_qualification(tmp_path, capsys):
    data, _, _ = setup(tmp_path)
    save(tmp_path, data, 'model-other.json')
    code, result = run(tmp_path, capsys)
    assert code == 0 and len(result['results']) == 4
    assert len({json.dumps(item['identity'], sort_keys=True) for item in result['results']}) == 4
    code, result = run(tmp_path, capsys, '--id', 's', '--kind', 'hook')
    assert code == 4 and result['status'] == 'ambiguous'
    assert len(result['selection']['candidates']) == 2
    code, result = run(tmp_path, capsys, '--id', 's', '--document', 'model.json')
    assert code == 0 and len(result['results']) == 1


def test_duplicate_ids_within_document_remain_separate(tmp_path, capsys):
    data, _, _ = setup(tmp_path)
    data['scripts'].append(copy.deepcopy(data['scripts'][0]))
    save(tmp_path, data)
    code, result = run(tmp_path, capsys, '--id', 's')
    assert code == 4 and result['status'] == 'ambiguous'
    assert {item['pointer'] for item in result['selection']['candidates']} == {'/scripts/0', '/scripts/1'}
    code, result = run(tmp_path, capsys, '--kind', 'script')
    assert len(result['results']) == 2
    assert any(d.get('kind') == 'duplicate' for d in result['diagnostics'])


@pytest.mark.parametrize('body', ['{', '{"scripts": false}', 'null'])
def test_malformed_corpus_keeps_available_results_partial(tmp_path, capsys, body):
    setup(tmp_path)
    (tmp_path / 'model-bad.json').write_text(body)
    code, result = run(tmp_path, capsys)
    assert code == 1 and result['status'] == 'partial' and not result['complete']
    assert len(result['results']) == 2 and result['diagnostics']
    code, result = run(tmp_path, capsys, '--id', 'absent')
    assert code == 1 and result['selection']['status'] == 'unresolved'


def test_invalid_readable_records_are_visible(tmp_path, capsys):
    data, _, _ = setup(tmp_path)
    del data['scripts'][0]['evidence']
    save(tmp_path, data)
    code, result = run(tmp_path, capsys, '--id', 's')
    assert code == 1 and not result['complete']
    item, = result['results']
    assert item['record'] == data['scripts'][0]
    assert item['conformance'] == 'invalid'
    assert item['evidence_status'] == 'not_assessed'


@pytest.mark.parametrize('change, expected', [('stale', 'stale'), ('missing', 'missing')])
def test_evidence_failure_is_visible_without_losing_records(tmp_path, capsys, change, expected):
    setup(tmp_path)
    if change == 'stale':
        (tmp_path / 's.md').write_text('changed evidence')
    else:
        (tmp_path / 's.md').unlink()
    code, result = run(tmp_path, capsys, '--id', 's')
    assert code == 0 and result['complete']
    item, = result['results']
    assert item['evidence_status'] == expected and item['conformance'] == 'valid'
    assert result['diagnostics']


def test_overlap_deduplicates_and_retains_invalid_assessment(tmp_path, capsys):
    _, schema, config = setup(tmp_path)
    config['schemas'].append(config['schemas'][0].copy())
    (tmp_path / 'ubiq.yaml').write_text(yaml.safe_dump(config))
    code, result = run(tmp_path, capsys)
    assert code == 0 and len(result['results']) == 2
    assert len(result['results'][0]['assessments']) == 2
    schema['required'] = ['absent']
    (tmp_path / 'strict.json').write_text(json.dumps(schema))
    config['schemas'][1]['schema'] = 'strict.json'
    (tmp_path / 'ubiq.yaml').write_text(yaml.safe_dump(config))
    code, result = run(tmp_path, capsys)
    assert code == 1 and len(result['results']) == 2 and not result['complete']
    assert all(item['conformance'] == 'invalid' for item in result['results'])
    assert all(item['evidence_status'] == 'not_assessed' for item in result['results'])


def test_non_graph_binding_cannot_hide_invalid_overlap(tmp_path, capsys):
    _, _, config = setup(tmp_path)
    (tmp_path / 'strict.json').write_text(json.dumps({'required': ['absent']}))
    config['schemas'].append({'schema': 'strict.json', 'files': ['model.json']})
    (tmp_path / 'ubiq.yaml').write_text(yaml.safe_dump(config))
    code, result = run(tmp_path, capsys)
    assert code == 1 and all(r['conformance'] == 'invalid' for r in result['results'])


def test_only_declared_collections_and_escaped_pointers(tmp_path, capsys):
    data, schema, _ = setup(tmp_path)
    data['scripts/~'] = data.pop('scripts')
    schema['x-ubiq']['collections']['scripts/~'] = schema['x-ubiq']['collections'].pop('scripts')
    data['proposals'] = [{'id': 'not-accepted', 'kind': 'script', 'domain': 'delivery'}]
    (tmp_path / 'schema.json').write_text(json.dumps(schema))
    save(tmp_path, data)
    code, result = run(tmp_path, capsys, '--kind', 'script')
    assert code == 0
    item, = result['results']
    assert item['metadata']['pointer'] == '/scripts~1~0/0'


@pytest.mark.parametrize('failure', ['schema', 'pattern'])
def test_unavailable_binding_is_not_empty_success(tmp_path, capsys, failure):
    _, _, config = setup(tmp_path)
    if failure == 'schema':
        (tmp_path / 'schema.json').unlink()
    else:
        config['schemas'][0]['files'] = ['absent.json']
        (tmp_path / 'ubiq.yaml').write_text(yaml.safe_dump(config))
    code, result = run(tmp_path, capsys)
    assert code == 1 and not result['complete'] and result['diagnostics']


def test_no_collections_is_explicit_empty_scope(tmp_path, capsys):
    setup(tmp_path)
    (tmp_path / 'schema.json').write_text('{}')
    code, result = run(tmp_path, capsys)
    assert code == 0 and result['results'] == [] and result['scope']['documents'] == []
    assert result['scope']['collections'] == 0


def test_local_query_does_not_load_dependencies(tmp_path, capsys):
    _, _, config = setup(tmp_path)
    config['edges'] = {'external': [{'name': 'absent', 'path': '../absent', 'required': False}]}
    (tmp_path / 'ubiq.yaml').write_text(yaml.safe_dump(config))
    code, result = run(tmp_path, capsys)
    assert code == 0 and len(result['results']) == 2


def test_deterministic_json_and_readable_complete_record(tmp_path, capsys):
    setup(tmp_path)
    assert main(['query', '--root', str(tmp_path), '--json']) == 0
    first = capsys.readouterr().out
    assert main(['query', '--root', str(tmp_path), '--json']) == 0
    assert capsys.readouterr().out == first
    assert main(['query', '--root', str(tmp_path), '--id', 's']) == 0
    text = capsys.readouterr().out
    for value in ('model.json', '/scripts/0', 'declared input', 'contract', 'fresh', 'sha256'):
        assert value in text


def test_revision_describes_observed_head(tmp_path, capsys):
    setup(tmp_path)
    for args in [('init', '-q'), ('add', '.'), ('-c', 'user.name=Test', '-c',
                 'user.email=test@example.com', 'commit', '-qm', 'initial')]:
        subprocess.run(['git', *args], cwd=tmp_path, check=True, capture_output=True)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=tmp_path, text=True).strip()
    code, result = run(tmp_path, capsys)
    assert code == 0 and all(item['repository']['revision'] == revision for item in result['results'])


def test_invalid_config_uses_query_envelope(tmp_path, capsys):
    (tmp_path / 'ubiq.yaml').write_text('schemas: invalid')
    code, result = run(tmp_path, capsys)
    assert code == 1 and result['version'] == 1 and result['status'] == 'unavailable'
    assert not result['complete'] and result['results'] == []


def test_later_slice_flags_are_usage_errors(tmp_path, capsys):
    setup(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(['query', '--root', str(tmp_path), '--incoming'])
    assert exc.value.code == 2


@pytest.mark.parametrize('scope', ['binding', 'pattern', 'walk'])
def test_scan_error_retains_available_records(tmp_path, capsys, monkeypatch, scope):
    import errno
    import os
    from pathlib import Path

    _, _, config = setup(tmp_path)
    denied = tmp_path / 'denied'
    denied.mkdir()
    if scope == 'binding':
        config['schemas'].append({'schema': 'schema.json', 'files': ['denied/*.json']})
    elif scope == 'pattern':
        config['schemas'][0]['files'].append('denied/*.json')
    else:
        config['schemas'][0]['files'] = ['**/model*.json']
    (tmp_path / 'ubiq.yaml').write_text(yaml.safe_dump(config))
    scandir = os.scandir

    def scan(path):
        if Path(path) == denied:
            raise PermissionError(errno.EACCES, 'Permission denied', str(path))
        return scandir(path)

    monkeypatch.setattr(os, 'scandir', scan)
    code, result = run(tmp_path, capsys)
    assert code == 1 and result['status'] == 'partial' and not result['complete']
    assert len(result['results']) == 2
    assert all(item['metadata']['file'] == 'model.json' for item in result['results'])
    assert any(d['code'] == 'E005' and d['file'] == 'denied'
               and 'Permission denied' in d['message'] for d in result['diagnostics'])
