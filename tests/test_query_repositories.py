"""Query configured checkouts without losing repository identity or pin policy."""

import hashlib
import json
import subprocess

import pytest
import yaml
from test_query import run, save, setup

from ubiq.cli import main
from ubiq.config import InvalidConfig, load_config
from ubiq.dependencies import validate_checkout


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True).strip()


def commit(root):
    git(root, 'init', '-q')
    git(root, 'add', '.')
    git(root, '-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-qm', 'corpus')
    return git(root, 'rev-parse', 'HEAD')


def configure(root, config, entries):
    config['edges'] = {'external': entries}
    (root / 'ubiq.yaml').write_text(yaml.safe_dump(config))


def workspace(tmp_path):
    local, dependency = tmp_path / 'local', tmp_path / 'dependency'
    local.mkdir()
    dependency.mkdir()
    _, _, config = setup(local)
    data, schema, other_config = setup(dependency)
    entry = {'name': 'shared', 'path': '../dependency', 'required': True}
    configure(local, config, [entry])
    return local, dependency, config, entry, data, schema, other_config


def snapshot(root, name):
    (root / name).write_text(f'{name} evidence')
    return {'path': name, 'sha256': hashlib.sha256((root / name).read_bytes()).hexdigest(),
            'anchor': 'evidence'}


def test_repository_selects_only_named_dependency(tmp_path, capsys):
    local, dependency, *_ = workspace(tmp_path)
    code, result = run(local, capsys, '--repository', 'shared', '--id', 's')
    assert code == 0 and result['complete']
    item, = result['results']
    assert item['identity']['repository'] == str(dependency)
    assert item['metadata']['file'] == 'model.json'
    assert result['scope']['mode'] == 'repository' and result['scope']['requested_repository'] == 'shared'
    entry, = result['scope']['repositories']
    assert entry['name'] == 'shared' and entry['root'] == str(dependency) and entry['status'] == 'available'
    assert result['scope']['documents'] == [str(dependency / 'model.json')]


def test_all_preserves_duplicate_ids_and_resolves_before_filters(tmp_path, capsys):
    local, dependency, *_ = workspace(tmp_path)
    code, result = run(local, capsys, '--all-repositories')
    assert code == 0 and len(result['results']) == 4
    assert {item['identity']['repository'] for item in result['results']} == {str(local), str(dependency)}
    code, result = run(local, capsys, '--all-repositories', '--id', 's', '--kind', 'hook')
    assert code == 4 and result['status'] == 'ambiguous'
    assert len(result['selection']['candidates']) == 2


def test_repository_relationships_resolve_inside_seed_corpus(tmp_path, capsys):
    local, dependency, _, _, data, *_ = workspace(tmp_path)
    code, result = run(local, capsys, '--repository', 'shared', '--id', 'h', '--outgoing')
    assert code == 0 and result['results'][0]['identity']['repository'] == str(dependency)
    assert result['relationships'][0]['endpoints']['to']['identity']['repository'] == str(dependency)
    data['scripts'] = []
    save(dependency, data)
    code, result = run(local, capsys, '--repository', 'shared', '--id', 'h', '--outgoing')
    assert code == 1 and not result['results']
    assert result['relationships'][0]['endpoints']['to']['status'] == 'missing'


def test_all_relationship_seed_is_globally_unique(tmp_path, capsys):
    local, _, *_ = workspace(tmp_path)
    code, result = run(local, capsys, '--all-repositories', '--id', 'h', '--incoming')
    assert code == 4 and result['relationships'] == []


def test_optional_absence_is_visible_but_explicit_selection_fails(tmp_path, capsys):
    local, _, config, entry, *_ = workspace(tmp_path)
    entry.update(path='../absent', required=False)
    configure(local, config, [entry])
    code, result = run(local, capsys, '--all-repositories')
    assert code == 0 and result['complete'] and len(result['results']) == 2
    optional, = [e for e in result['scope']['repositories'] if e['name'] == 'shared']
    assert optional['status'] == 'skipped_optional' and optional['reason']
    code, result = run(local, capsys, '--repository', 'shared')
    assert code == 1 and result['status'] == 'unavailable' and not result['complete']


