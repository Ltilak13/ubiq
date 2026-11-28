"""Inspect the checked Python symbol registry without importing project code."""
from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from importlib.util import resolve_name
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from . import xref
from .check import Diagnostic
from .config import Config
from .globs import Glob, GlobError, first_match
from .records import FRONTMATTER_RE
from .schemas import load_data


@dataclass(frozen=True)
class Symbol:
    id: str
    module: Path
    name: str
    feature: str
    scenarios: tuple[str, ...]
    record: Path
    line: int


@dataclass(frozen=True)
class SymbolRegistry:
    records: tuple[Symbol, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class _Parameter:
    name: str
    kind: str
    default: str | None
    annotation: str | None

    @property
    def required(self) -> bool:
        return self.default is None and self.kind not in ("var-positional", "var-keyword")


@dataclass(frozen=True)
class _Definition:
    line: int
    parameters: tuple[_Parameter, ...] = ()
    result: str | None = None
    required: bool = True


_Function = ast.FunctionDef | ast.AsyncFunctionDef
_SCOPES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
           ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _name(path: Path, root: Path) -> str:
    parts = path.relative_to(root).with_suffix("").parts
    if len(parts) > 1 and parts[0] == "src":
        parts = parts[1:]
    if len(parts) > 1 and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _text(node: ast.expr | None) -> str | None:
    return ast.unparse(node) if node is not None else None


def _parameter(arg: ast.arg, kind: str, default: ast.expr | None = None) -> _Parameter:
    return _Parameter(arg.arg, kind, _text(default), _text(arg.annotation))


def _parameters(args: ast.arguments, *, receiver: bool) -> tuple[_Parameter, ...]:
    positional = [*args.posonlyargs, *args.args]
    defaults = [None] * (len(positional) - len(args.defaults)) + args.defaults
    formed = [_parameter(arg, "positional-only" if i < len(args.posonlyargs)
                         else "positional-or-keyword", default)
              for i, (arg, default) in enumerate(zip(positional, defaults))]
    if receiver:
        formed = formed[1:]
    if args.vararg is not None:
        formed.append(_parameter(args.vararg, "var-positional"))
    formed.extend(_parameter(arg, "keyword-only", default)
                  for arg, default in zip(args.kwonlyargs, args.kw_defaults))
    if args.kwarg is not None:
        formed.append(_parameter(args.kwarg, "var-keyword"))
    return tuple(formed)


def _called(node: ast.expr, name: str) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    return isinstance(target, ast.Name) and target.id == name or (
        isinstance(target, ast.Attribute) and target.attr == name)


def _option(node: ast.expr | None, name: str) -> object:
    if isinstance(node, ast.Call):
        for keyword in node.keywords:
            if keyword.arg == name and isinstance(keyword.value, ast.Constant):
                return keyword.value.value
    return None


def _constructor(cls: ast.ClassDef, methods: dict[str, _Function]) -> tuple[_Parameter, ...]:
    if initializer := methods.get("__init__"):
        return _parameters(initializer.args, receiver=True)
    decorator = next((d for d in cls.decorator_list if _called(d, "dataclass")), None)
    if decorator is None or _option(decorator, "init") is False:
        return ()
    parameters: list[_Parameter] = []
    for node in cls.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        annotation = node.annotation.value if isinstance(node.annotation, ast.Subscript) else node.annotation
        if _called(annotation, "ClassVar"):
            continue
        keyword_only = _option(decorator, "kw_only") is True
        default = node.value
        if isinstance(default, ast.Call) and _called(default, "field"):
            if _option(default, "init") is False:
                continue
            explicit = _option(default, "kw_only")
            if explicit is not None:
                keyword_only = explicit is True
            default = next((kw.value for kw in default.keywords
                            if kw.arg in ("default", "default_factory")), None)
        kind = "keyword-only" if keyword_only else "positional-or-keyword"
        parameters.append(_Parameter(node.target.id, kind, _text(default), _text(node.annotation)))
    return tuple(sorted(parameters, key=lambda parameter: parameter.kind == "keyword-only"))


def _definitions(tree: ast.Module) -> dict[str, _Definition]:
    definitions: dict[str, _Definition] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            definitions[node.name] = _Definition(node.lineno, _parameters(node.args, receiver=False),
                                                 _text(node.returns), not node.name.startswith("_"))
        elif isinstance(node, ast.ClassDef):
            methods = {item.name: item for item in node.body
                       if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))}
            public = not node.name.startswith("_")
            definitions[node.name] = _Definition(node.lineno, _constructor(node, methods), required=public)
            for name, method in methods.items():
                receiver = not any(_called(d, "staticmethod") for d in method.decorator_list)
                definitions[f"{node.name}.{name}"] = _Definition(
                    method.lineno, _parameters(method.args, receiver=receiver), _text(method.returns),
                    public and not name.startswith("_"))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    annotation = _text(node.annotation) if isinstance(node, ast.AnnAssign) else None
                    definitions[target.id] = _Definition(node.lineno, result=annotation, required=False)
    return definitions


