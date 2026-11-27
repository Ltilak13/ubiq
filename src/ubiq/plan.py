"""The adoption order of ubiq's own features (`ubiq plan`).

Each feature is a record (`src/ubiq/features/*.md`) with `requires` edges to the
features it builds on. The order is a topological sort that takes the
alphabetically first ready feature at each step, so equal features list stably.
`--next` prints only the unused features whose requirements a repository already
meets, detected from its `ubiq.yaml` (each feature's `config` keys) and `--used`.

A feature has a `status`: `shipped` (the default) or `planned`. A planned feature
is work in flight, so it is not in the adoption order and `--next` never offers it;
`ubiq plan --json` lists its name under `planned`. A planned feature may require
planned or shipped features, but a shipped feature may not require a planned one.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

from .records import InvalidRecord, parse_frontmatter

BUNDLED = Path(__file__).resolve().parent / "features"


STATUSES = ("planned", "shipped")


class PlanError(ValueError):
    """Feature records that cannot be ordered (missing requirement, cycle, bad record)."""


@dataclass(frozen=True)
class Feature:
    name: str
    summary: str
    requires: tuple[str, ...] = ()
    codes: tuple[str, ...] = ()
    config: tuple[str, ...] = ()
    docs: str = ""
    status: str = "shipped"
    issue: int | None = None


def _strings(meta: dict, key: str, path: Path) -> tuple[str, ...]:
    value = meta.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise PlanError(f"{path.name}: {key} must be a list of strings")
    return tuple(value)


def load_features(directory: Path = BUNDLED) -> list[Feature]:
    """Read every feature record in `directory`, sorted by name."""
    if not directory.is_dir():
        raise PlanError(f"feature directory does not exist or is not a directory: {directory}")
    features = []
    for path in sorted(directory.glob("*.md")):
        try:
            meta, _ = parse_frontmatter(path)
        except InvalidRecord as exc:
            raise PlanError(f"{path.name}: {exc}") from exc
        name, summary = meta.get("name"), meta.get("summary")
        if not isinstance(name, str) or not isinstance(summary, str):
            raise PlanError(f"{path.name}: name and summary must be strings")
        status = meta.get("status", "shipped")
        if status not in STATUSES:
            raise PlanError(f"{path.name}: status must be one of {', '.join(STATUSES)}")
        issue = meta.get("issue")
        if issue is not None:
            if isinstance(issue, bool) or not str(issue).isdigit() or int(issue) < 1:
                raise PlanError(f"{path.name}: issue must be a positive integer")
            issue = int(issue)
        features.append(Feature(name, summary, _strings(meta, "requires", path),
                                _strings(meta, "codes", path), _strings(meta, "config", path),
                                str(meta.get("docs") or ""), status, issue))
    return sorted(features, key=lambda f: f.name)


def order(features: Iterable[Feature]) -> list[Feature]:
    """Shipped features in dependency order, alphabetical among those ready together.

    Planned features take part in validation and ordering but are left out of the
    result. Raises PlanError for a duplicate name, a requirement that names no
    feature, a shipped feature that requires a planned one, or a cycle (two
    features that require each other, or a longer loop).
    """
    by_name: dict[str, Feature] = {}
    for f in features:
        if f.name in by_name:
            raise PlanError(f"feature {f.name} is defined twice")
        by_name[f.name] = f
    for f in by_name.values():
        for need in f.requires:
            if need not in by_name:
                raise PlanError(f"feature {f.name} requires {need}, which is not a feature")
            if f.status == "shipped" and by_name[need].status == "planned":
                raise PlanError(f"shipped feature {f.name} requires {need}, which is only planned")
    done: list[Feature] = []
    placed: set[str] = set()
    pending = dict(by_name)
    while pending:
        ready = sorted(n for n, f in pending.items() if all(r in placed for r in f.requires))
        if not ready:
            raise PlanError("requires cycle: " + _cycle(pending))
        nxt = ready[0]
        done.append(pending.pop(nxt))
        placed.add(nxt)
    return [f for f in done if f.status == "shipped"]


def _cycle(pending: Mapping[str, Feature]) -> str:
    """One loop among the features that never became ready, as `a -> b -> a`."""
    node = min(pending)
    path: list[str] = []
    while node not in path:
        path.append(node)
        node = min(r for r in pending[node].requires if r in pending)
    return " -> ".join([*path[path.index(node):], node])


def _configured(settings: object, dotted: str) -> bool:
    for part in dotted.split("."):
        if not isinstance(settings, dict) or settings.get(part) in (None, [], {}, ""):
            return False
        settings = settings[part]
    return True


def used_features(features: Sequence[Feature], root: Path,
                  declared: Iterable[str] = ()) -> set[str]:
    """Features a repository uses: those whose `config` keys are set in its
    `ubiq.yaml`, those named in `declared`, the glossary when a glossary exists,
    and everything they require."""
    path = root / "ubiq.yaml"
    try:
        settings = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError, UnicodeError, yaml.YAMLError):
        settings = None
    by_name = {f.name: f for f in features}
    used = {f.name for f in features if any(_configured(settings, key) for key in f.config)}
    used.update(name for name in declared if name in by_name)
    if "glossary" in by_name and any(root.glob("glossary/**/*.md")):
        used.add("glossary")
    pending = list(used)
    while pending:
        for need in by_name[pending.pop()].requires:
            if need not in used:
                used.add(need)
                pending.append(need)
    return used


def next_steps(ordered: Sequence[Feature], used: set[str]) -> list[Feature]:
    """Unused features whose requirements are all used, in adoption order."""
    return [f for f in ordered if f.name not in used and all(r in used for r in f.requires)]


def _line(index: int, f: Feature, digits: int, width: int) -> str:
    return f"{f'{index}.':<{digits + 1}} {f.name:<{width}}  {f.summary}"


def _json(index: int, f: Feature) -> dict:
    return {"position": index, "name": f.name, "summary": f.summary, "requires": list(f.requires),
            "codes": list(f.codes), "docs": f.docs}


def cmd_plan(args) -> int:
    try:
        features = load_features(Path(args.features) if args.features else BUNDLED)
        ordered = order(features)
        planned = sorted(f.name for f in features if f.status == "planned")
        unplanned = sorted(set(args.used or ()) & set(planned))
        if unplanned:
            raise PlanError(f"--used names a planned feature: {', '.join(unplanned)}")
        unknown = sorted(set(args.used or ()) - {f.name for f in ordered})
        if unknown:
            raise PlanError(f"--used names no feature: {', '.join(unknown)}")
    except PlanError as exc:
        print(json.dumps({"error": str(exc)}) if args.json else f"error: {exc}")
        return 1
    used: set[str] | None = None
    shown = ordered
    if args.next:
        used = used_features(ordered, Path(args.root).resolve(), args.used or ())
        shown = next_steps(ordered, used)
    position = {f.name: i for i, f in enumerate(ordered, 1)}
    if args.json:
        out: dict = {"features": [_json(position[f.name], f) for f in shown], "planned": planned}
        if used is not None:
            out["used"] = [f.name for f in ordered if f.name in used]
        print(json.dumps(out, indent=2))
        return 0
    width = max((len(f.name) for f in shown), default=0)
    digits = len(str(len(ordered)))
    for f in shown:
        print(_line(position[f.name], f, digits, width))
    if used is not None and not shown:
        print("every feature is in use")
    return 0
