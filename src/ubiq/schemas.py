"""Opt-in JSON Schema validation, separate from lexical vocabulary parsing."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from . import xref
from .check import Diagnostic
from .config import SchemaSpec
from .globs import GlobError
from .integrity import Finding, assess_integrity, validate_spec
from .kinds import by_id, by_name
from .records import FRONTMATTER_RE, normalize
from .scan import SKIP_FIELD_VALUES, Ref

if TYPE_CHECKING:
    from jsonschema.protocols import Validator

DIALECT = "https://json-schema.org/draft/2020-12/schema"


class _TypedLoader(yaml.SafeLoader):
    """JSON scalar types in YAML; legacy spellings such as `on` stay strings."""


_TypedLoader.yaml_implicit_resolvers = {
    first: [(tag, regex) for tag, regex in resolvers
            if tag not in {"tag:yaml.org,2002:bool", "tag:yaml.org,2002:int",
                           "tag:yaml.org,2002:float", "tag:yaml.org,2002:timestamp"}]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_TypedLoader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$"), list("tf"))
_TypedLoader.add_implicit_resolver("tag:yaml.org,2002:int", re.compile(r"^-?(?:0|[1-9][0-9]*)$"), list("-0123456789"))
_TypedLoader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+(?:[eE][+-]?[0-9]+)?|[eE][+-]?[0-9]+)$"),
    list("-0123456789"))


def _mapping(loader, node):
    pairs = [(loader.construct_object(k), loader.construct_object(v)) for k, v in node.value]
    return _unique_mapping(pairs)


def _unique_mapping(pairs):
    result = {}
    for key, value in pairs:
        if not isinstance(key, str):
            raise TypeError("object keys must be strings")
        if key in result:
            raise ValueError(f"duplicate object key: {key}")
        result[key] = value
    return result


_TypedLoader.add_constructor("tag:yaml.org,2002:map", _mapping)


def _json_value(value, active=None):
    """Reject YAML-only objects and cycles before a validator can recurse."""
    active = set() if active is None else active
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        json.dumps(value, allow_nan=False)
        return
    if not isinstance(value, (dict, list)):
        raise TypeError(f"not a JSON value: {type(value).__name__}")
    if id(value) in active:
        raise ValueError("cyclic data is not supported")
    active.add(id(value))
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("object keys must be strings")
            _json_value(item, active)
    else:
        for item in value:
            _json_value(item, active)
    active.remove(id(value))


def load_data(path: Path, *, frontmatter: bool = False):
    """Read strict JSON-compatible YAML/JSON, or a Markdown frontmatter mapping."""
    text = path.read_text(encoding="utf-8")
    if frontmatter:
        match = FRONTMATTER_RE.match(text)
        if match is None:
            raise ValueError("required YAML frontmatter is missing or not closed")
        text = match.group(1)
    value = (json.loads(text, object_pairs_hook=_unique_mapping)
             if path.suffix.lower() == ".json" and not frontmatter
             else yaml.load(text, Loader=_TypedLoader))
    _json_value(value)
    if frontmatter and not isinstance(value, dict):
        raise ValueError("frontmatter must be a mapping")
    return value


def _schema_locations(resource):
    """Collect declared schema positions, excluding annotations and instance values."""
    locations = {id(resource.contents)}
    for child in resource.subresources():
        locations.update(_schema_locations(child))
    return locations


def _check_refs(resource, resolver, locations):
    """Inspect schema positions only; examples/defaults are instance data."""
    value = resource.contents
    if not isinstance(value, dict):
        return
    if "$schema" in value and value["$schema"] != DIALECT:
        raise ValueError(f"only {DIALECT} is supported")
    for key in ("$ref", "$dynamicRef"):
        if key in value:
            if not isinstance(value[key], str) or not value[key].startswith("#"):
                raise ValueError(f"{key}: only same-document fragment references are supported")
            target = resolver.lookup(value[key]).contents
            if id(target) not in locations:
                raise ValueError(f"{key}: target must be a declared schema location")
    for child in resource.subresources():
        _check_refs(child, resolver.in_subresource(child), locations)


def _pointer(parts):
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts)


BUNDLED = "ubiq-file:"  # prefix of the $defs keys under which load_schema inlines files


def load_schema(root: Path, path: Path):
    """A schema with each relative-file `$ref` inlined, so every reference is same-document.

    `"$ref": "tracking.json#/properties/pr"` names a schema file next to this one. Its
    contents are copied to `$defs["ubiq-file:.ubiq/schemas/tracking.json"]` (the key is
    the file's repository path) and the reference is
    rewritten to point there; the copied file's own references are rewritten the same way.
    Only files inside `root` can be referenced, and a reference with a scheme (`https:`)
    stays as written, which the validator rejects (E008).
    """
    root = Path(root).resolve()
    schema = load_data(path)
    files: dict[str, Any] = {}

    def key_of(base: Path, target: str) -> str:
        resolved = (base.parent / target).resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ValueError(f"$ref: {target!r} names no schema file inside the repository")
        name = resolved.relative_to(root).as_posix()
        if name not in files:
            files[name] = None  # reserve the key first, so a reference cycle ends
            files[name] = rewrite(load_data(resolved), resolved, f"/$defs/{_escape(BUNDLED + name)}")
        return name

    def rewrite(node: Any, base: Path, prefix: str) -> Any:
        if isinstance(node, list):
            return [rewrite(item, base, prefix) for item in node]
        if not isinstance(node, dict):
            return node
        out = {k: rewrite(v, base, prefix) for k, v in node.items()}
        for key in ("$ref", "$dynamicRef"):
            ref = node.get(key)
            if not isinstance(ref, str) or ":" in ref.split("#", 1)[0]:
                continue
            target, _, fragment = ref.partition("#")
            if target:
                out[key] = f"#/$defs/{_escape(BUNDLED + key_of(base, target))}{fragment}"
            elif prefix:
                out[key] = "#" + prefix + fragment
        return out

    path = Path(path).resolve()
    if not isinstance(schema, dict):
        return schema
    bundled = rewrite(schema, path, "")
    if files:
        bundled.setdefault("$defs", {}).update({BUNDLED + name: value for name, value in files.items()})
    return bundled


def _escape(name: str) -> str:
    return name.replace("~", "~0").replace("/", "~1")


def validate_schema(schema):
    """Validate a Draft 2020-12 schema and index its local reference targets."""
    Draft202012Validator.check_schema(schema)
    resource = DRAFT202012.create_resource(schema)
    resolver = Registry().resolver_with_root(resource)
    locations = _schema_locations(resource)
    _check_refs(resource, resolver, locations)
    return resolver, locations


def _validator(root: Path, location: str):
    filename, separator, fragment = location.partition("#")
    path = root / filename
    schema = load_schema(root, path)
    resolver, locations = validate_schema(schema)
    validator: Validator = Draft202012Validator(schema, registry=Registry())
    selected = schema
    if separator:
        # Resolve eagerly so missing fragments fail even with an empty target set.
        reference = "#" + fragment
        resolved = resolver.lookup(reference).contents
        if id(resolved) not in locations:
            raise ValueError("schema fragment must select a declared schema location")
        Draft202012Validator.check_schema(resolved)
        selected = resolved
        validator = validator.evolve(schema={"$ref": reference})
    return selected, validator


def _annotations(root: Path, location: str) -> list[xref.Annotation]:
    """The `x-ubiq-ref` annotations of the schema (or fragment) at `location`."""
    filename, _, fragment = location.partition("#")
    document = load_schema(root, root / filename)
    selected = xref.pointer(document, "#" + fragment) if fragment else document
    return xref.collect(selected, document)


def _in_namespace(glossary, ref: Ref):
    """A record id or name that resolves, among the records of the annotation's namespace."""
    return [t for t in by_id(glossary, ref) if t.ns == ref.ns] or by_name(glossary, ref)


def edge_names(cfg) -> set[str]:
    """The edge and field names that bound schemas declare with `x-ubiq-ref`."""
    names: set[str] = set()
    for spec in cfg.schemas:
        try:
            for annotation in _annotations(cfg.root, spec.schema):
                names.add(annotation.ref.edge)
                if annotation.steps and annotation.steps[-1][0] == "key":
                    names.add(annotation.steps[-1][1])
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, yaml.YAMLError, RecursionError):
            continue  # an unreadable schema is E008
    return names


