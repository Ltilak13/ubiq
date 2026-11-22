"""Infer asset groups and candidate domain contexts from repository paths."""

from __future__ import annotations

import json
import os
from glob import escape
from pathlib import Path

import yaml

from .config import load_config
from .globs import Glob, first_match
from .records import (
    InvalidRecord,
    Term,
    normalize,
    overlay_onto,
    parse_frontmatter,
    parse_record,
)

FAMILIES = ('skills', 'rules', 'scripts', 'hooks')
EXCLUDED = ('.git', 'node_modules', '.venv', 'venv', '__pycache__',
            '.pytest_cache', '.ruff_cache', 'dist', 'build', 'vendor')
CONTAINERS = {'src', 'packages', 'services', 'apps', 'domains', 'contexts', 'glossary'}
TECHNICAL = {'src', 'lib', 'utils', 'util', 'shared', 'common', 'types', 'tests',
             'test', 'scripts', 'hooks', 'rules', 'skills', 'components'}
SCRIPT_SUFFIXES = {'.sh', '.bash', '.zsh', '.py', '.js', '.mjs', '.cjs', '.ts', '.ps1'}


def discover(root: Path) -> dict:
    """Return path groups, glossary locations, and unconfirmed context candidates.

    Directory names are evidence to review, not inferred business semantics.
    Never follow symlinks or inspect dependency/build directories.
    """
    ignore = tuple(Glob.parse(f'**/{name}/**', root) for name in EXCLUDED)
    if (root / 'ubiq.yaml').exists():
        ignore += load_config(root).ignore
    groups: dict[str, dict[str, list[str]]] = {}
    contexts: dict[str, str] = {}
    glossaries: list[str] = []
    schema_inputs: list[tuple[str, str | None, dict]] = []

    def walk_error(error: OSError):
        raise error

    for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        parent = Path(directory)
        if parent == root / '.ubiq':
            dirs[:] = [d for d in dirs if d == 'glossary']
            files = []
        dirs[:] = sorted(d for d in dirs if not (parent / d).is_symlink()
                         and not any(g.covers_dir(parent / d) for g in ignore))
        for filename in sorted(files):
            path = parent / filename
            if path.is_symlink() or not path.is_file() or first_match(ignore, path):
                continue
            relative = path.relative_to(root)
            source = relative.as_posix()
            parts = relative.parts
            group = relative.parent.as_posix()
            if filename in {'GLOSSARY.md', 'GLOSSARY-MAP.md', 'CONTEXT.md'}:
                glossaries.append(source)
                if filename == 'GLOSSARY.md':
                    contexts[group] = 'glossary'
            for index, part in enumerate(parts[:-2]):
                candidate = parts[index + 1]
                if part in CONTAINERS and candidate not in TECHNICAL and not candidate.startswith('.'):
                    context = '/'.join(parts[:index + 2])
                    contexts.setdefault(context, 'directory')
            family = None
            if filename == 'SKILL.md':
                family = 'skills'
            elif any(p in {'hooks', '.githooks', '.husky'} for p in parts[:-1]):
                family = 'hooks'
            elif 'rules' in parts[:-1] and path.suffix in {'.mdc', '.md'}:
                family = 'rules'
            elif any(p in {'scripts', 'bin'} for p in parts[:-1]) and path.suffix in SCRIPT_SUFFIXES:
                family = 'scripts'
            if 'glossary' in parts[:-1]:
                family = None
            metadata = {}
            if path.suffix in {'.md', '.mdc'}:
                try:
                    metadata, _ = parse_frontmatter(path)
                except InvalidRecord as exc:
                    raise InvalidRecord(f'{source}: {exc}') from exc
            if family or metadata:
                schema_inputs.append((source, family, metadata))
            if family:
                groups.setdefault(group, {kind: [] for kind in FAMILIES})[family].append(source)
    schemas: dict[str, dict] = {}
    for source, family, metadata in schema_inputs:
        group = Path(source).parent.as_posix()
        fields = ('name', 'term') if family == 'skills' else ('term', 'name', 'title')
        term_field = next((f for f in fields if isinstance(metadata.get(f), str) and metadata[f].strip()), None)
        storage = 'frontmatter' if term_field or not family else 'overlay'
        if isinstance(metadata.get('ns'), str) and metadata['ns'].strip():
            ns, evidence = metadata['ns'], 'frontmatter'
        elif family:
            ns, evidence = family[:-1], 'asset-kind'
        else:
            ancestors = [p for p in contexts if p != '.' and (group == p or group.startswith(p + '/'))]
            context = max(ancestors, key=len) if ancestors else None
            ns = normalize(Path(context).name) if context else 'repo'
            evidence = 'directory-candidate' if context else 'default'
        schema = {'path': group, 'storage': storage,
                  'term_field': term_field if storage == 'frontmatter' else 'term',
                  'name_source': 'frontmatter' if term_field else ('relative_path' if family else 'review_required'),
                  'ns': ns, 'namespace_evidence': evidence,
                  'fields': sorted(str(key) for key in metadata),
                  'requires_review': family not in FAMILIES or family == 'skills' and term_field is None}
        key = json.dumps(schema, sort_keys=True)
        schemas.setdefault(key, {**schema, 'files': []})['files'].append(source)
    return {'groups': dict(sorted(groups.items())),
            'schemas': list(schemas.values()),
            'contexts': [{'path': path, 'evidence': evidence} for path, evidence in sorted(contexts.items())],
            'glossaries': sorted(glossaries)}