def _display(path: Path, root: Path, line: int = 0) -> str:
    relative = path.relative_to(root).as_posix()
    return f"{relative}:{line}" if line else relative


def _signature_diff(definition: _Definition, params: Any, result: Any) -> list[str]:
    if not isinstance(params, dict) or params.get("type") != "object":
        return ["params must be an object schema"]
    properties = params.get("properties")
    if not isinstance(properties, dict):
        return ["params must declare properties"]
    expected = [parameter.name for parameter in definition.parameters]
    if list(properties) != expected:
        return [f"parameters are {expected!r} in Python and {list(properties)!r} in the contract"]
    required = {parameter.name for parameter in definition.parameters if parameter.required}
    if set(params.get("required", [])) != required:
        return [f"required parameters must be {sorted(required)!r}"]
    differences = []
    for parameter in definition.parameters:
        contract = properties[parameter.name]
        if not isinstance(contract, dict):
            differences.append(f"{parameter.name} must have a parameter schema")
            continue
        for key, actual in (("kind", parameter.kind), ("default", parameter.default),
                            ("type", parameter.annotation)):
            declared = contract.get(f"x-python-{key}")
            if actual != declared:
                differences.append(f"{parameter.name} {key} is {actual!r} in Python and {declared!r} in the contract")
    declared_result = result.get("x-python-type") if isinstance(result, dict) else None
    if definition.result != declared_result:
        differences.append(f"result type is {definition.result!r} in Python and {declared_result!r} in the contract")
    return differences


def _record(root: Path, path: Path, module: str, name: str, spec: Any, line: int,
            definition: _Definition, diagnostics: list[Diagnostic]) -> Symbol | None:
    expected_id = f"symbol:{module}.{name}"
    source = _display(path, root, definition.line)
    sidecar = path.with_suffix(".md")
    if not isinstance(spec, dict):
        return None  # E009 from the schema binding
    if spec.get("id") != expected_id:
        diagnostics.append(Diagnostic("E010", f"Symbol {name} must use ID {expected_id}", sidecar, line))
        return None
    for key in ("params", "result", "errors"):
        contract = spec.get(key)
        if not isinstance(contract, (dict, bool)):
            diagnostics.append(Diagnostic("E009", f"{expected_id} {key}: expected a JSON Schema", sidecar, line))
            return None
        try:
            Draft202012Validator.check_schema(contract)
        except SchemaError as exc:
            diagnostics.append(Diagnostic("E009", f"{expected_id} {key}: {exc.message}", sidecar, line))
            return None
    differences = _signature_diff(definition, spec["params"], spec["result"])
    if differences:
        contract = _display(sidecar, root, line)
        diagnostics.append(Diagnostic("E010", f"{source} differs from {contract}: " + "; ".join(differences),
                                      path, definition.line))
        return None
    feature, scenarios = spec.get("feature"), spec.get("scenarios")
    if not isinstance(feature, str) or not isinstance(scenarios, list) or not all(
        isinstance(scenario, str) for scenario in scenarios
    ):
        return None  # E009 from the schema binding
    return Symbol(expected_id, path, name, feature, tuple(scenarios), sidecar, line)


def _read_module(cfg: Config, path: Path, tree: ast.Module, diagnostics: list[Diagnostic]
                 ) -> tuple[set[str], list[Symbol]]:
    sidecar = path.with_suffix(".md")
    definitions = _definitions(tree)
    try:
        if not sidecar.resolve().is_relative_to(cfg.root):
            raise ValueError("symbol sidecar resolves outside the repository")
        symbols = load_data(sidecar, frontmatter=True)["symbols"]
        if not isinstance(symbols, dict):
            raise TypeError("symbols must be a mapping")
        match = FRONTMATTER_RE.match(sidecar.read_text(encoding="utf-8"))
        frontmatter = match.group(1) if match else ""
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError, RecursionError) as exc:
        diagnostics.append(Diagnostic("E009", f"Cannot read symbol records for {_display(path, cfg.root)}: {exc}",
                                      sidecar))
        return set(), []
    for name, definition in definitions.items():
        if definition.required and name not in symbols:
            diagnostics.append(Diagnostic("E010", f"Public symbol {name} has no record in "
                                          f"{_display(sidecar, cfg.root)}", path, definition.line))
    records: list[Symbol] = []
    for name, spec in sorted(symbols.items()):
        line = xref.line_of(frontmatter, ("symbols", name))
        if name not in definitions:
            diagnostics.append(Diagnostic("E010", f"Symbol record {name} has no definition in "
                                          f"{_display(path, cfg.root)}", sidecar, line))
            continue
        if record := _record(cfg.root, path, _name(path, cfg.root), name, spec, line,
                             definitions[name], diagnostics):
            records.append(record)
    return set(symbols) & definitions.keys(), records


