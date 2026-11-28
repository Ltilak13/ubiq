"""The `x-ubiq-ref` schema annotation: a relationship declared once, in the schema.

A property annotated `{"x-ubiq-ref": {"ns": "feature", "edge": "requires"}}` holds a
record name (or a list of them) that must resolve to a record in `ns` (E006). The
resolved link is a composition edge named `edge`, so `ubiq graph --kind requires`
selects it. `acyclic` and `single` are parsed and kept for the checks that enforce
them (cycles, one parent); nothing here enforces them yet.

This module reads schemas and walks instance data. It does not touch the glossary.
"""
from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

KEY = "x-ubiq-ref"
FIELDS = ("ns", "edge", "acyclic", "single", "within")
EDGE_RE = re.compile(r"[a-z][a-z0-9_]*(?:-[a-z0-9_]+)*")
# Edge kinds that ubiq derives itself; an annotation cannot reuse their names.
RESERVED = ("invoke", "include", "route", "reference")

# One step from a schema position to a value: an object key, any key that matches
# a `patternProperties` pattern, or each item of an array.
Step = tuple[str, str]  # ("key" | "pattern" | "items", name or pattern)


@dataclass(frozen=True)
class XRef:
    ns: str
    edge: str
    acyclic: bool = False
    single: bool = False
    within: str = ""  # a top-level mapping in the same file whose keys are the valid values


@dataclass(frozen=True)
class Annotation:
    steps: tuple[Step, ...]  # where the annotated property sits in the instance
    ref: XRef


def parse(value: Any) -> XRef:
    """Read one annotation, or raise ValueError (TypeError for a wrong type) naming what is wrong."""
    if not isinstance(value, dict):
        raise TypeError(f"{KEY}: expected an object with ns and edge")
    unknown = sorted(set(value) - set(FIELDS))
    if unknown:
        raise ValueError(f"{KEY}: unknown field {', '.join(unknown)}; expected {', '.join(FIELDS)}")
    for name in ("ns", "edge"):
        if not isinstance(value.get(name), str) or not value[name].strip():
            raise ValueError(f"{KEY}.{name}: expected a non-empty string")
    if not EDGE_RE.fullmatch(value["edge"]):
        raise ValueError(f"{KEY}.edge: {value['edge']!r} must be lowercase words joined by - or _")
    if value["edge"] in RESERVED:
        raise ValueError(f"{KEY}.edge: {value['edge']!r} is a built-in edge kind")
    for name in ("acyclic", "single"):
        if not isinstance(value.get(name, False), bool):
            raise TypeError(f"{KEY}.{name}: expected true or false")
    within = value.get("within", "")
    if not isinstance(within, str) or (within and not within.strip()):
        raise TypeError(f"{KEY}.within: expected the name of a top-level property")
    return XRef(value["ns"].strip(), value["edge"], value.get("acyclic", False),
                value.get("single", False), within.strip())


def pointer(root: Any, ref: str) -> Any:
    node = root
    for part in ref[1:].split("/")[1:] if ref != "#" else []:
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def collect(schema: Any, root: Any = None) -> list[Annotation]:
    """Every `x-ubiq-ref` in `schema`, with the instance path it applies to.

    Follows same-document `$ref`s and the applicators that add properties at the
    same position (`allOf`, `anyOf`, `oneOf`, `if`, `then`, `else`). `root` is the
    document that `$ref`s point into (default: `schema`).
    """
    found: dict[tuple[tuple[Step, ...], XRef], Annotation] = {}
    document = schema if root is None else root

    def walk(node: Any, steps: tuple[Step, ...], active: frozenset[str]) -> None:
        if not isinstance(node, dict):
            return
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#") and ref not in active:
            try:
                target = pointer(document, ref)
            except (KeyError, IndexError, TypeError):
                target = None  # an unresolvable $ref is E008 from the validator
            walk(target, steps, active | {ref})
        if KEY in node:
            xref = parse(node[KEY])
            found.setdefault((steps, xref), Annotation(steps, xref))
        for keyword in ("allOf", "anyOf", "oneOf"):
            subs = node.get(keyword)
            for sub in subs if isinstance(subs, list) else []:
                walk(sub, steps, active)
        for keyword in ("if", "then", "else"):
            walk(node.get(keyword), steps, active)
        for name, sub in (node.get("properties") or {}).items():
            walk(sub, (*steps, ("key", name)), active)
        for pattern, sub in (node.get("patternProperties") or {}).items():
            walk(sub, (*steps, ("pattern", pattern)), active)
        if isinstance(node.get("items"), dict):
            walk(node["items"], (*steps, ("items", "")), active)

    walk(schema, (), frozenset())
    return list(found.values())


def values(data: Any, steps: tuple[Step, ...], keys: tuple[str, ...] = ()
           ) -> Iterator[tuple[tuple[str, ...], str]]:
    """Each string at `steps` in `data` with the object keys on the way (for its line).

    A string, or a list of strings, is a value. Anything else is not: the schema
    reports a wrong type (E009), so it makes no reference here.
    """
    if not steps:
        if isinstance(data, str):
            yield keys, data
        elif isinstance(data, list):
            yield from ((keys, item) for item in data if isinstance(item, str))
        return
    (kind, name), rest = steps[0], steps[1:]
    if kind == "items":
        for item in data if isinstance(data, list) else []:
            yield from values(item, rest, keys)
    elif isinstance(data, Mapping):
        for key, item in data.items():
            if (kind == "key" and key == name) or (kind == "pattern" and re.search(name, key)):
                yield from values(item, rest, (*keys, key))


def line_of(frontmatter: str, keys: tuple[str, ...]) -> int:
    """The file line of the last key in `keys`, searching each key after the one before.

    Frontmatter starts on line 2. A key that cannot be found keeps the line of the
    one before it, so a diagnostic still lands in the record.
    """
    lines = frontmatter.splitlines()
    at = 0
    for key in keys:
        pattern = re.compile(rf"^\s*[\"']?{re.escape(key)}[\"']?\s*:")
        found = next((i for i in range(at, len(lines)) if pattern.match(lines[i])), None)
        if found is not None:
            at = found
    return at + 2
