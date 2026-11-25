"""Change review: compare a git baseline with the working tree.

The baseline is the committed tree at `git merge-base <rev> HEAD`. The head is
the working tree, including untracked files. See "Change review" in docs/spec.md.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from .graph import DEPENDS, Edge
from .records import Term


class BaselineError(RuntimeError):
    """The baseline cannot be built: no git work tree, an unknown rev, or bad config."""


@dataclass(frozen=True)
class ChangedFile:
    status: str  # added, modified, deleted, renamed
    file: str  # root-relative, head path
    source: str | None = None  # root-relative baseline path of a rename

    def as_json(self) -> dict:
        out = {"status": self.status, "file": self.file}
        return {**out, "from": self.source} if self.source else out


@dataclass
class Side:
    """One built side of a review: records, edges, and what could not be read."""
    name: str  # "head" or "baseline"
    root: Path
    terms: dict[str, Term]  # qualified name -> record (this repository only)
    owner: Callable[[Path], Term | None]
    edges: list[Edge]
    invalid: dict[str, str]  # root-relative file -> E005 reason
    unread: list[tuple[Path, str]] = field(default_factory=list)

    def rel(self, path: Path) -> str:
        p = path if path.is_absolute() else self.root / path
        p = p.resolve()
        return str(p.relative_to(self.root)) if p.is_relative_to(self.root) else str(p)


def _git(cwd: Path, *args: str, env: dict | None = None, data: bool = False):
    proc = subprocess.run(["git", *args], check=False, cwd=cwd, capture_output=True, env=env)
    if proc.returncode:
        message = proc.stderr.decode(errors="replace").strip().splitlines()
        raise BaselineError(message[-1] if message else f"git {args[0]} failed")
    return proc.stdout if data else proc.stdout.decode()


@dataclass(frozen=True)
class Baseline:
    rev: str
    commit: str
    toplevel: Path
    prefix: str  # root relative to the repository top level, "" at the top

    def as_json(self) -> dict:
        return {"rev": self.rev, "commit": self.commit}


def resolve_baseline(root: Path, rev: str) -> Baseline:
    try:
        top = Path(_git(root, "rev-parse", "--show-toplevel").strip()).resolve()
    except (BaselineError, OSError) as exc:
        raise BaselineError(f"{root} is not inside a git work tree ({exc})") from exc
    try:
        if rev.startswith("-"):  # never let a rev read as an option
            raise BaselineError(rev)
        commit = _git(root, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}").strip()
    except BaselineError:
        raise BaselineError(f"'{rev}' names no commit") from None
    commit = _git(root, "merge-base", commit, "HEAD").strip()
    try:
        prefix = root.resolve().relative_to(top).as_posix()
    except ValueError:
        raise BaselineError(f"{root} is not inside git work tree {top}") from None
    return Baseline(rev, commit, top, "" if prefix == "." else prefix)


@contextmanager
def checkout(baseline: Baseline) -> Iterator[Path]:
    """The baseline tree in a temporary directory; yields the root inside it."""
    tmp = Path(tempfile.mkdtemp(prefix="ubiq-baseline-"))
    try:
        # A throwaway index and checkout-index write the tree the way a checkout
        # would: smudge and eol filters apply, export attributes do not.
        tree = tmp / "tree"
        env = {**os.environ, "GIT_INDEX_FILE": str(tmp / "index")}
        _git(baseline.toplevel, "read-tree", baseline.commit, env=env)
        _git(baseline.toplevel, "checkout-index", "--all", "--force",
             f"--prefix={tree}/", env=env)
        _retarget_outside_links(tree, baseline.toplevel)
        root = tree / baseline.prefix if baseline.prefix else tree
        root.mkdir(parents=True, exist_ok=True)
        yield root.resolve()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _retarget_outside_links(tree: Path, toplevel: Path) -> None:
    """Point committed relative symlinks that leave the repository at the place
    they reach from the real checkout. Links inside the repository keep reading
    the baseline tree; paths outside it are read in their current state."""
    for dirpath, dirnames, filenames in os.walk(tree):
        for name in [*dirnames, *filenames]:
            link = Path(dirpath) / name
            if not link.is_symlink() or os.path.isabs(target := os.readlink(link)):
                continue
            real = Path(os.path.normpath(toplevel / link.parent.relative_to(tree) / target))
            if not real.is_relative_to(toplevel):
                link.unlink()
                link.symlink_to(real)


_STATUS = {"A": "added", "C": "added", "M": "modified", "T": "modified",
           "D": "deleted", "R": "renamed"}


def changed_files(baseline: Baseline) -> list[ChangedFile]:
    """Name-status from the baseline to the working tree, untracked files included.

    A throwaway index stages the working tree so unstaged moves pair as renames;
    the real index is never written.
    """
    top = baseline.toplevel
    index = Path(_git(top, "rev-parse", "--git-path", "index").strip())
    index = index if index.is_absolute() else top / index
    with tempfile.TemporaryDirectory(prefix="ubiq-index-") as tmp:
        scratch = Path(tmp) / "index"
        if index.is_file():
            shutil.copyfile(index, scratch)
        env = {**os.environ, "GIT_INDEX_FILE": str(scratch)}
        _git(top, "add", "-A", "--", ".", env=env)
        out = _git(top, "diff", "--cached", "-M", "--name-status", "-z",
                   "--no-ext-diff", baseline.commit, env=env)
    fields = out.split("\0")
    prefix = f"{baseline.prefix}/" if baseline.prefix else ""

    def local(path: str) -> str | None:
        return path[len(prefix):] if path.startswith(prefix) else None

    found: list[ChangedFile] = []
    i = 0
    while i < len(fields) and fields[i]:
        code = fields[i][0]
        if code in "RC":
            old, new = local(fields[i + 1]), local(fields[i + 2])
            i += 3
            if new is None and old is not None:
                found.append(ChangedFile("deleted", old))
            elif new is not None and code == "R" and old is not None:
                found.append(ChangedFile("renamed", new, old))
            elif new is not None:  # a copy, or a move in from outside the root
                found.append(ChangedFile("added", new))
            continue
        path = local(fields[i + 1])
        i += 2
        if path is not None:
            found.append(ChangedFile(_STATUS.get(code, "modified"), path))
    return sorted(found, key=lambda c: c.file)


@dataclass
class Change:
    record: str
    change: str  # added, deleted, edited, renamed, unknown
    files: list[str]
    source: str | None = None  # baseline qualified name of a rename

    def starts(self, side: str) -> str | None:
        """The name to walk callers from in that side's graph, if any."""
        if side == "head":
            return None if self.change == "deleted" else self.record
        if self.change == "renamed":
            return self.source
        return self.record if self.change in ("deleted", "unknown") else None

    def as_json(self) -> dict:
        out: dict = {"record": self.record, "change": self.change}
        if self.source:
            out["from"] = self.source
        return {**out, "files": self.files}


