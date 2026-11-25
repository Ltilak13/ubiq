"""Read-only validation of explicitly identified dependency checkouts."""

from collections.abc import Sequence
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

from .config import Config, Dependency, InvalidConfig, load_config
from .review import Baseline, BaselineError, _git, checkout


def _input_paths(paths: set[Path]) -> set[Path]:
    """Retain each input, its target, and every symlink needed to reach it."""
    pending = list(paths)
    visited: set[Path] = set()
    inputs: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        try:
            target = path.resolve(strict=True)  # Detect cycles on every supported Python version.
        except FileNotFoundError:
            target = path.resolve()  # Deleted inputs must still participate in dirty checks.
        inputs.update((path, target))
        for component in reversed((path, *path.parents)):
            if component.is_symlink():
                inputs.add(component.parent.resolve() / component.name)
                pending.append(component.parent / component.readlink() / path.relative_to(component))
                break
    return inputs


def validate_checkout(dependency: Dependency, cfg: Config,
                      inputs: Sequence[Path] = ()) -> None:
    if dependency.revision is None:
        return
    root = dependency.path.resolve()
    try:
        actual = dependency.revision if dependency.snapshot else _git(root, "rev-parse", "HEAD").strip()
        if actual != dependency.revision:
            raise InvalidConfig(f"dependency {dependency.name!r} at {root}: revision mismatch; "
                                f"expected {dependency.revision}, found {actual}")
        changed = [] if dependency.snapshot else (
            _git(root, "diff", "--no-renames", "--relative", "--name-only", "-z", "HEAD", "--").split("\0")
            + _git(root, "ls-files", "--others", "-z").split("\0"))
        patterns = (*cfg.docs, *cfg.historical, *cfg.overlays, *cfg.edges.install,
                    *(rule.glob for rule in cfg.glossary),
                    *(pattern for spec in cfg.schemas for pattern in spec.files))
        # Retain lexical names so retargeted schema/catalog symlinks remain dirty inputs.
        explicit = {root / "ubiq.yaml", *inputs, *(s.file for s in cfg.catalogs),
                    *(root / s.schema.split("#", 1)[0] for s in cfg.schemas)}
        explicit.update(path for pattern in patterns for path in pattern.walk(cfg.ignore))
        explicit = _input_paths(explicit)
        outside = [str(path) for path in explicit
                   if not path.is_relative_to(root) or not path.resolve().is_relative_to(root)]
        if outside:
            raise InvalidConfig(f"dependency {dependency.name!r}: pinned inputs leave checkout: "
                                + ", ".join(sorted(outside)))
        dirty = sorted({name for name in changed if name and (
            root / name in explicit or any(g.matches(root / name) for g in patterns))})
        if dirty:
            raise InvalidConfig(f"dependency {dependency.name!r} at {root}: pinned inputs are dirty: "
                                + ", ".join(dirty))
    except (BaselineError, OSError, RuntimeError) as exc:
        raise InvalidConfig(f"dependency {dependency.name!r} at {root}: cannot verify revision ({exc})") from exc


class Snapshots:
    """Keep exact, locally available dependency revisions alive for one review."""

    def __init__(self, stack: ExitStack):
        self.stack = stack
        self.configs: dict[Path, Config] = {}
        self.roots: dict[tuple[Path, str], Path] = {}
        self.originals: dict[Path, Path] = {}
        self.unread: list[tuple[Path, str]] = []

    def prepare(self, cfg: Config, original: Path) -> Config:
        if cfg.root in self.configs:
            return self.configs[cfg.root]
        self.configs[cfg.root] = cfg
        declarations = []
        for dep in cfg.edges.external:
            real = ((original / dep.path.relative_to(cfg.root))
                    if dep.path.is_relative_to(cfg.root) else dep.path)
            if dep.name is None:
                declarations.append(replace(dep, path=real))
                continue
            real = real.resolve()
            if dep.revision is None:
                self.unread.append((real, f"dependency {dep.name!r} has no historical revision pin"))
                continue
            try:
                key = (real, dep.revision)
                if key not in self.roots:
                    top = Path(_git(real, "rev-parse", "--show-toplevel").strip()).resolve()
                    commit = _git(real, "rev-parse", "--verify", f"{dep.revision}^{{commit}}").strip()
                    prefix = real.relative_to(top).as_posix()
                    snapshot = self.stack.enter_context(checkout(Baseline(
                        dep.revision, commit, top, "" if prefix == "." else prefix)))
                    self.roots[key] = snapshot
                    self.originals[snapshot] = real
                    self.prepare(load_config(snapshot), real)
                declarations.append(replace(dep, path=self.roots[key], snapshot=True))
            except (BaselineError, InvalidConfig, OSError, ValueError) as exc:
                self.unread.append((real, f"dependency {dep.name!r} revision {dep.revision} unavailable: {exc}"))
        prepared = replace(cfg, edges=replace(cfg.edges, external=tuple(declarations)))
        self.configs[cfg.root] = prepared
        return prepared
