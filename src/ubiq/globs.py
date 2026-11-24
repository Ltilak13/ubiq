"""One pattern language for every path setting.

A pattern is relative to the repository root unless it is absolute. `*`, `?`,
and `[...]` match within one path segment, dotfiles included. `**` matches zero
or more directories. Ignore rules use the same language: `**/node_modules/**`
ignores every copy, and `node_modules/**` only the one at the root.
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePath

_MAGIC = frozenset("*?[")


def _match(parts: tuple[str, ...], pattern: tuple[str, ...]) -> bool:
    """Match path segments. `**` consumes zero or more directories."""
    if not pattern:
        return not parts
    if pattern[0] == "**":
        return _match(parts, pattern[1:]) or bool(parts) and _match(parts[1:], pattern)
    return (bool(parts) and fnmatch.fnmatchcase(parts[0], pattern[0])
            and _match(parts[1:], pattern[1:]))


@dataclass(frozen=True)
class Glob:
    """A compiled pattern: a literal base directory plus the segments after it.

    Splitting at the first wildcard keeps the root literal, so a root path that
    contains `[` or `*` never acts as a pattern, and walks start at the base.
    """
    pattern: str  # as written in the configuration
    base: Path
    tail: tuple[str, ...]

    @classmethod
    def parse(cls, pattern: str, root: Path) -> Glob:
        parts = PurePath(os.path.normpath(pattern)).parts
        cut = next((i for i, part in enumerate(parts) if _MAGIC & set(part)), len(parts))
        base = Path(os.path.normpath(os.path.join(root, *parts[:cut])))
        return cls(pattern, base, parts[cut:])

    def matches(self, path: Path) -> bool:
        try:
            parts = Path(os.path.abspath(path)).relative_to(self.base).parts
        except ValueError:
            return False
        return _match(parts, self.tail)

    def covers_dir(self, path: Path) -> bool:
        """Whether every path under the directory `path` matches (`dir/**`)."""
        if not self.tail or self.tail[-1] != "**":
            return False
        try:
            parts = Path(os.path.abspath(path)).relative_to(self.base).parts
        except ValueError:
            return False
        # `node_modules/x` is covered because its ancestor `node_modules` is.
        return any(_match(parts[:k], self.tail[:-1]) for k in range(len(parts) + 1))

    def walk(self, ignore: Iterable[Glob] = (), prune: bool = True) -> Iterator[Path]:
        """Matching paths under the base. With `prune`, ignored directories are
        not entered; `explain` turns it off to report every ignored candidate."""
        if not self.tail:
            if self.base.is_file():
                yield self.base
            return
        ignore = tuple(ignore)
        # Without `**`, a match is exactly len(tail) segments deep.
        max_depth = None if "**" in self.tail else len(self.tail) - 1
        ancestors: list[str] = []
        for dirpath, dirnames, filenames in os.walk(self.base, followlinks=True):
            depth = len(Path(dirpath).relative_to(self.base).parts)
            del ancestors[depth:]
            real = os.path.realpath(dirpath)
            if real in ancestors:  # Stop cycles without hiding matching sibling aliases.
                dirnames[:] = []
                continue
            ancestors.append(real)
            if max_depth is not None and depth >= max_depth:
                dirnames[:] = []
            elif prune:
                dirnames[:] = [d for d in dirnames
                               if not any(g.covers_dir(Path(dirpath, d)) for g in ignore)]
            for name in filenames:
                path = Path(dirpath, name)
                if self.matches(path):
                    yield path


def first_match(globs: Iterable[Glob], path: Path) -> Glob | None:
    return next((g for g in globs if g.matches(path)), None)
