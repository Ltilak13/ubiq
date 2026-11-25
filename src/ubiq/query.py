"""Read complete records from schema-declared collections without interpreting prose."""

from __future__ import annotations

import json
from pathlib import Path

from .config import Config
from .coverage import _assessed, _integrity
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


def select(cfg: Config, glossary: Glossary, *, kind: str | None = None,
           domain: str | None = None, ident: str | None = None,
           document: str | None = None) -> dict:
    """Select local declarations. Integrity diagnostics do not assert semantic truth."""
    bindings = assess_schemas(cfg, glossary, retain_scan_errors=True)
    repository = _repository(cfg.root)
    diagnostics: list[dict] = []
    complete = True
    documents: set[str] = set()
    collections: set[tuple[str, str]] = set()
    records: dict[tuple[str, str], dict] = {}
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
                    records.setdefault((file, pointer), {
                        'identity': {'repository': str(cfg.root), 'document': file, 'id': record['id']},
                        'repository': repository, 'metadata': {'file': file, 'pointer': pointer},
                        'record': record})

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
        checked = [_assessment(b, t, item['identity']['id'], file) for b, t in assessments[file]]
        item['assessments'] = checked
        item['conformance'] = ('invalid' if any(a['conformance'] == 'invalid' for a in checked)
                               else 'valid')
        evidence = {a['evidence_status'] for a, (b, _) in zip(checked, assessments[file])
                    if b.extension is not None}
        item['evidence_status'] = ('not_assessed' if item['conformance'] == 'invalid' else
                                   next((s for s in ('not_assessed', 'invalid', 'missing', 'stale')
                                         if s in evidence), 'fresh'))

    available = [item for (file, _), item in sorted(records.items())
                 if document is None or file == document]
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
    results = [item for item in available
               if (kind is None or item['record'].get('kind') == kind)
               and (domain is None or item['record'].get('domain') == domain)]
    status = 'partial' if not complete else (
        selection['status'] if selection['status'] in ('not_found', 'ambiguous') else 'ok')
    # Identical overlapping bindings can produce identical findings apart from the
    # binding index. Retain both so each schema assessment stays attributable.
    diagnostics.sort(key=lambda d: json.dumps(d, sort_keys=True))
    return {'version': VERSION, 'status': status, 'complete': complete,
            'scope': {'repository': str(cfg.root), 'documents': sorted(documents),
                      'collections': len(collections)},
            'selection': selection, 'results': results, 'diagnostics': diagnostics}


def exit_code(report: dict) -> int:
    return {'ok': 0, 'partial': 1, 'unavailable': 1, 'not_found': 3, 'ambiguous': 4}[report['status']]


def render(report: dict) -> str:
    """Show complete records and their provenance in readable output."""
    lines = [f"query: {report['status']} ({len(report['results'])} records)"]
    for item in report['results']:
        lines.append(f"\n{item['identity']['id']} — {item['metadata']['file']}#{item['metadata']['pointer']}")
        lines.append(json.dumps(item, indent=2, sort_keys=True, ensure_ascii=False))
    if report['selection'].get('candidates'):
        lines.append(json.dumps(report['selection'], indent=2, sort_keys=True, ensure_ascii=False))
    for diagnostic in report['diagnostics']:
        lines.append(f"{diagnostic['code']} {diagnostic['file']}: {diagnostic['message']}")
    if not report['scope']['collections']:
        lines.append('No schema-declared record collections are available.')
    return '\n'.join(lines)
