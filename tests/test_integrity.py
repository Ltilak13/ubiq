import copy
import hashlib

from ubiq.integrity import check_integrity, validate_spec
from ubiq.records import Glossary, Term


def example(root):
    (root / 's.md').write_text('source evidence')
    (root / 'h.md').write_text('hook evidence')
    def evidence(path):
        body = (root / path).read_bytes()
        return {'path': path, 'sha256': hashlib.sha256(body).hexdigest(), 'anchor': 'evidence'}
    data = {
        'domains': [{'id': 'delivery', 'evidence': [evidence('s.md')]}],
        'scripts': [{'id': 's', 'kind': 'script', 'domain': 'delivery', 'source': 's.md',
                     'evidence': [evidence('s.md')]}],
        'hooks': [{'id': 'h', 'kind': 'hook', 'domain': 'delivery', 'source': 'h.md',
                   'handler': 's', 'evidence': [evidence('h.md')]}],
        'relationships': [{'id': 'calls', 'from': 'h', 'to': 's', 'kind': 'invokes',
                           'evidence': evidence('h.md')}],
        'interactions': [],
    }
    spec = {'collections': {'scripts': 'script', 'hooks': 'hook'}, 'domains': 'domains',
            'relationships': 'relationships', 'interactions': 'interactions',
            'roles': {'invokes': {'from': ['hook'], 'to': ['script']}},
            'references': [{'kind': 'hook', 'field': 'handler', 'target_kind': 'script',
                            'relationship': 'invokes'}],
            'coverage': {'glossary': True, 'exclude': []}, 'evidence': True}
    glossary = Glossary()
    glossary.add(Term('source', 'core', root / 's.md'))
    glossary.add(Term('hook', 'core', root / 'h.md'))
    return data, spec, glossary


def test_graph_rejects_invalid_constraints(tmp_path):
    data, spec, glossary = example(tmp_path)
    validate_spec(spec)
    def check(value):
        return check_integrity(value, spec, tmp_path, glossary, tmp_path / 'model.yaml')
    assert check(data) == []
    mutations = [
        ('duplicate', lambda d: d['scripts'].append(copy.deepcopy(d['scripts'][0]))),
        ('unknown domain', lambda d: d['scripts'][0].update(domain='missing')),
        ('endpoint', lambda d: d['relationships'][0].update(to='missing')),
        ('types', lambda d: d['relationships'][0].update(to='h')),
        ('handler', lambda d: d['hooks'][0].update(handler='h')),
        ('exactly one', lambda d: d.update(relationships=[])),
        ('drift', lambda d: d['scripts'][0]['evidence'][0].update(sha256='0' * 64)),
        ('anchor', lambda d: d['scripts'][0]['evidence'][0].update(anchor='not present')),
        ('coverage', lambda d: d.update(hooks=[], relationships=[])),
        ('source', lambda d: d['scripts'][0].update(source='../external')),
        ('interaction', lambda d: d['interactions'].append(
            {'from': 'missing', 'to': 'delivery', 'via': ['calls']})),
    ]
    for expected, mutate in mutations:
        bad = copy.deepcopy(data)
        mutate(bad)
        errors = check(bad)
        assert errors and any(expected in d.message for d in errors), (expected, errors)
        assert all(d.code == 'E010' and d.is_error for d in errors)


def test_graph_exclusions_must_be_explicit_and_current(tmp_path):
    data, spec, glossary = example(tmp_path)
    data['hooks'] = []
    data['relationships'] = []
    spec['coverage']['exclude'] = [{'source': 'h.md', 'reason': 'Owned upstream'}]
    assert not check_integrity(data, spec, tmp_path, glossary, tmp_path / 'model.yaml')
    spec['coverage']['exclude'][0]['source'] = 'missing.md'
    assert any('exclusion' in d.message for d in check_integrity(
        data, spec, tmp_path, glossary, tmp_path / 'model.yaml'))
    spec['coverage']['exclude'][0]['reason'] = ''
    try:
        validate_spec(spec)
    except ValueError:
        pass
    else:
        assert False, 'empty exclusion reason accepted'


def test_graph_invalid_shapes_are_diagnostics(tmp_path):
    data, spec, glossary = example(tmp_path)
    for value in (None, [], {'scripts': [None]}, {**data, 'domains': []}):
        assert check_integrity(value, spec, tmp_path, glossary, tmp_path / 'model.yaml')


def test_graph_cyclic_exclusion_is_diagnostic(tmp_path):
    data, spec, glossary = example(tmp_path)
    (tmp_path / 'cycle').symlink_to('cycle')
    spec['coverage']['exclude'] = [{'source': 'cycle', 'reason': 'External dependency'}]
    errors = check_integrity(data, spec, tmp_path, glossary, tmp_path / 'model.yaml')
    assert any(d.code == 'E010' and 'exclusion' in d.message for d in errors)


