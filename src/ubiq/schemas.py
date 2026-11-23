"""Opt-in JSON Schema validation, separate from lexical vocabulary parsing."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from .check import Diagnostic
from .records import FRONTMATTER_RE

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
    validator = Draft202012Validator(schema, registry=Registry())
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


def check_schemas(cfg, glossary):
    """Return E008 schema/config errors and E009 target conformance errors."""
    diagnostics = []
    for spec in cfg.schemas:
        try:
            schema, validator = _validator(cfg.root, spec.schema)
            has_integrity = isinstance(schema, dict) and "x-ubiq" in schema
            integrity = schema.get("x-ubiq") if has_integrity else None
            if has_integrity:
                from .integrity import validate_spec
                validate_spec(integrity)
        except (OSError, UnicodeError, ValueError, TypeError, yaml.YAMLError, SchemaError,
                Unresolvable, RecursionError) as exc:
            diagnostics.append(Diagnostic("E008", f"schema {spec.schema}: {exc}", cfg.root / "ubiq.yaml"))
            continue
        paths = set()
        for pattern in spec.files:
            matches = {p for p in pattern.walk(cfg.ignore)
                       if not any(g.matches(p) for g in cfg.ignore)}
            if not matches:
                diagnostics.append(Diagnostic("E009", f"schema target pattern matched no files: {pattern.pattern}",
                                              cfg.root / "ubiq.yaml"))
            paths.update(matches)
        for path in sorted(paths):
            try:
                value = load_data(path, frontmatter=spec.format == "frontmatter")
                errors = list(validator.iter_errors(value))
                diagnostics.extend(Diagnostic("E009", f"{_pointer(e.absolute_path)}: {e.message}", path)
                                   for e in errors)
                if not errors and integrity is not None:
                    from .integrity import check_integrity
                    diagnostics.extend(check_integrity(value, integrity, cfg.root, glossary, path))
            except (OSError, UnicodeError, ValueError, TypeError, yaml.YAMLError, Unresolvable, RecursionError) as exc:
                diagnostics.append(Diagnostic("E009", f"schema validation failed: {exc}", path))
    return diagnostics
