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