@pytest.mark.parametrize('failure', ['missing', 'config', 'file'])
def test_unavailable_dependencies_keep_healthy_results(tmp_path, capsys, failure):
    local, dependency, config, entry, *_ = workspace(tmp_path)
    if failure == 'missing':
        entry['path'] = '../absent'
    elif failure == 'config':
        entry['required'] = False
        (dependency / 'ubiq.yaml').write_text('schemas: invalid')
    else:
        entry.update(path='../not-directory', required=False)
        (tmp_path / 'not-directory').write_text('file')
    configure(local, config, [entry])
    code, result = run(local, capsys, '--all-repositories')
    assert code == 1 and result['status'] == 'partial' and len(result['results']) == 2
    assert all(item['identity']['repository'] == str(local) for item in result['results'])
    assert any(d['repository'] != str(local) for d in result['diagnostics'])
    code, result = run(local, capsys, '--all-repositories', '--id', 'absent')
    assert code == 1 and result['selection']['status'] == 'unresolved'


def test_malformed_unpinned_corpus_retains_readable_records(tmp_path, capsys):
    local, dependency, *_ = workspace(tmp_path)
    (dependency / 'model-bad.json').write_text('{')
    code, result = run(local, capsys, '--all-repositories')
    assert code == 1 and len(result['results']) == 4
    assert any(d['repository'] == str(dependency) and d['code'] == 'E009' for d in result['diagnostics'])


def test_unknown_name_and_selector_conflict_are_explicit(tmp_path, capsys):
    local, *_ = workspace(tmp_path)
    for name in ['unknown', 'local', 'dependency']:
        code, result = run(local, capsys, '--repository', name)
        assert code == 1 and result['status'] == 'unavailable' and result['diagnostics']
    with pytest.raises(SystemExit) as exc:
        main(['query', '--root', str(local), '--repository', 'shared', '--all-repositories'])
    assert exc.value.code == 2


def test_dependency_query_does_not_load_local_glossary(tmp_path, capsys):
    local, _, config, entry, *_ = workspace(tmp_path)
    config['glossary'] = ['bad/*.md']
    (local / 'bad').mkdir()
    (local / 'bad/a.md').write_text('---\nterm: collision\n---')
    (local / 'bad/b.md').write_text('---\nterm: collision\n---')
    configure(local, config, [entry])
    code, result = run(local, capsys, '--repository', 'shared')
    assert code == 0 and len(result['results']) == 2


def test_pinned_revision_and_observed_revision_are_reported(tmp_path, capsys):
    local, dependency, config, entry, *_ = workspace(tmp_path)
    revision = commit(dependency)
    entry['revision'] = revision
    configure(local, config, [entry])
    code, result = run(local, capsys, '--repository', 'shared')
    assert code == 0
    repository, = result['scope']['repositories']
    assert repository['revision'] == repository['observed_revision'] == revision
    assert all(item['repository']['revision'] == revision for item in result['results'])
    entry['revision'] = '0' * 40
    configure(local, config, [entry])
    code, result = run(local, capsys, '--all-repositories')
    assert code == 1 and len(result['results']) == 2
    assert any('revision mismatch' in d['message'] for d in result['diagnostics'])


@pytest.mark.parametrize('changed', ['model.json', 's.md', 'h.md', 'reference.md', 'domain.md', 'edge.md'])
def test_pin_checks_all_typed_inputs_before_filtering(tmp_path, capsys, changed):
    local, dependency, config, entry, data, *_ = workspace(tmp_path)
    data['scripts'][0]['evidence'].append(snapshot(dependency, 'reference.md'))
    data['domains'][0]['evidence'] = [snapshot(dependency, 'domain.md')]
    data['relationships'][0]['evidence'] = snapshot(dependency, 'edge.md')
    save(dependency, data)
    entry['revision'] = commit(dependency)
    configure(local, config, [entry])
    with (dependency / changed).open('a') as output:
        output.write('\n ')
    code, result = run(local, capsys, '--repository', 'shared', '--id', 's')
    assert code == 1 and result['status'] == 'unavailable' and not result['results']
    assert any('dirty' in d['message'] and changed in d['message'] for d in result['diagnostics'])