def classify(files: list[ChangedFile], base: Side, head: Side) -> list[Change]:
    """Changed records, by the changed files each side's records own."""
    head_defines = {head.rel(t.file): q for q, t in head.terms.items()}
    base_defines = {base.rel(t.file): q for q, t in base.terms.items()}
    renamed_to = {c.source: c.file for c in files if c.source}

    owned: dict[str, set[str]] = {}
    unknown: dict[str, set[str]] = {}
    for c in files:
        old = c.source or c.file
        # A record file that one side cannot parse: what that side defines is unknown.
        hidden = ((c.file in head.invalid and base_defines.get(old))
                  or (old in base.invalid and head_defines.get(c.file)))
        if hidden:
            unknown.setdefault(hidden, set()).add(c.file)
            continue
        for side, path, skip in ((head, c.file, "deleted"), (base, old, "added")):
            owner = side.owner(side.root / path) if c.status != skip else None
            if owner is not None and owner.repository is None:
                owned.setdefault(owner.qualified, set()).add(c.file)

    changes: dict[str, Change] = {q: Change(q, "unknown", sorted(f))
                                  for q, f in unknown.items()}
    for q in sorted(owned.keys() - changes.keys()):
        files_ = sorted(owned[q])
        if q in head.terms and q in base.terms:
            changes[q] = Change(q, "edited", files_)
        elif q in head.terms:
            changes[q] = Change(q, "added", files_)
        else:
            changes[q] = Change(q, "deleted", files_)

    # A deleted record whose file (or that file's rename) defines an added record
    # is one rename.
    for q, ch in list(changes.items()):
        if ch.change != "deleted":
            continue
        old_file = base.rel(base.terms[q].file)
        added = changes.get(head_defines.get(renamed_to.get(old_file, old_file), ""))
        if added is not None and added.change == "added":
            del changes[q]
            added.change, added.source = "renamed", q
            added.files = sorted(set(added.files) | set(ch.files))
    return sorted(changes.values(), key=lambda c: c.record)


def edge_json(e: Edge, side: Side) -> dict:
    return {"kind": e.kind, "source": e.source.qualified, "target": e.target.qualified,
            "file": side.rel(e.file), "line": e.line, "side": side.name}


def affected(changes: list[Change], base: Side, head: Side,
             depth: int | None) -> list[dict]:
    """Records that depend on a changed record, each with its shortest path.

    Breadth-first over incoming invoke and include edges, from every changed
    record at once. Head callers reach added, edited, and renamed records;
    baseline callers reach deleted records and the old names of renamed ones.
    On equal length, the head path wins.
    """
    changed = {c.record for c in changes} | {c.source for c in changes if c.source}
    paths: dict[str, list[tuple[Edge, Side]]] = {}
    for side in (head, base):
        starts = {q for c in changes if (q := c.starts(side.name))}
        incoming: dict[str, list[Edge]] = {}
        for e in side.edges:
            if e.kind in DEPENDS and e.source.repository is None:
                incoming.setdefault(e.target.qualified, []).append(e)
        found: dict[str, list[Edge]] = {q: [] for q in starts}
        frontier, level = sorted(starts), 0
        while frontier and (depth is None or level < depth):
            nxt: dict[str, list[Edge]] = {}
            for target in frontier:
                for e in sorted(incoming.get(target, []),
                                key=lambda e: (e.source.qualified, str(e.file), e.line)):
                    src = e.source.qualified
                    if src in found or src in nxt:
                        continue
                    nxt[src] = [e, *found[target]]
            found.update(nxt)
            frontier, level = sorted(nxt), level + 1
        for q, path in found.items():
            if q in changed or not path:
                continue
            if q not in paths or len(path) < len(paths[q]):
                paths[q] = [(e, side) for e in path]
    return [{"record": q, "via": [edge_json(e, s) for e, s in paths[q]]}
            for q in sorted(paths)]


def incomplete(*sides: Side) -> list[dict]:
    """Missing dependency data on either side: unreadable repositories and E005 files."""
    out = [{"side": s.name, "file": str(repo.resolve()), "reason": reason}
           for s in sides for repo, reason in s.unread]
    out += [{"side": s.name, "file": f, "reason": r}
            for s in sides for f, r in sorted(s.invalid.items())]
    return sorted(out, key=lambda i: (i["side"] != "baseline", i["file"]))
