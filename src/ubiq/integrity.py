"""Check schema-declared record graphs, source coverage, and evidence snapshots."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

from .check import Diagnostic
from .records import Glossary, parse_frontmatter
from .scan import _covers, _interpret_markdown, _mask, resolve_doc_link

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
_SPEC['properties']['source_references'] = {
    'type': 'array', 'uniqueItems': True, 'items': _object({
        'kind': _TEXT, 'field': _TEXT, 'target_kind': _TEXT, 'relationship': _TEXT,
        'direction': {'enum': ['incoming', 'outgoing']}, 'body_section': _TEXT})}
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
    for ref in spec.get('source_references', []):
        role = spec['roles'].get(ref['relationship'])
        source, target = ('to', 'from') if ref['direction'] == 'incoming' else ('from', 'to')
        if role is None or ref['kind'] not in role[source] or ref['target_kind'] not in role[target]:
            raise ValueError('x-ubiq.source_references: reference types must match the declared relationship role')
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


@dataclass(frozen=True)
class Finding:
    """One E010 failure, categorized so callers never parse its message.

    category: shape, graph, source, relationship, evidence, or coverage.
    kind: what failed within the category, such as unresolved or stale.
    records: ids of the source records the failure concerns, if any.
    """
    category: str
    kind: str
    message: str
    records: tuple[str, ...] = ()


def check_integrity(data, spec, root: Path, glossary: Glossary, file: Path) -> list[Diagnostic]:
    """Check a structurally valid instance against the configured graph contract."""
    return [Diagnostic('E010', f.message, file) for f in assess_integrity(data, spec, root, glossary)]


def assess_integrity(data, spec, root: Path, glossary: Glossary) -> list[Finding]:
    """Assess stored and source-derived declarations without changing the input."""
    return assess_model(data, spec, root, glossary)[1]


def relationship_owner(edge):
    """Evidence belongs to the declaring record, including inverse declarations."""
    origin = edge.get('derived_from')
    if isinstance(origin, dict) and isinstance(origin.get('record'), str):
        return origin['record']
    return edge['from']


def assess_model(data, spec, root: Path, glossary: Glossary):
    """Return the effective graph and findings; derived edges retain source provenance."""
    if not Draft202012Validator(_shape(spec)).is_valid(data):
        return data, _assess_integrity(data, spec, root, glossary)
    reserved = [Finding('shape', 'reserved', 'derived_from is reserved for generated provenance')
                for edge in data[spec['relationships']] if 'derived_from' in edge]
    if reserved:
        return data, reserved + _assess_integrity(data, spec, root, glossary)
    if not spec.get('source_references'):
        return data, _assess_integrity(data, spec, root, glossary)
    root = root.resolve()
    records = [record for name in spec['collections'] for record in data[name]]
    edges = list(data[spec['relationships']])
    found = []
    for ref in spec['source_references']:
        for record in records:
            if record['kind'] != ref['kind']:
                continue
            try:
                if ref['field'] in record:
                    raise ValueError(f"{ref['field']} belongs only in source frontmatter")
                source = Path(record['source'])
                path = (root / source).resolve()
                if source.is_absolute() or '..' in source.parts or not path.is_relative_to(root):
                    raise ValueError('source must stay inside the repository')
                meta, body = parse_frontmatter(path)
                value = meta.get(ref['field'])
                targets = [item for item in records if item['id'] == value]
                if len(targets) != 1 or targets[0]['kind'] != ref['target_kind']:
                    raise ValueError(f"{ref['field']} must resolve to one {ref['target_kind']}")
                target = targets[0]
                # Use the scanner's masked prose and resolved Markdown links, so code
                # examples and comments cannot satisfy the visible-link contract.
                document = _interpret_markdown(body)
                headings = list(re.finditer(r'^#{1,2} +(.+?) *#* *$',
                                            _mask(document.prose, document.comments), re.MULTILINE))
                sections = [(heading.end(), headings[i + 1].start() if i + 1 < len(headings) else len(body))
                            for i, heading in enumerate(headings)
                            if heading.group(0).startswith('## ') and heading[1] == ref['body_section']]
                if len(sections) != 1:
                    raise ValueError(f"expected one ## {ref['body_section']} section")
                start, end = sections[0]
                hidden = _covers(document.comments)
                links = [resolve_doc_link(path, dest, root) for offset, _, dest in document.links
                         if start <= offset < end and not hidden(offset)]
                if not links or set(links) != {(root / target['source']).resolve()}:
                    raise ValueError(f"{ref['body_section']} links must match {ref['field']}")
                snapshots = [item for item in record['evidence'] if item['path'] == record['source']]
                if len(snapshots) != 1:
                    raise ValueError('expected one primary evidence snapshot')
                origin, destination = (target, record) if ref['direction'] == 'incoming' else (record, target)
                if any(edge['kind'] == ref['relationship'] and
                       edge['to' if ref['direction'] == 'incoming' else 'from'] == record['id']
                       for edge in edges):
                    found.append(Finding('shape', 'duplicate-source-reference',
                                         f"{record['id']}: source-derived relationship also declared elsewhere",
                                         (record['id'],)))
                    continue
                edges.append(dict(id=f"{record['id']}--{ref['field']}",
                                  **{'from': origin['id'], 'to': destination['id']},
                                  kind=ref['relationship'], evidence=dict(snapshots[0]),
                                  derived_from={'file': record['source'], 'field': ref['field'],
                                                    'record': record['id']}))
            except (OSError, ValueError, RuntimeError) as exc:
                found.append(Finding('relationship', 'source-reference',
                                     f"{record['id']}: {exc}", (record['id'],)))
    effective = {**data, spec['relationships']: edges}
    return effective, found + _assess_integrity(effective, spec, root, glossary)


def _assess_integrity(data, spec, root: Path, glossary: Glossary) -> list[Finding]:
    """Every integrity failure of a structurally valid instance, categorized."""
    found: list[Finding] = []

    def error(category, kind, message, *records):
        found.append(Finding(category, kind, message, tuple(r for r in records if isinstance(r, str))))

    for invalid in Draft202012Validator(_shape(spec)).iter_errors(data):
        location = '/' + '/'.join(map(str, invalid.absolute_path))
        error('shape', 'invalid', f'graph {location}: {invalid.message}')
    if found:
        return found
    root = root.resolve()
    records = [record for name in spec['collections'] for record in data[name]]
    domains = data[spec['domains']]
    relationships = data[spec['relationships']]
    interactions = data[spec['interactions']]

    def index(items, label):
        result = {}
        for item in items:
            if item['id'] in result:
                error('graph', 'duplicate', f"{label}: duplicate identity {item['id']}",
                      item['id'] if label == 'records' else None)
            result[item['id']] = item
        return result

    nodes = index(records, 'records')
    domain_ids = index(domains, 'domains')
    edges = index(relationships, 'relationships')
    sources = {}

    def source_path(value, label, category, owner=None):
        path = Path(value)
        if path.is_absolute() or '..' in path.parts:
            error(category, 'invalid', f'{label}: source path must be repository-relative: {value}', owner)
            return None
        try:
            path = (root / path).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                error(category, 'missing', f'{label}: missing or external source {value}', owner)
                return None
        except (OSError, ValueError, RuntimeError) as exc:
            error(category, 'invalid', f'{label}: invalid source {value}: {exc}', owner)
            return None
        return path

    for record in records:
        if record['domain'] not in domain_ids:
            error('graph', 'unknown-domain', f"{record['id']}: unknown domain {record['domain']}", record['id'])
        path = source_path(record['source'], record['id'], 'source', record['id'])
        if path is not None:
            if path in sources:
                error('graph', 'duplicate-source', f"{record['id']}: duplicate source {record['source']}",
                      record['id'])
            sources[path] = record
        if record['source'] not in {item['path'] for item in record['evidence']}:
            error('evidence', 'missing', f"{record['id']}: primary source has no evidence snapshot",
                  record['id'])

    for edge in relationships:
        source, target = nodes.get(edge['from']), nodes.get(edge['to'])
        role = spec['roles'].get(edge['kind'])
        if source is None or target is None:
            error('relationship', 'unresolved', f"{edge['id']}: unresolved relationship endpoint",
                  *(edge[end] for end in ('from', 'to') if edge[end] in nodes))
        elif role is None or source['kind'] not in role['from'] or target['kind'] not in role['to']:
            error('relationship', 'incompatible', f"{edge['id']}: incompatible relationship types",
                  edge['from'], edge['to'])
    for ref in spec['references']:
        for record in records:
            if record['kind'] != ref['kind']:
                continue
            value = record.get(ref['field'])
            target = nodes.get(value) if isinstance(value, str) else None
            if target is None or target['kind'] != ref['target_kind']:
                error('relationship', 'unresolved' if target is None else 'incompatible',
                      f"{record['id']}: {ref['field']} must resolve to {ref['target_kind']}", record['id'])
            matching = [edge for edge in relationships if
                        (edge['from'], edge['kind'], edge['to']) ==
                        (record['id'], ref['relationship'], value)]
            if len(matching) != 1:
                error('relationship', 'undeclared',
                      f"{record['id']}: expected exactly one {ref['field']} relationship", record['id'])
    represented = set()
    for interaction in interactions:
        if interaction['from'] not in domain_ids or interaction['to'] not in domain_ids:
            error('graph', 'interaction', 'interaction: unknown domain')
        for edge_id in interaction['via']:
            edge = edges.get(edge_id)
            if edge is None:
                error('graph', 'interaction', f'interaction: unknown relationship {edge_id}')
            elif edge['from'] in nodes and edge['to'] in nodes:
                pair = (nodes[edge['from']]['domain'], nodes[edge['to']]['domain'])
                if pair != (interaction['from'], interaction['to']):
                    error('graph', 'interaction', f'{edge_id}: interaction contradicts endpoint domains',
                          edge['from'], edge['to'])
                else:
                    represented.add(edge_id)
    for edge in relationships:
        source, target = nodes.get(edge['from']), nodes.get(edge['to'])
        if (source and target and source['domain'] != target['domain']
                and edge['id'] not in represented):
            error('graph', 'interaction', f"{edge['id']}: cross-domain relationship has no interaction",
                  edge['from'], edge['to'])

    # Imported records support link resolution, not local coverage obligations.
    registered = {term.file.resolve() for term in glossary.terms}
    excluded = set()
    for exclusion in spec['coverage']['exclude']:
        try:
            path = (root / exclusion['source']).resolve()
        except (OSError, ValueError, RuntimeError) as exc:
            error('coverage', 'invalid', f"coverage: invalid exclusion {exclusion['source']}: {exc}")
            continue
        if path not in registered:
            error('coverage', 'stale', f"coverage: stale exclusion {exclusion['source']}")
        if path in sources:
            error('coverage', 'conflict',
                  f"coverage: represented source is also excluded: {exclusion['source']}")
        excluded.add(path)
    for path in sorted(registered - excluded - set(sources)):
        error('coverage', 'untyped', f'coverage: registered source has no typed record: {path}')

    # Each snapshot belongs to the record that carries it; domain snapshots to none.
    evidence = [(item, record['id']) for record in records for item in record['evidence']]
    evidence += [(item, None) for domain in domains for item in domain['evidence']]
    evidence += [(edge['evidence'], relationship_owner(edge))
                 for edge in relationships]
    snapshots = {}
    for item, owner in evidence:
        path = source_path(item['path'], 'evidence', 'evidence', owner)
        if path is None:
            continue
        try:
            if path not in snapshots:
                body = path.read_bytes()
                snapshots[path] = (hashlib.sha256(body).hexdigest(), body.decode('utf-8'))
            digest, text = snapshots[path]
        except (OSError, UnicodeError) as exc:
            error('evidence', 'invalid', f"evidence: cannot read {item['path']}: {exc}", owner)
            continue
        if digest != item['sha256']:
            error('evidence', 'stale', f"evidence drift: {item['path']}", owner)
        if item['anchor'] not in text:
            error('evidence', 'stale', f"evidence anchor missing: {item['path']}", owner)
    return found