@pytest.mark.parametrize('state', ['deleted', 'untracked', 'ignored'])
def test_pin_rejects_missing_or_untracked_declared_source(tmp_path, capsys, state):
    local, dependency, config, entry, *_ = workspace(tmp_path)
    if state in ('untracked', 'ignored'):
        (dependency / '.gitignore').write_text('s.md\n' if state == 'ignored' else '')
        git(dependency, 'init', '-q')
        git(dependency, 'add', 'schema.json', 'model.json', 'h.md', 'ubiq.yaml', '.gitignore')
        git(dependency, '-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-qm', 'corpus')
        entry['revision'] = git(dependency, 'rev-parse', 'HEAD')
    else:
        entry['revision'] = commit(dependency)
        (dependency / 's.md').unlink()
    configure(local, config, [entry])
    code, result = run(local, capsys, '--repository', 'shared')
    assert code == 1 and any('s.md' in d['message'] and 'dirty' in d['message']
                            for d in result['diagnostics'])


def test_pin_rejects_source_symlink_leaving_checkout(tmp_path, capsys):
    local, dependency, config, entry, *_ = workspace(tmp_path)
    external = tmp_path / 'external.md'
    external.write_bytes((dependency / 's.md').read_bytes())
    (dependency / 's.md').unlink()
    (dependency / 's.md').symlink_to(external)
    entry['revision'] = commit(dependency)
    configure(local, config, [entry])
    code, result = run(local, capsys, '--repository', 'shared')
    assert code == 1 and any('leave checkout' in d['message'] for d in result['diagnostics'])


def test_aliases_deduplicate_results_but_validate_each_pin(tmp_path, capsys):
    local, dependency, config, entry, *_ = workspace(tmp_path)
    entry['revision'] = commit(dependency)
    alias = tmp_path / 'alias'
    alias.symlink_to(dependency, target_is_directory=True)
    second = {**entry, 'name': 'alias', 'path': '../alias'}
    configure(local, config, [entry, second])
    code, result = run(local, capsys, '--all-repositories', '--kind', 'script')
    assert code == 0 and len(result['results']) == 2
    assert len(result['scope']['repositories']) == 3
    assert {e['root'] for e in result['scope']['repositories']} == {str(local), str(dependency)}
    second['revision'] = '0' * 40
    configure(local, config, [entry, second])
    code, result = run(local, capsys, '--all-repositories', '--kind', 'script')
    assert code == 1 and len(result['results']) == 2
    assert any(e['name'] == 'alias' and e['status'] == 'unavailable' for e in result['scope']['repositories'])


def test_legacy_paths_are_all_scope_only_and_missing_is_partial(tmp_path, capsys):
    local, _, config, _, *_ = workspace(tmp_path)
    configure(local, config, ['../dependency', '../missing'])
    code, result = run(local, capsys, '--all-repositories')
    assert code == 1 and len(result['results']) == 4
    assert all(e['name'] is None for e in result['scope']['repositories'])
    assert any(e['status'] == 'unavailable' for e in result['scope']['repositories'])
    code, result = run(local, capsys, '--repository', 'dependency')
    assert code == 1 and result['status'] == 'unavailable'


def test_scope_is_direct_only_and_local_default_is_isolated(tmp_path, capsys):
    local, dependency, config, entry, _, _, other_config = workspace(tmp_path)
    configure(dependency, other_config, [{'name': 'nested', 'path': '../absent', 'required': True}])
    code, result = run(local, capsys, '--all-repositories')
    assert code == 0 and len(result['scope']['repositories']) == 2
    entry['revision'] = '0' * 40
    configure(local, config, [entry])
    code, result = run(local, capsys)
    assert code == 0 and len(result['results']) == 2 and 'repositories' not in result['scope']