def init_assets(root: Path, report: dict, config: dict) -> dict[Path, str]:
    """Prepare linker files without writing or editing source files."""
    writes: dict[Path, str] = {}
    catalog: dict[str, list[str]] = {kind: [] for kind in FAMILIES}
    covers: dict[str, list[str]] = {kind: [] for kind in FAMILIES}
    schemas = {source: schema for schema in report['schemas'] for source in schema['files']}
    for group in report['groups'].values():
        for family, sources in group.items():
            ns = family[:-1]
            for source in sources:
                schema = schemas[source]
                if family == 'skills' or schema['storage'] == 'frontmatter':
                    fields = [schema['term_field']] if schema['term_field'] else ['name', 'term']
                    record = parse_record(root / source, tuple(fields), default_ns=ns)
                    if record is None:
                        raise InvalidRecord(f'{source}: a skill needs name or term frontmatter')
                    config['glossary'].append({'glob': escape(source), 'term_field': fields, 'ns': ns})
                    qualified = f'{record.ns}:{record.term}'
                else:
                    # The full relative path is stable when another group adds the same filename.
                    existing, _ = parse_frontmatter(root / source)
                    metadata = {key: existing[key] for key in ('aliases', 'id') if key in existing}
                    metadata.update({'source': source, 'term': source, 'ns': schema['ns']})
                    record = overlay_onto(Term(normalize(source), ns, root / source), metadata)
                    overlay = root / '.ubiq/overlays/assets' / family / (source + '.md')
                    writes[overlay] = '---\n' + yaml.safe_dump(metadata, sort_keys=False) + '---\n'
                    qualified = record.qualified
                catalog[family].append(qualified)
                covers[family].append(escape(source))
    if any(catalog.values()):
        catalog_path = '.ubiq/catalogs/assets.json'
        writes[root / catalog_path] = json.dumps(catalog, indent=2) + '\n'
        config['catalogs'] = [
            {'file': catalog_path, 'items': family, 'term': 'literal', 'cover': covers[family]}
            for family in FAMILIES if covers[family]
        ]
    config['docs'] = list(dict.fromkeys([*config['docs'], *(escape(path) for path in report['glossaries'])]))
    if report['groups'] or report['contexts'] or report['glossaries'] or report['schemas']:
        writes[root / '.ubiq/discovery.json'] = json.dumps(report, indent=2) + '\n'
    return writes
