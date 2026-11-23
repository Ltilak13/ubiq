"""Check schema-declared record graphs, source coverage, and evidence snapshots."""

from __future__ import annotations

import hashlib
from pathlib import Path

from jsonschema import Draft202012Validator

from .check import Diagnostic
from .records import Glossary

_TEXT = {'type': 'string', 'minLength': 1, 'pattern': r'\S'}
_TEXTS = {'type': 'array', 'items': _TEXT, 'minItems': 1, 'uniqueItems': True}


def _object(properties, required=None):
    return {'type': 'object', 'properties': properties,
            'required': list(properties) if required is None else required,
            'additionalProperties': False}


_SPEC = _object({
    'collections': {'type': 'object', 'minProperties': 1, 'propertyNames': _TEXT,
                    'additionalProperties': _TEXT},
    'domains': _TEXT, 'relationships': _TEXT, 'interactions': _TEXT,
    'roles': {'type': 'object', 'propertyNames': _TEXT,
              'additionalProperties': _object({'from': _TEXTS, 'to': _TEXTS})},
    'references': {'type': 'array', 'uniqueItems': True, 'items': _object({
        'kind': _TEXT, 'field': _TEXT, 'target_kind': _TEXT, 'relationship': _TEXT})},
    'coverage': _object({'glossary': {'const': True}, 'exclude': {
        'type': 'array', 'uniqueItems': True,
        'items': _object({'source': _TEXT, 'reason': _TEXT})}}),
    'evidence': {'const': True},
})
_EVIDENCE = _object({'path': _TEXT, 'sha256': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'},
                     'anchor': _TEXT})


def validate_spec(spec) -> None:
    """Reject malformed or contradictory x-ubiq graph declarations."""
    errors = list(Draft202012Validator(_SPEC).iter_errors(spec))
    if errors:
        raise ValueError(f"x-ubiq: {errors[0].message}")
    selectors = [*spec['collections'], spec['domains'], spec['relationships'], spec['interactions']]
    if len(set(selectors)) != len(selectors):
        raise ValueError('x-ubiq: collection selectors must be distinct')
    kinds = set(spec['collections'].values())
    for role in spec['roles'].values():
        if not {*role['from'], *role['to']} <= kinds:
            raise ValueError('x-ubiq.roles: all endpoint kinds must have a collection')
    for ref in spec['references']:
        role = spec['roles'].get(ref['relationship'])
        if role is None or ref['kind'] not in role['from'] or ref['target_kind'] not in role['to']:
            raise ValueError('x-ubiq.references: reference types must match the declared relationship role')
    exclusions = [item['source'] for item in spec['coverage']['exclude']]
    if len(set(exclusions)) != len(exclusions):
        raise ValueError('x-ubiq.coverage: duplicate exclusion source')
    for source in exclusions:
        if Path(source).is_absolute() or '..' in Path(source).parts:
            raise ValueError('x-ubiq.coverage: exclusion paths must be repository-relative')


def _shape(spec):
    """Require graph fields even when the caller's JSON Schema omits them."""
    def records(properties):
        item = _object(properties)
        item['additionalProperties'] = True
        return {'type': 'array', 'items': item}
    evidence = {'type': 'array', 'items': _EVIDENCE, 'minItems': 1}
    properties = {name: records({'id': _TEXT, 'kind': {'const': kind}, 'domain': _TEXT,
                                 'source': _TEXT, 'evidence': evidence})
                  for name, kind in spec['collections'].items()}
    properties[spec['domains']] = {**records({'id': _TEXT, 'evidence': evidence}), 'minItems': 1}
    properties[spec['relationships']] = records({'id': _TEXT, 'from': _TEXT, 'to': _TEXT,
                                                  'kind': _TEXT, 'evidence': _EVIDENCE})
    properties[spec['interactions']] = records({'from': _TEXT, 'to': _TEXT, 'via': _TEXTS})
    return {**_object(properties), 'additionalProperties': True}


