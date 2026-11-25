"""Read complete records from schema-declared collections without interpreting prose."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .coverage import _assessed, _integrity
from .integrity import relationship_owner
from .records import Glossary
from .review import BaselineError, _git
from .schemas import Binding, Target, _pointer, assess_schemas

VERSION = 1


def _path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def _repository(root: Path) -> dict:
    try:
        revision = _git(root, 'rev-parse', '--verify', 'HEAD').strip()
    except (BaselineError, OSError):
        revision = None
    return {'root': str(root), 'revision': revision, 'state': 'working_tree'}


def unavailable(root: Path, message: str) -> dict:
    """Keep query failures in the same envelope as successful selections."""
    return {'version': VERSION, 'status': 'unavailable', 'complete': False,
            'scope': {'repository': str(root), 'documents': [], 'collections': 0},
            'selection': {'status': 'unresolved'}, 'results': [],
            'diagnostics': [{'code': 'Q001', 'file': 'ubiq.yaml', 'message': message}]}


def _conformance(target: Target) -> str:
    shape = any(f.category == 'shape' for f in target.integrity or [])
    return 'invalid' if target.errors or shape else 'valid'


def _assessment(binding: Binding, target: Target, ident: str, file: str) -> dict:
    found = _assessed(target, binding)
    mine = None if found is None else [f for f in found if ident in f.records]
    evidence, _, findings = _integrity([(file, mine)])
    return {'binding': binding.index, 'schema': binding.spec.schema,
            'conformance': _conformance(target),
            'evidence_status': 'fresh' if evidence == 'ok' else evidence,
            'findings': findings}


def _wrap(record: dict, file: str, pointer: str, repository: dict) -> dict:
    return {'identity': {'repository': repository['root'], 'document': file, 'id': record.get('id')},
            'repository': repository, 'metadata': {'file': file, 'pointer': pointer}, 'record': record}


def _annotate(item: dict, bindings: list[tuple[Binding, Target]], owner: str, file: str) -> None:
    checked = [_assessment(b, t, owner, file) for b, t in bindings]
    item['assessments'] = checked
    item['conformance'] = ('invalid' if any(a['conformance'] == 'invalid' for a in checked)
                           else 'valid')
    evidence = {a['evidence_status'] for a, (b, _) in zip(checked, bindings)
                if b.extension is not None}
    item['evidence_status'] = ('not_assessed' if item['conformance'] == 'invalid' else
                               next((s for s in ('not_assessed', 'invalid', 'missing', 'stale')
                                     if s in evidence), 'fresh'))


def _matches(item: dict, kind: str | None, domain: str | None) -> bool:
    return ((kind is None or item['record'].get('kind') == kind)
            and (domain is None or item['record'].get('domain') == domain))


def _resolve(records: list[dict], complete: bool, ident: str | None, document: str | None,
             kind: str | None, domain: str | None) -> tuple[list[dict], dict]:
    available = [item for item in records if document is None or item['metadata']['file'] == document]
    selection: dict = {'kind': kind, 'domain': domain, 'id': ident, 'document': document,
                      'status': 'matched'}
    if ident is not None:
        available = [item for item in available if item['identity']['id'] == ident]
        if not available:
            selection['status'] = 'not_found' if complete else 'unresolved'
        elif len(available) > 1:
            selection['status'] = 'ambiguous'
            selection['candidates'] = [{**item['identity'], 'pointer': item['metadata']['pointer']}
                                       for item in available]
            available = []
    return available, selection


def _endpoint(declared_id, candidates: list[dict], owners: set[int],
              record_bindings: dict[tuple[str, str], set[int]]) -> dict:
    endpoint: dict = {'declared_id': declared_id}
    if not isinstance(declared_id, str) or not declared_id.strip():
        return {**endpoint, 'status': 'invalid'}
    candidates = [item for item in candidates if owners & record_bindings[
        (item['metadata']['file'], item['metadata']['pointer'])]]
    if len(candidates) == 1:
        item = candidates[0]
        if owners <= record_bindings[(item['metadata']['file'], item['metadata']['pointer'])]:
            return {**endpoint, 'status': 'resolved', 'identity': item['identity'],
                    'metadata': item['metadata']}
    endpoint['status'] = 'ambiguous' if len(candidates) > 1 else 'missing'
    if candidates:
        endpoint['candidates'] = [{'identity': item['identity'], 'metadata': item['metadata']}
                                  for item in candidates]
    return endpoint


def _follow(seed: dict, direction: str, relation: str | None, kind: str | None,
            domain: str | None, records: dict[tuple[str, str], dict],
            edges: dict[tuple[str, str], dict], record_bindings: dict[tuple[str, str], set[int]],
            edge_bindings: dict[tuple[str, str], set[int]],
            assessments: dict[str, list[tuple[Binding, Target]]]) -> tuple[list[dict], list[dict], list[dict]]:
    source, neighbor_end = ('to', 'from') if direction == 'incoming' else ('from', 'to')
    file = seed['metadata']['file']
    indexed: dict[str, list[dict]] = {}
    for (document, _), item in sorted(records.items()):
        if document == file:
            indexed.setdefault(item['identity']['id'], []).append(item)
    neighbors: dict[tuple[str, str], dict] = {}
    relationships, diagnostics = [], []
    for key, edge in sorted(edges.items()):
        declaration = edge['record']
        if key[0] != file or declaration.get(source) != seed['identity']['id']:
            continue
        if relation is not None and declaration.get('kind') != relation:
            continue
        endpoints = {}
        for end in ('from', 'to'):
            ident = declaration.get(end)
            candidates = indexed.get(ident, []) if isinstance(ident, str) else []
            endpoints[end] = _endpoint(ident, candidates, edge_bindings[key], record_bindings)
        edge['endpoints'] = endpoints
        derived = declaration.get('derived_from')
        owner = relationship_owner(declaration) if 'from' in declaration else ''
        _annotate(edge, assessments[file], owner if isinstance(owner, str) else '', file)
        edge['evidence_scope'] = 'declaring_record' if derived else 'source_record'
        statuses = {endpoint['status'] for endpoint in endpoints.values()}
        edge['resolution'] = next((state for state in ('invalid', 'ambiguous', 'missing')
                                   if state in statuses), 'resolved')
        if edge['conformance'] == 'invalid':
            edge['resolution'] = 'invalid'
        if edge['resolution'] == 'resolved':
            for binding, _ in assessments[file]:
                if binding.index not in edge_bindings[key] or binding.extension is None:
                    continue
                role = (binding.extension['roles'].get(declaration.get('kind'))
                        if isinstance(declaration.get('kind'), str) else None)
                if role is None or any(records[(file, endpoints[end]['metadata']['pointer'])]['record'].get('kind')
                                       not in role[end] for end in ('from', 'to')):
                    edge['resolution'] = 'invalid'
                    break
        endpoint = endpoints[neighbor_end]
        neighbor = (records[(file, endpoint['metadata']['pointer'])]
                    if endpoint['status'] == 'resolved' else None)
        if edge['resolution'] != 'resolved':
            diagnostics.append({'code': 'Q002', 'file': file, 'pointer': key[1],
                                'message': f"relationship {key[1]} has {edge['resolution']} endpoints or types"})
        elif neighbor is not None and not _matches(neighbor, kind, domain):
            continue
        relationships.append(edge)
        if neighbor is not None and _matches(neighbor, kind, domain):
            neighbors[(file, neighbor['metadata']['pointer'])] = neighbor
    return [item for _, item in sorted(neighbors.items())], relationships, diagnostics


def select(cfg: Config, glossary: Glossary, *, kind: str | None = None,
           domain: str | None = None, ident: str | None = None,
           document: str | None = None, direction: str | None = None,
           relation: str | None = None, bindings: list[Binding] | None = None) -> dict:
    """Select local declarations. Integrity diagnostics do not assert semantic truth."""
    if direction is None and relation is not None:
        direction = 'outgoing'
    if direction not in (None, 'incoming', 'outgoing') or direction is not None and ident is None:
        raise ValueError('relationship queries require an ID and an incoming or outgoing direction')
    if bindings is None:
        bindings = assess_schemas(cfg, glossary, retain_scan_errors=True)
    repository = _repository(cfg.root)
    diagnostics: list[dict] = []
    complete = True
    documents: set[str] = set()
    collections: set[tuple[str, str]] = set()
    records: dict[tuple[str, str], dict] = {}
    edges: dict[tuple[str, str], dict] = {}
    record_bindings: dict[tuple[str, str], set[int]] = {}
    edge_bindings: dict[tuple[str, str], set[int]] = {}
    assessments: dict[str, list[tuple[Binding, Target]]] = {}

    # Assess every overlapping binding, including ordinary structural schemas.
    # A broken schema has unknown scope and therefore cannot yield a complete answer.
    for binding in bindings:
        if binding.error is not None:
            complete = False
            diagnostics.append({'code': 'E008', 'file': 'ubiq.yaml', 'binding': binding.index,
                                'message': f'schema {binding.spec.schema}: {binding.error}'})
        if binding.scan_errors:
            complete = False
            diagnostics.extend({
                'code': 'E005', 'file': _path(Path(error.filename), cfg.root) if error.filename else '.',
                'binding': binding.index, 'pattern': pattern,
                'message': f'cannot scan schema pattern {pattern}: {error}'}
                for pattern, error in binding.scan_errors)
        for target in binding.targets:
            file = _path(target.path, cfg.root)
            assessments.setdefault(file, []).append((binding, target))
        if binding.extension is None:
            continue
        if binding.unmatched:
            complete = False
            diagnostics.extend({'code': 'E009', 'file': 'ubiq.yaml', 'binding': binding.index,
                                'message': f'schema target pattern matched no files: {pattern}'}
                               for pattern in binding.unmatched)
        for target in binding.targets:
            file = _path(target.path, cfg.root)
            documents.add(file)
            if not target.loaded or not isinstance(target.data, dict):
                continue
            for collection in sorted(binding.extension['collections']):
                collections.add((file, collection))
                items = target.data.get(collection)
                if not isinstance(items, list):
                    continue
                for index, record in enumerate(items):
                    if not isinstance(record, dict) or not isinstance(record.get('id'), str):
                        continue
                    pointer = _pointer((collection, index))
                    records.setdefault((file, pointer), _wrap(record, file, pointer, repository))
                    record_bindings.setdefault((file, pointer), set()).add(binding.index)
            if direction is not None:
                collection = binding.extension['relationships']
                items = (target.graph_data if target.graph_data is not None else target.data).get(collection)
                if isinstance(items, list):
                    for index, edge in enumerate(items):
                        if not isinstance(edge, dict):
                            continue
                        pointer = _pointer((collection, index))
                        if 'derived_from' in edge:
                            pointer = _pointer(('$derived', binding.index, collection, index))
                        edges.setdefault((file, pointer), _wrap(edge, file, pointer, repository))
                        if 'derived_from' in edge:
                            edges[(file, pointer)]['metadata']['derived_from'] = edge['derived_from']
                        edge_bindings.setdefault((file, pointer), set()).add(binding.index)

    # Non-collection documents are not query inputs. A non-collection schema that
    # also selects a queried document still contributes its conformance result.
    for file in sorted(documents):
        for binding, target in assessments[file]:
            if not target.loaded or _conformance(target) == 'invalid':
                complete = False
            diagnostics.extend({'code': 'E009', 'file': file, 'binding': binding.index,
                                'message': message} for message in target.errors)
            diagnostics.extend({'code': 'E010', 'file': file, 'binding': binding.index,
                                'category': f.category, 'kind': f.kind,
                                'records': list(f.records), 'message': f.message}
                               for f in target.integrity or [])

    for (file, _), item in sorted(records.items()):
        _annotate(item, assessments[file], item['identity']['id'], file)

    available, selection = _resolve([item for _, item in sorted(records.items())],
                                    complete, ident, document, kind, domain)
    results = [item for item in available if _matches(item, kind, domain)]
    relationships: list[dict] = []
    if direction is not None:
        selection.update(direction=direction, relation=relation)
        results = []
        if len(available) == 1:
            seed = available[0]
            selection['seed'] = {'identity': seed['identity'], 'metadata': seed['metadata']}
            results, relationships, failures = _follow(
                seed, direction, relation, kind, domain, records, edges,
                record_bindings, edge_bindings, assessments)
            diagnostics.extend(failures)
            complete = complete and not failures
    status = 'partial' if not complete else (
        selection['status'] if selection['status'] in ('not_found', 'ambiguous') else 'ok')
    # Identical overlapping bindings can produce identical findings apart from the
    # binding index. Retain both so each schema assessment stays attributable.
    diagnostics.sort(key=lambda d: json.dumps(d, sort_keys=True))
    report = {'version': VERSION, 'status': status, 'complete': complete,
            'scope': {'repository': str(cfg.root), 'documents': sorted(documents),
                      'collections': len(collections)},
            'selection': selection, 'results': results, 'diagnostics': diagnostics}
    if direction is not None:
        report['relationships'] = relationships
    return report


@dataclass
class Corpus:
    config: Config
    glossary: Glossary
    bindings: list[Binding]
    overlays: list[Path]


def declared_inputs(corpus: Corpus) -> list[Path]:
    """Collect every declared source and snapshot before applying query filters."""
    paths: set[Path] = set()
    for binding in corpus.bindings:
        spec = binding.extension
        if spec is None:
            continue
        for target in binding.targets:
            paths.add(target.path)
            if not target.loaded or not isinstance(target.data, dict):
                continue
            for name in [*spec['collections'], spec['domains'], spec['relationships']]:
                records = target.data.get(name)
                if not isinstance(records, list):
                    continue
                for record in records:
                    if not isinstance(record, dict):
                        continue
                    source = record.get('source') if name in spec['collections'] else None
                    if isinstance(source, str) and source.strip():
                        paths.add(corpus.config.root / source)
                    snapshots = record.get('evidence', [])
                    if isinstance(snapshots, dict):
                        snapshots = [snapshots]
                    if isinstance(snapshots, list):
                        for snapshot in snapshots:
                            path = snapshot.get('path') if isinstance(snapshot, dict) else None
                            if isinstance(path, str) and path.strip():
                                paths.add(corpus.config.root / path)
    # validate_checkout retains these lexical paths and also checks resolved targets.
    return sorted(paths)


def select_repositories(root: Path, corpora: dict[Path, Corpus], entries: list[dict],
                        failures: list[dict], *, requested_repository: str | None = None,
                        kind: str | None = None, domain: str | None = None,
                        ident: str | None = None, document: str | None = None,
                        direction: str | None = None, relation: str | None = None) -> dict:
    """Resolve identities over accepted checkouts before filtering or traversal."""
    if direction is None and relation is not None:
        direction = 'outgoing'
    reports = {str(path): select(c.config, c.glossary, bindings=c.bindings)
               for path, c in sorted(corpora.items())}
    diagnostics = list(failures)
    for path, report in reports.items():
        diagnostics.extend({**d, 'repository': path} for d in report['diagnostics'])
    for entry in entries:
        if entry['status'] != 'available':
            continue
        report = reports[entry['root']]
        entry.update(documents=report['scope']['documents'], collections=report['scope']['collections'])
        if not report['complete']:
            entry['status'] = 'partial'
    complete = all(e['status'] in ('available', 'skipped_optional') for e in entries) and not failures
    available, selection = _resolve([item for report in reports.values() for item in report['results']],
                                    complete, ident, document, kind, domain)
    results = [item for item in available if _matches(item, kind, domain)]
    relationships: list[dict] = []
    if direction is not None:
        selection.update(direction=direction, relation=relation)
        results = []
        if len(available) == 1:
            seed = available[0]
            path = seed['identity']['repository']
            corpus = corpora[Path(path)]
            traversed = select(corpus.config, corpus.glossary, kind=kind, domain=domain,
                               ident=ident, document=seed['metadata']['file'], direction=direction,
                               relation=relation, bindings=corpus.bindings)
            selection['seed'] = traversed['selection']['seed']
            results, relationships = traversed['results'], traversed['relationships']
            diagnostics.extend({**d, 'repository': path} for d in traversed['diagnostics'])
            complete = complete and traversed['complete']
    status = ('unavailable' if not reports else 'partial') if not complete else (
        selection['status'] if selection['status'] in ('not_found', 'ambiguous') else 'ok')
    diagnostics = [value for _, value in sorted({json.dumps(d, sort_keys=True): d
                                                for d in diagnostics}.items())]
    report = {'version': VERSION, 'status': status, 'complete': complete,
              'scope': {'repository': str(root),
                        'mode': 'repository' if requested_repository is not None else 'all_repositories',
                        'requested_repository': requested_repository,
                        'repositories': entries,
                        'documents': sorted(str(Path(path) / file) for path, r in reports.items()
                                            for file in r['scope']['documents']),
                        'collections': sum(r['scope']['collections'] for r in reports.values())},
              'selection': selection, 'results': results, 'diagnostics': diagnostics}
    if direction is not None:
        report['relationships'] = relationships
    return report


def exit_code(report: dict) -> int:
    return {'ok': 0, 'partial': 1, 'unavailable': 1, 'not_found': 3, 'ambiguous': 4}[report['status']]


def render(report: dict) -> str:
    """Show complete records and their provenance in readable output."""
    lines = [f"query: {report['status']} ({len(report['results'])} records)"]
    for item in report['results']:
        lines.append(f"\n{item['identity']['id']} — {item['metadata']['file']}#{item['metadata']['pointer']}")
        lines.append(json.dumps(item, indent=2, sort_keys=True, ensure_ascii=False))
    for edge in report.get('relationships', []):
        lines.append(f"\nrelationship {edge['identity']['id']} — "
                     f"{edge['metadata']['file']}#{edge['metadata']['pointer']}")
        lines.append(json.dumps(edge, indent=2, sort_keys=True, ensure_ascii=False))
    if report['selection'].get('candidates'):
        lines.append(json.dumps(report['selection'], indent=2, sort_keys=True, ensure_ascii=False))
    for entry in report['scope'].get('repositories', []):
        label = entry['name'] if entry['name'] is not None else entry['root']
        lines.append(f"repository {label}: {entry['status']}" +
                     (f" ({entry['reason']})" if entry.get('reason') else ''))
    for diagnostic in report['diagnostics']:
        repository = f" [{diagnostic['repository']}]" if 'repository' in diagnostic else ''
        lines.append(f"{diagnostic['code']}{repository} {diagnostic['file']}: {diagnostic['message']}")
    if not report['scope']['collections']:
        lines.append('No schema-declared record collections are available.')
    return '\n'.join(lines)