def test_pin_includes_composition_doc_closure(tmp_path, capsys):
    local, dependency, config, entry, _, _, other_config = workspace(tmp_path)
    other_config['docs'] = ['entry.md']
    (dependency / 'entry.md').write_text('[additional](linked.md)')
    (dependency / 'linked.md').write_text('linked source')
    (dependency / 'ubiq.yaml').write_text(yaml.safe_dump(other_config))
    entry['revision'] = commit(dependency)
    configure(local, config, [entry])
    (dependency / 'linked.md').write_text('changed')
    code, result = run(local, capsys, '--repository', 'shared')
    assert code == 1 and any('linked.md' in d['message'] and 'dirty' in d['message']
                            for d in result['diagnostics'])


def test_repository_output_is_deterministic(tmp_path, capsys):
    local, *_ = workspace(tmp_path)
    args = ['query', '--root', str(local), '--all-repositories', '--json']
    assert main(args) == 0
    first = capsys.readouterr().out
    assert main(args) == 0
    assert capsys.readouterr().out == first


def test_unique_global_seed_does_not_resolve_neighbors_globally(tmp_path, capsys):
    local, dependency, *_ = workspace(tmp_path)
    data = json.loads((local / 'model.json').read_text())
    data['hooks'][0]['id'] = 'local-h'
    data['relationships'][0]['from'] = 'local-h'
    save(local, data)
    code, result = run(local, capsys, '--all-repositories', '--id', 'h', '--outgoing')
    assert code == 0 and len(result['results']) == len(result['relationships']) == 1
    assert result['results'][0]['identity']['repository'] == str(dependency)


@pytest.mark.parametrize('change', ['target', 'symlink'])
def test_pin_checks_both_source_symlink_and_internal_target(tmp_path, capsys, change):
    local, dependency, config, entry, *_ = workspace(tmp_path)
    body = (dependency / 's.md').read_bytes()
    (dependency / 'real.md').write_bytes(body)
    (dependency / 'other.md').write_bytes(body)
    (dependency / 's.md').unlink()
    (dependency / 's.md').symlink_to('real.md')
    entry['revision'] = commit(dependency)
    configure(local, config, [entry])
    if change == 'target':
        (dependency / 'real.md').write_text('changed evidence')
    else:
        (dependency / 's.md').unlink()
        (dependency / 's.md').symlink_to('other.md')
    code, result = run(local, capsys, '--repository', 'shared')
    assert code == 1 and any('dirty' in d['message'] for d in result['diagnostics'])


def test_unavailable_root_keeps_repository_scope_and_diagnostic_attribution(tmp_path, capsys):
    (tmp_path / 'ubiq.yaml').write_text('schemas: invalid')
    code, result = run(tmp_path, capsys, '--all-repositories')
    assert code == 1 and result['scope']['mode'] == 'all_repositories'
    assert result['diagnostics'][0]['repository'] == str(tmp_path)


@pytest.mark.parametrize('input_kind', ['schema', 'catalog'])
def test_pin_rejects_retargeted_schema_or_catalog_symlink(tmp_path, capsys, input_kind):
    local, dependency, config, entry, _, _, other_config = workspace(tmp_path)
    if input_kind == 'schema':
        path = dependency / 'schema.json'
    else:
        path = dependency / 'catalog.json'
        path.write_text('{"items": []}')
        other_config['catalogs'] = [{'file': 'catalog.json', 'items': 'items', 'term': 'name',
                                    'cover': []}]
        (dependency / 'ubiq.yaml').write_text(yaml.safe_dump(other_config))
    body = path.read_bytes()
    (dependency / 'first.json').write_bytes(body)
    (dependency / 'second.json').write_bytes(body)
    path.unlink()
    path.symlink_to('first.json')
    entry['revision'] = commit(dependency)
    configure(local, config, [entry])
    path.unlink()
    path.symlink_to('second.json')
    with pytest.raises(InvalidConfig, match=path.name):
        validate_checkout(load_config(local).edges.external[0], load_config(dependency))
    code, result = run(local, capsys, '--repository', 'shared')
    assert code == 1 and any(path.name in d['message'] and 'dirty' in d['message']
                            for d in result['diagnostics'])