def check_integrity(data, spec, root: Path, glossary: Glossary, file: Path) -> list[Diagnostic]:
    """Check a structurally valid instance against the configured graph contract."""
    diags: list[Diagnostic] = []

    def error(message):
        diags.append(Diagnostic('E010', message, file))

    for invalid in Draft202012Validator(_shape(spec)).iter_errors(data):
        location = '/' + '/'.join(map(str, invalid.absolute_path))
        error(f'graph {location}: {invalid.message}')
    if diags:
        return diags
    root = root.resolve()
    records = [record for name in spec['collections'] for record in data[name]]
    domains = data[spec['domains']]
    relationships = data[spec['relationships']]
    interactions = data[spec['interactions']]

    def index(items, label):
        result = {}
        for item in items:
            if item['id'] in result:
                error(f"{label}: duplicate identity {item['id']}")
            result[item['id']] = item
        return result

    nodes = index(records, 'records')
    domain_ids = index(domains, 'domains')
    edges = index(relationships, 'relationships')
    sources = {}

    def source_path(value, label):
        path = Path(value)
        if path.is_absolute() or '..' in path.parts:
            error(f'{label}: source path must be repository-relative: {value}')
            return None
        try:
            path = (root / path).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                error(f'{label}: missing or external source {value}')
                return None
        except (OSError, ValueError, RuntimeError) as exc:
            error(f'{label}: invalid source {value}: {exc}')
            return None
        return path

    for record in records:
        if record['domain'] not in domain_ids:
            error(f"{record['id']}: unknown domain {record['domain']}")
        path = source_path(record['source'], record['id'])
        if path is not None:
            if path in sources:
                error(f"{record['id']}: duplicate source {record['source']}")
            sources[path] = record
        if record['source'] not in {item['path'] for item in record['evidence']}:
            error(f"{record['id']}: primary source has no evidence snapshot")

    for edge in relationships:
        source, target = nodes.get(edge['from']), nodes.get(edge['to'])
        role = spec['roles'].get(edge['kind'])
        if source is None or target is None:
            error(f"{edge['id']}: unresolved relationship endpoint")
        elif role is None or source['kind'] not in role['from'] or target['kind'] not in role['to']:
            error(f"{edge['id']}: incompatible relationship types")
    for ref in spec['references']:
        for record in records:
            if record['kind'] != ref['kind']:
                continue
            value = record.get(ref['field'])
            target = nodes.get(value) if isinstance(value, str) else None
            if target is None or target['kind'] != ref['target_kind']:
                error(f"{record['id']}: {ref['field']} must resolve to {ref['target_kind']}")
            matching = [edge for edge in relationships if
                        (edge['from'], edge['kind'], edge['to']) ==
                        (record['id'], ref['relationship'], value)]
            if len(matching) != 1:
                error(f"{record['id']}: expected exactly one {ref['field']} relationship")
    represented = set()
    for interaction in interactions:
        if interaction['from'] not in domain_ids or interaction['to'] not in domain_ids:
            error('interaction: unknown domain')
        for edge_id in interaction['via']:
            edge = edges.get(edge_id)
            if edge is None:
                error(f'interaction: unknown relationship {edge_id}')
            elif edge['from'] in nodes and edge['to'] in nodes:
                pair = (nodes[edge['from']]['domain'], nodes[edge['to']]['domain'])
                if pair != (interaction['from'], interaction['to']):
                    error(f'{edge_id}: interaction contradicts endpoint domains')
                else:
                    represented.add(edge_id)
    for edge in relationships:
        source, target = nodes.get(edge['from']), nodes.get(edge['to'])
        if (source and target and source['domain'] != target['domain']
                and edge['id'] not in represented):
            error(f"{edge['id']}: cross-domain relationship has no interaction")

    registered = set(glossary.by_file)
    excluded = set()
    for exclusion in spec['coverage']['exclude']:
        try:
            path = (root / exclusion['source']).resolve()
        except (OSError, ValueError, RuntimeError) as exc:
            error(f"coverage: invalid exclusion {exclusion['source']}: {exc}")
            continue
        if path not in registered:
            error(f"coverage: stale exclusion {exclusion['source']}")
        if path in sources:
            error(f"coverage: represented source is also excluded: {exclusion['source']}")
        excluded.add(path)
    for path in sorted(registered - excluded - set(sources)):
        error(f'coverage: registered source has no typed record: {path}')

    evidence = [item for record in [*records, *domains] for item in record['evidence']]
    evidence += [edge['evidence'] for edge in relationships]
    snapshots = {}
    for item in evidence:
        path = source_path(item['path'], 'evidence')
        if path is None:
            continue
        try:
            if path not in snapshots:
                body = path.read_bytes()
                snapshots[path] = (hashlib.sha256(body).hexdigest(), body.decode('utf-8'))
            digest, text = snapshots[path]
        except (OSError, UnicodeError) as exc:
            error(f"evidence: cannot read {item['path']}: {exc}")
            continue
        if digest != item['sha256']:
            error(f"evidence drift: {item['path']}")
        if item['anchor'] not in text:
            error(f"evidence anchor missing: {item['path']}")
    return diags
