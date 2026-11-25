"""Opt-in JSON Schema validation, separate from lexical vocabulary parsing."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from .check import Diagnostic
from .config import SchemaSpec
from .globs import GlobError
from .integrity import Finding, assess_model, validate_spec
from .records import FRONTMATTER_RE

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


def _validator(root: Path, location: str):
    filename, separator, fragment = location.partition("#")
    path = root / filename
    schema = load_data(path)
    Draft202012Validator.check_schema(schema)
    resource = DRAFT202012.create_resource(schema)
    resolver = Registry().resolver_with_root(resource)
    locations = _schema_locations(resource)
    _check_refs(resource, resolver, locations)
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


@dataclass
class Target:
    """One file a binding selects: what loaded, and how it conforms."""
    path: Path
    errors: list[str] = field(default_factory=list)  # E009 messages; empty when conforming
    data: object = None
    loaded: bool = False
    # E010 findings; None when not assessed (no x-ubiq extension, or not conforming).
    integrity: list[Finding] | None = None
    graph_data: dict | None = None  # Effective graph, including source-derived edges.


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
                    target.graph_data, target.integrity = assess_model(
                        target.data, binding.extension, cfg.root, glossary)
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