@pytest.mark.parametrize('chain', ['directory', 'file', 'external'])
def test_pin_checks_every_symlink_node_in_declared_inputs(tmp_path, capsys, chain):
    local, dependency, config, entry, data, *_ = workspace(tmp_path)
    body = (dependency / 's.md').read_bytes()
    if chain == 'directory':
        for directory in ['first', 'second']:
            (dependency / directory).mkdir()
            (dependency / directory / 's.md').write_bytes(body)
        link = dependency / 'source-alias'
        link.symlink_to('first', target_is_directory=True)
        data['scripts'][0]['source'] = 'source-alias/s.md'
        data['scripts'][0]['evidence'][0]['path'] = 'source-alias/s.md'
        target = 'second'
    else:
        (dependency / 'first.md').write_bytes(body)
        (dependency / 'second.md').write_bytes(body)
        (dependency / 's.md').unlink()
        if chain == 'file':
            link = dependency / 'middle.md'
            link.symlink_to('first.md')
            (dependency / 's.md').symlink_to('middle.md')
        else:
            link = tmp_path / 'external.md'
            link.symlink_to(dependency / 'first.md')
            (dependency / 's.md').symlink_to(link)
        target = 'second.md' if chain == 'file' else str(dependency / 'second.md')
    save(dependency, data)
    entry['revision'] = commit(dependency)
    configure(local, config, [entry])
    if chain != 'external':
        code, result = run(local, capsys, '--repository', 'shared')
        assert code == 0 and result['results']  # Valid in-checkout symlink chains still work.
    link.unlink()
    link.symlink_to(target, target_is_directory=chain == 'directory')
    code, result = run(local, capsys, '--repository', 'shared')
    assert code == 1 and result['status'] == 'unavailable'
    expected = 'leave checkout' if chain == 'external' else 'dirty'
    assert any(expected in d['message'] for d in result['diagnostics'])


def test_pinned_symlink_cycle_is_an_invalid_checkout(tmp_path, capsys):
    local, dependency, config, entry, *_ = workspace(tmp_path)
    (dependency / 's.md').unlink()
    (dependency / 's.md').symlink_to('middle.md')
    (dependency / 'middle.md').symlink_to('s.md')
    entry['revision'] = commit(dependency)
    configure(local, config, [entry])
    with pytest.raises(InvalidConfig, match='cannot verify revision'):
        validate_checkout(load_config(local).edges.external[0], load_config(dependency), [dependency / 's.md'])
    code, result = run(local, capsys, '--repository', 'shared')
    assert code == 1 and result['status'] == 'unavailable'


@pytest.mark.parametrize('changed', ['api.py', 'api.md', 'use_api.py'])
def test_pin_checks_symbol_contracts_and_consumers(tmp_path, changed):
    local, dependency, config, entry, _, _, other_config = workspace(tmp_path)
    other_config['symbols'] = {'coverage': ['api.py']}
    (dependency / 'ubiq.yaml').write_text(yaml.safe_dump(other_config))
    (dependency / 'api.py').write_text('def public(): pass\n')
    (dependency / 'api.md').write_text('---\nsymbols: {}\n---\n')
    entry['revision'] = commit(dependency)
    configure(local, config, [entry])
    edge, = load_config(local).edges.external
    dependency_config = load_config(dependency)
    validate_checkout(edge, dependency_config)

    (dependency / changed).write_text('changed after the pin\n')
    with pytest.raises(InvalidConfig, match=changed):
        validate_checkout(edge, dependency_config)