def _absolute_from(node: ast.ImportFrom, own: str, pkg: bool) -> str:
    if not node.level:
        return node.module or ""
    parent = own if pkg else own.rpartition(".")[0]
    try:
        return resolve_name("." * node.level + (node.module or ""), parent)
    except ImportError:
        return ""


def _access(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and (base := _access(node.value)):
        return f"{base}.{node.attr}"
    return ""


def _scope_nodes(scope: ast.AST) -> Iterator[ast.AST]:
    for node in ast.iter_child_nodes(scope):
        yield node
        if not isinstance(node, _SCOPES):
            yield from _scope_nodes(node)


def _uses(path: Path, own: str, scope: ast.AST, names: dict[str, set[str]],
          inherited: dict[str, str] | None = None) -> Iterator[tuple[str, str, int]]:
    nodes = list(_scope_nodes(scope))
    aliases = dict(inherited or {})
    rebound = set()
    for node in nodes:
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            rebound.add(node.id)
        elif isinstance(node, ast.arg):
            rebound.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            rebound.add(node.name)
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name in names and item.name != own:
                    aliases[item.asname or item.name] = item.name
                elif item.asname:
                    rebound.add(item.asname)
        if isinstance(node, ast.ImportFrom):
            target = _absolute_from(node, own, path.name == "__init__.py")
            for item in node.names:
                full = f"{target}.{item.name}" if target else item.name
                if full in names and full != own:
                    aliases[item.asname or item.name] = full
                else:
                    rebound.add(item.asname or item.name)
                    if target in names and target != own:
                        yield target, item.name, node.lineno
    aliases = {alias: target for alias, target in aliases.items() if alias.split(".", 1)[0] not in rebound}
    for node in nodes:
        if isinstance(node, ast.Attribute):
            if module := aliases.get(_access(node.value)):
                yield module, node.attr, node.lineno
        elif isinstance(node, _SCOPES):
            yield from _uses(path, own, node, names, aliases)


def _walk(cfg: Config, globs: tuple[Glob, ...], diagnostics: list[Diagnostic]) -> list[Path]:
    paths: set[Path] = set()
    for pattern in globs:
        try:
            paths.update(path for path in pattern.walk(cfg.ignore)
                         if first_match(cfg.ignore, path) is None and path.resolve().is_relative_to(cfg.root))
        except GlobError as exc:
            diagnostics.append(Diagnostic("E010", f"Cannot scan symbol coverage: {exc}", cfg.root / "ubiq.yaml"))
    return sorted(paths)


def _check_orphan_records(cfg: Config, diagnostics: list[Diagnostic]) -> None:
    patterns = tuple(Glob.parse(pattern.pattern[:-3] + ".md", cfg.root)
                     for pattern in cfg.symbol_coverage if pattern.pattern.endswith(".py"))
    for sidecar in _walk(cfg, patterns, diagnostics):
        source = sidecar.with_suffix(".py")
        if source.is_file():
            continue
        try:
            data = load_data(sidecar, frontmatter=True)
        except (OSError, ValueError, TypeError, yaml.YAMLError, RecursionError):
            continue  # only a recognizable symbol sidecar is in scope here
        if "symbols" in data:
            diagnostics.append(Diagnostic("E010", f"Symbol sidecar has no module at "
                                          f"{_display(source, cfg.root)}", sidecar))


def load_symbols(cfg: Config) -> SymbolRegistry:
    """Return the checked records for covered modules and diagnostics from static inspection."""
    if not cfg.symbol_coverage:
        return SymbolRegistry()
    diagnostics: list[Diagnostic] = []
    records: list[Symbol] = []
    names: dict[str, set[str]] = {}
    trees: dict[Path, ast.Module] = {}
    _check_orphan_records(cfg, diagnostics)
    for path in _walk(cfg, (Glob.parse("**/*.py", cfg.root),), diagnostics):
        covered = first_match(cfg.symbol_coverage, path) is not None
        try:
            tree = ast.parse(path.read_bytes(), filename=str(path))
        except (OSError, SyntaxError, ValueError) as exc:
            if covered:
                line = exc.lineno or 0 if isinstance(exc, SyntaxError) else 0
                diagnostics.append(Diagnostic("E010", f"Cannot inspect Python symbols: {exc}", path, line))
            continue
        trees[path] = tree
        if covered:
            name = _name(path, cfg.root)
            if name in names:
                diagnostics.append(Diagnostic("E010", f"Multiple covered modules use the name {name}", path))
                continue
            names[name], found = _read_module(cfg, path, tree, diagnostics)
            records.extend(found)

    for path, tree in trees.items():
        own = _name(path, cfg.root)
        for target, name, line in sorted(set(_uses(path, own, tree, names)), key=lambda item: (item[2], item)):
            if name not in names[target]:
                diagnostics.append(Diagnostic("E010", f"Unregistered symbol {target}.{name} used from {own}",
                                              path, line))
    return SymbolRegistry(tuple(sorted(records, key=lambda record: record.id)), tuple(diagnostics))