def xref_refs(cfg) -> list[Ref]:
    """A field reference for each value of an `x-ubiq-ref` property in a bound file.

    Each resolves to a record in the annotation's namespace (E006 when none does) and
    makes an edge named by the annotation. A top-level field that `ref_fields` already
    resolves keeps its `ref_fields` meaning, so it is not read twice. Files and schemas
    that cannot be read, or do not conform, are reported (E005, E008, E009) elsewhere.
    """
    refs: list[Ref] = []
    field_policy = cfg.policies["field"]
    for spec in cfg.schemas:
        try:
            found = _annotations(cfg.root, spec.schema)
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, yaml.YAMLError, RecursionError):
            continue
        if not found or spec.format != "frontmatter":
            continue  # the other formats have no lines to point at
        policy = replace(field_policy, resolve=_in_namespace)
        paths: set[Path] = set()
        for pattern in spec.files:
            try:
                paths.update(p for p in pattern.walk(cfg.ignore)
                             if not any(g.matches(p) for g in cfg.ignore))
            except GlobError:
                continue
        for path in sorted(paths):
            try:
                data = load_data(path, frontmatter=True)
                match = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError, TypeError, yaml.YAMLError, RecursionError):
                continue
            text = match.group(1) if match else ""
            for annotation in found:
                if annotation.ref.within:
                    continue  # names in the same file: step_refs.py checks them
                for keys, value in xref.values(data, annotation.steps):
                    value = value.strip().strip("'\"")
                    if (not value or value.lower() in SKIP_FIELD_VALUES
                            or (len(keys) == 1 and keys[0] in cfg.ref_fields)):
                        continue
                    ref = annotation.ref
                    if ref.edge == "requires" and xref.pr_entry(value) is not None:
                        continue  # `pr: <n>` names a pull request, not a record
                    field_name = keys[-1] if keys else ref.edge
                    refs.append(Ref(policy, f"{field_name}: {value}", normalize(value), ref.ns,
                                    path, xref.line_of(text, keys), target=value, edge=ref.edge))
    return refs


