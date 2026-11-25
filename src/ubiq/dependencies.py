"""Read-only validation of explicitly identified dependency checkouts."""

from collections.abc import Sequence
from pathlib import Path

from .config import Config, Dependency, InvalidConfig
from .review import BaselineError, _git


def validate_checkout(dependency: Dependency, cfg: Config,
                      inputs: Sequence[Path] = ()) -> None:
    if dependency.revision is None:
        return
    root = dependency.path.resolve()
    try:
        actual = _git(root, "rev-parse", "HEAD").strip()
        if actual != dependency.revision:
            raise InvalidConfig(f"dependency {dependency.name!r} at {root}: revision mismatch; "
                                f"expected {dependency.revision}, found {actual}")
        changed = _git(root, "diff", "--relative", "--name-only", "-z", "HEAD", "--").split("\0")
        changed += _git(root, "ls-files", "--others", "-z").split("\0")
        patterns = (*cfg.docs, *cfg.historical, *cfg.overlays, *cfg.edges.install,
                    *(rule.glob for rule in cfg.glossary),
                    *(pattern for spec in cfg.schemas for pattern in spec.files))
        explicit = {root / "ubiq.yaml", *inputs, *(s.file.resolve() for s in cfg.catalogs),
                    *((root / s.schema.split("#", 1)[0]).resolve() for s in cfg.schemas)}
        explicit.update(path for pattern in patterns for path in pattern.walk(cfg.ignore))
        explicit |= {path.resolve() for path in explicit}
        outside = [str(path) for path in explicit if not path.resolve().is_relative_to(root)]
        if outside:
            raise InvalidConfig(f"dependency {dependency.name!r}: pinned inputs leave checkout: "
                                + ", ".join(sorted(outside)))
        dirty = sorted({name for name in changed if name and (
            root / name in explicit or any(g.matches(root / name) for g in patterns))})
        if dirty:
            raise InvalidConfig(f"dependency {dependency.name!r} at {root}: pinned inputs are dirty: "
                                + ", ".join(dirty))
    except (BaselineError, OSError) as exc:
        raise InvalidConfig(f"dependency {dependency.name!r} at {root}: cannot verify revision ({exc})") from exc