def test_findings_are_categorized_without_reading_messages(tmp_path):
    from ubiq.integrity import assess_integrity
    data, spec, glossary = example(tmp_path)
    cases = [
        (lambda d: d['relationships'][0].update(to='missing'), ('relationship', 'unresolved', ('h',))),
        (lambda d: d['relationships'][0].update(to='h'), ('relationship', 'incompatible', ('h', 'h'))),
        (lambda d: d['hooks'][0].update(handler='missing'), ('relationship', 'unresolved', ('h',))),
        (lambda d: d['scripts'][0]['evidence'][0].update(sha256='0' * 64), ('evidence', 'stale', ('s',))),
        (lambda d: d['scripts'][0]['evidence'][0].update(path='gone.md'), ('evidence', 'missing', ('s',))),
        (lambda d: d['scripts'][0]['evidence'][0].update(path='/abs.md'), ('evidence', 'invalid', ('s',))),
        (lambda d: d.update(scripts=[None]), ('shape', 'invalid', ())),
    ]
    for mutate, expected in cases:
        bad = copy.deepcopy(data)
        mutate(bad)
        found = {(f.category, f.kind, f.records) for f in assess_integrity(bad, spec, tmp_path, glossary)}
        assert expected in found, (expected, found)


def test_reference_to_wrong_kind_is_incompatible_not_unresolved(tmp_path):
    from ubiq.integrity import assess_integrity
    data, spec, glossary = example(tmp_path)
    data['hooks'][0]['handler'] = 'h'  # exists, but is a hook, not a script
    found = {(f.category, f.kind) for f in assess_integrity(data, spec, tmp_path, glossary)}
    assert ('relationship', 'incompatible') in found
    assert ('relationship', 'unresolved') not in found


def test_dependency_records_do_not_require_local_coverage(tmp_path):
    data, spec, glossary = example(tmp_path)
    dependency = Glossary()
    dependency.add(Term('dependency', 'core', tmp_path / 'vendor' / 'dep.md'))
    glossary.add_external('vendor', dependency)
    assert not check_integrity(data, spec, tmp_path, glossary, tmp_path / 'model.yaml')

    data['hooks'] = []
    data['relationships'] = []
    errors = check_integrity(data, spec, tmp_path, glossary, tmp_path / 'model.yaml')
    assert len(errors) == 1
    assert 'registered source has no typed record' in errors[0].message
    assert str(tmp_path / 'h.md') in errors[0].message


def test_local_symlink_requires_exclusion_even_when_dependency_imports_it(tmp_path):
    root = tmp_path / 'local'
    root.mkdir()
    data, spec, glossary = example(root)
    external = tmp_path / 'external.md'
    external.write_text('external evidence')
    link = root / 'linked.md'
    link.symlink_to(external)
    glossary.add(Term('linked', 'core', link))
    dependency = Glossary()
    dependency.add(Term('linked', 'core', external))
    glossary.add_external('vendor', dependency)
    errors = check_integrity(data, spec, root, glossary, root / 'model.yaml')
    assert len(errors) == 1 and 'no typed record' in errors[0].message
    spec['coverage']['exclude'] = [{'source': 'linked.md', 'reason': 'Owned upstream'}]
    assert not check_integrity(data, spec, root, glossary, root / 'model.yaml')
    glossary.terms.pop()
    assert any('stale exclusion' in d.message for d in check_integrity(
        data, spec, root, glossary, root / 'model.yaml'))


def test_build_with_named_dependency_and_native_coverage(tmp_path):
    import json

    import yaml

    from ubiq.cli import _check

    root = tmp_path / 'local'
    root.mkdir()
    data, spec, _ = example(root)
    (root / 's.md').write_text('---\nterm: source\n---\nsource evidence')
    data['scripts'][0]['evidence'][0]['sha256'] = hashlib.sha256(
        (root / 's.md').read_bytes()).hexdigest()
    data['domains'][0]['evidence'] = copy.deepcopy(data['scripts'][0]['evidence'])
    data['relationships'][0]['evidence'] = copy.deepcopy(data['scripts'][0]['evidence'][0])
    (root / 'model.json').write_text(json.dumps(data))
    (root / 'schema.json').write_text(json.dumps({'x-ubiq': spec}))
    dependency = tmp_path / 'dependency'
    dependency.mkdir()
    (dependency / 'dep.md').write_text('---\nterm: dependency\n---\n')
    (dependency / 'ubiq.yaml').write_text('glossary: [dep.md]\ndocs: []\n')
    (root / 'ubiq.yaml').write_text(yaml.safe_dump({
        'glossary': ['s.md'], 'docs': [],
        'edges': {'external': [{'name': 'vendor', 'path': '../dependency', 'required': True}]},
        'schemas': [{'schema': 'schema.json', 'files': ['model.json'], 'format': 'document'}],
    }))
    diagnostics, _, _ = _check(root)
    assert not [d for d in diagnostics if d.is_error]