def single_diagnostics(cfg) -> list[Diagnostic]:
    """E009 for a `single` property that names more than one record, at the field's line.

    Reads the same files as `xref_refs`; unreadable files and schemas are reported
    elsewhere. Values that are not strings are the schema's to report.
    """
    found_errors: list[Diagnostic] = []
    for spec in cfg.schemas:
        try:
            found = [a for a in _annotations(cfg.root, spec.schema) if a.ref.single]
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, yaml.YAMLError, RecursionError):
            continue
        if not found or spec.format != "frontmatter":
            continue
        paths: set[Path] = set()
        for pattern in spec.files:
            try:
                paths.update(p for p in pattern.walk(cfg.ignore)
                             if not any(g.matches(p) for g in cfg.ignore))
            except GlobError:
                continue
        for path in sorted(paths):
            try:
                data = load_data(path, frontmatter=True)
                match = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError, TypeError, yaml.YAMLError, RecursionError):
                continue
            text = match.group(1) if match else ""
            for annotation in found:
                for keys, names in xref.groups(data, annotation.steps):
                    if len(names) > 1:
                        found_errors.append(Diagnostic(
                            "E009", f"{'.'.join(keys)}: {annotation.ref.edge} names {len(names)} "
                            f"records ({', '.join(names)}); at most one is allowed",
                            path, xref.line_of(text, keys)))
    return found_errors


@dataclass
class Target:
    """One file a binding selects: what loaded, and how it conforms."""
    path: Path
    errors: list[str] = field(default_factory=list)  # E009 messages; empty when conforming
    data: object = None
    loaded: bool = False
    # E010 findings; None when not assessed (no x-ubiq extension, or not conforming).
    integrity: list[Finding] | None = None


@dataclass
class Binding:
    """One `schemas` entry, assessed: the schema, its extension, and its targets."""
    index: int
    spec: SchemaSpec
    error: str | None = None  # the schema or its x-ubiq extension cannot load (E008)
    extension: dict | None = None
    unmatched: list[str] = field(default_factory=list)  # file patterns that matched nothing
    targets: list[Target] = field(default_factory=list)
    scan_errors: list[tuple[str, GlobError]] = field(default_factory=list)


def assess_schemas(cfg, glossary, *, retain_scan_errors: bool = False) -> list[Binding]:
    """Assess bindings. Opt-in scan recovery retains targets discovered before failure."""
    bindings = []
    for index, spec in enumerate(cfg.schemas):
        binding = Binding(index, spec)
        bindings.append(binding)
        try:
            schema, validator = _validator(cfg.root, spec.schema)
            if isinstance(schema, dict) and "x-ubiq" in schema:
                validate_spec(schema["x-ubiq"])
                binding.extension = schema["x-ubiq"]
            _annotations(cfg.root, spec.schema)
        except (OSError, UnicodeError, ValueError, TypeError, yaml.YAMLError, SchemaError,
                Unresolvable, RecursionError) as exc:
            binding.error = str(exc)
            continue
        paths = set()
        for pattern in spec.files:
            matches = set()
            try:
                for path in pattern.walk(cfg.ignore):
                    if not any(g.matches(path) for g in cfg.ignore):
                        matches.add(path)
            except GlobError as exc:
                if not retain_scan_errors:
                    raise
                binding.scan_errors.append((pattern.pattern, exc))
            else:
                if not matches:
                    binding.unmatched.append(pattern.pattern)
            paths.update(matches)
        for path in sorted(paths):
            target = Target(path)
            binding.targets.append(target)
            try:
                target.data = load_data(path, frontmatter=spec.format == "frontmatter")
                target.loaded = True
                target.errors = [f"{_pointer(e.absolute_path)}: {e.message}"
                                 for e in validator.iter_errors(target.data)]
                if not target.errors and binding.extension is not None:
                    target.integrity = assess_integrity(target.data, binding.extension,
                                                        cfg.root, glossary)
            except (OSError, UnicodeError, ValueError, TypeError, yaml.YAMLError, Unresolvable, RecursionError) as exc:
                target.errors = [f"schema validation failed: {exc}"]
    return bindings


def check_schemas(cfg, glossary, bindings: list[Binding] | None = None):
    """Return E008 schema/config errors and E009 target conformance errors."""
    diagnostics = []
    for binding in assess_schemas(cfg, glossary) if bindings is None else bindings:
        if binding.error is not None:
            diagnostics.append(Diagnostic("E008", f"schema {binding.spec.schema}: {binding.error}",
                                          cfg.root / "ubiq.yaml"))
            continue
        diagnostics.extend(Diagnostic("E005", f"cannot scan schema pattern {pattern}: {error}",
                                      Path(error.filename) if error.filename else cfg.root)
                           for pattern, error in binding.scan_errors)
        diagnostics.extend(Diagnostic("E009", f"schema target pattern matched no files: {pattern}",
                                      cfg.root / "ubiq.yaml") for pattern in binding.unmatched)
        for target in binding.targets:
            diagnostics.extend(Diagnostic("E009", message, target.path) for message in target.errors)
            diagnostics.extend(Diagnostic("E010", f.message, target.path)
                               for f in target.integrity or [])
    return diagnostics
