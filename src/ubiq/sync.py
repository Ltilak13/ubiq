"""Mirror records to GitHub issues (`ubiq sync github`).

The sync is a diff. `desired_from_config` reads the records and returns what
GitHub should hold (`Desired`). `plan` compares that with a snapshot of the
repository's issues and returns actions; only `noop` actions mean the mirror is
in sync, and any other action is drift. `plan` is pure. `GitHub` is the thin
adapter: it reads the snapshot and performs actions through an injectable
transport.

Each mirrored fact is one function in `FACTS`: given a desired item and the
issues that track it, return the actions that make GitHub match. A later fact
(priority label, blocked-by link, sub-issue) adds one function there and one
handler in `GitHub.handlers`; the matching, drift, and CLI code do not change.

Current behavior, from the goal-issue script this generalizes: the sync creates
issues and closes issues that a criterion lists in `issues:` or that carry its
marker and were opened by the workflow bot. It never reopens an issue or edits a
title.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Config, load_config
from .schemas import load_data

# A criterion line and its indented continuation lines.
CRITERION_RE = re.compile(r'^\d+\. (AC\d+): .+(?:\n[ \t]+\S.*)*', re.MULTILINE)
# Anyone can write a marker into an issue; only the workflow's own issues count.
BOT = 'github-actions[bot]'
MARKER_RE = re.compile(r'<!-- (ubiq-[a-z]+: [^>]+?) -->')
CLOSED_MARKER = '<!-- ubiq-goal-closed: {name} {ac} -->'

Action = dict[str, Any]
Issue = Mapping[str, Any]


class SyncError(Exception):
    """A record the sync cannot read."""


@dataclass(frozen=True)
class Desired:
    """What GitHub should hold for one record item (today, one goal criterion).

    `ident` is copied into every action about the item. `marker` is the text
    inside the generated body marker that finds the issue again. `state` is
    `closed` when the record is done, else `open`. Later tickets add fields here
    (priority, requires, part_of) and one fact function each.
    """
    kind: str
    ident: Mapping[str, str]
    marker: str
    title: str
    body: str
    state: str
    listed: tuple[int, ...] = ()
    close_comment: str = ''


# -- desired state: records -> Desired ---------------------------------------------

def _goal_body(goal: Mapping[str, Any], ac: str, criterion: Mapping[str, Any], marker: str) -> str:
    checks = [s['check'] for s in criterion['support']]
    evidence = '\n'.join(f"- `{c['path']}`: `{c['anchor']}`" for c in checks) or '- None cited yet.'
    paths = ' '.join(dict.fromkeys(c['path'] for c in checks)) or 'tests/test_goals.py'
    return (f"Criterion from `{goal['path']}`:\n\n"
            f"> {goal['text'].get(ac, ac)}\n\n"
            f"## Gap\n\n{criterion['gap']}\n\n## Cited checks\n\n{evidence}\n\n"
            "## Verify\n\n```sh\nubiq check\n"
            f"python3 -m pytest {paths}\n```\n\n"
            "Then review the cited tests against the criterion. When it holds, set the "
            "criterion to `met` with its support and a `review` record. The merge closes "
            f"this issue.\n\n<!-- {marker} -->\n")


def load_goal(path: Path, root: Path) -> dict[str, Any]:
    """Read a goal file into its name, repository path, criteria, and criterion lines."""
    path = Path(path).resolve()
    try:
        data = load_data(path, frontmatter=True)
        text = {m.group(1): ' '.join(m.group(0).split())
                for m in CRITERION_RE.finditer(path.read_text(encoding='utf-8'))}
        return {'name': data['name'], 'path': path.relative_to(Path(root).resolve()).as_posix(),
                'criteria': data['criteria'], 'text': text}
    except (ValueError, KeyError, OSError) as exc:
        raise SyncError(f"{path}: not a readable goal ({exc})") from exc


def goal_desired(goal: Mapping[str, Any], sha: str = '') -> list[Desired]:
    """One `Desired` per criterion: open until the criterion is `met`, then closed."""
    items = []
    for ac, criterion in goal['criteria'].items():
        marker = f"ubiq-goal: {goal['name']} {ac}"
        title = goal['text'].get(ac, ac).split(': ', 1)[-1]
        met = criterion['assessment'] == 'met'
        comment = ''
        if met:
            review = criterion['review']
            comment = (f"Goal `{goal['name']}` {ac} is `met` at {sha or 'the merged commit'}. "
                       f"Review by {review['by']}: {review['note']}\n\n"
                       + CLOSED_MARKER.format(name=goal['name'], ac=ac))
        items.append(Desired(
            kind='goal', ident={'goal': goal['name'], 'criterion': ac}, marker=marker,
            title=textwrap.shorten(f"{goal['name']} {ac}: {title}", 200),
            body=_goal_body(goal, ac, criterion, marker),
            state='closed' if met else 'open',
            listed=tuple(criterion.get('issues', [])), close_comment=comment))
    return items


def desired_from_config(cfg: Config, sha: str = '') -> list[Desired]:
    """Desired state for every record file that `sync.records` selects."""
    assert cfg.sync is not None
    items: list[Desired] = []
    for record in cfg.sync.records:
        for path in sorted(record.glob.walk(cfg.ignore)):
            if record.kind == 'goal':
                items += goal_desired(load_goal(path, cfg.root), sha)
    return items


# -- planner: desired vs snapshot -> actions ---------------------------------------

def _marked(snapshot: Iterable[Issue]) -> dict[str, list[Issue]]:
    index: dict[str, list[Issue]] = {}
    for issue in snapshot:
        if (issue.get('user') or {}).get('login') != BOT:
            continue
        for match in MARKER_RE.finditer(issue.get('body') or ''):
            index.setdefault(match.group(1), []).append(issue)
    return index


def fact_exists(item: Desired, tracked: Sequence[int], issues: Mapping[int, Issue]) -> list[Action]:
    """An open record needs an issue; create one when none tracks it."""
    if tracked or item.state != 'open':
        return []
    return [{'action': 'create', **item.ident, 'title': item.title, 'body': item.body}]


def fact_state(item: Desired, tracked: Sequence[int], issues: Mapping[int, Issue]) -> list[Action]:
    """A done record closes its open issues. Never reopen: an open record leaves state alone."""
    if item.state != 'closed':
        return []
    return [{'action': 'close', **item.ident, 'issue': n, 'comment': item.close_comment}
            for n in tracked if issues.get(n, {}).get('state') == 'open']


# Each mirrored fact: (item, tracked issue numbers, issues by number) -> actions.
FACTS: tuple[Callable[[Desired, Sequence[int], Mapping[int, Issue]], list[Action]], ...] = (
    fact_exists, fact_state)


def plan(desired: Iterable[Desired], snapshot: Sequence[Issue]) -> list[Action]:
    """Return create, close, noop, and warn actions for every desired item.

    `snapshot` holds dicts with `number`, `state`, `body`, and `user.login`.
    Markers count only in issues opened by `BOT`. Issues that are neither listed
    by a record nor marked by `BOT` are ignored. A listed number that is not an
    existing issue (a pull request, a typo) gets a `warn`. Applying the result
    and planning again returns only `noop` actions.
    """
    by_number = {i['number']: i for i in snapshot}
    by_marker = _marked(snapshot)
    actions: list[Action] = []
    for item in desired:
        marked = [i['number'] for i in by_marker.get(item.marker, [])]
        tracked = list(dict.fromkeys([*item.listed, *marked]))
        actions += [{'action': 'warn', **item.ident, 'issue': n, 'reason': 'listed number is not an issue'}
                    for n in item.listed if n not in by_number]
        found = [a for fact in FACTS for a in fact(item, tracked, by_number)]
        actions += found
        if not found:
            reason = 'met; no open issue' if item.state == 'closed' else 'tracked'
            actions.append({'action': 'noop', **item.ident, 'reason': reason, 'issues': tracked})
    return actions


def drift(actions: Iterable[Action]) -> list[Action]:
    """The actions that differ from GitHub: everything but `noop`."""
    return [a for a in actions if a['action'] != 'noop']


# -- GitHub REST adapter -----------------------------------------------------------

Transport = Callable[[str, str, str, 'dict | None'], Any]


def urllib_transport(method: str, url: str, token: str, payload: dict | None = None) -> Any:
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read() or b'null')


class GitHub:
    """Read the issue snapshot and perform actions on one repository."""

    def __init__(self, repo: str, token: str = '', transport: Transport = urllib_transport,
                 pause: float = 1.0) -> None:
        self.repo, self.token, self.transport, self.pause = repo, token, transport, pause
        self.base = f'https://api.github.com/repos/{repo}/issues'
        self.handlers: dict[str, Callable[[Action], None]] = {
            'create': self._create, 'close': self._close}

    def _call(self, method: str, url: str, payload: dict | None = None) -> Any:
        return self.transport(method, url, self.token, payload)

    def snapshot(self) -> list[Issue]:
        """Every issue (not pull request) in the repository, open or closed."""
        issues: list[Issue] = []
        page = 1
        while True:
            batch = self._call('GET', f'{self.base}?state=all&per_page=100&page={page}')
            issues += [i for i in batch if 'pull_request' not in i]
            if len(batch) < 100:
                return issues
            page += 1

    def _create(self, action: Action) -> None:
        issue = self._call('POST', self.base, {'title': action['title'], 'body': action['body']})
        action['issue'] = issue['number']

    def _close(self, action: Action) -> None:
        url = f"{self.base}/{action['issue']}"
        self._call('PATCH', url, {'state': 'closed', 'state_reason': 'completed'})
        marker = action['comment'].rsplit('\n', 1)[-1]
        comments = self._call('GET', f'{url}/comments?per_page=100')
        if not any(marker in (c.get('body') or '') for c in comments):
            time.sleep(self.pause)
            self._call('POST', f'{url}/comments', {'body': action['comment']})

    def apply(self, actions: Iterable[Action], done: list[Action]) -> None:
        """Perform each action, appending finished ones to `done`. `noop` and `warn` do nothing."""
        for action in actions:
            handler = self.handlers.get(action['action'])
            if handler is None:
                continue
            handler(action)
            done.append(action)
            time.sleep(self.pause)  # Space out writes for GitHub's secondary rate limit.


# -- command -----------------------------------------------------------------------

GUIDANCE = ("sync is not configured. Add a `sync:` section to ubiq.yaml, for example:\n"
            "  sync:\n    repo: owner/name\n    records:\n"
            "      - {glob: \"docs/goals/*-goal.md\", kind: goal}")


def _dump(value: Any) -> None:
    print(json.dumps(value, indent=2))


def _head(root: Path, rev: str | None = None) -> str:
    sha = None if rev else os.environ.get('GITHUB_SHA')
    if sha:
        return sha
    done = subprocess.run(['git', 'rev-parse', rev or 'HEAD'], cwd=root, capture_output=True,
                          text=True, check=False)
    return done.stdout.strip()


def _git(root: Path, rev: str, *cmd: str) -> bytes:
    done = subprocess.run(['git', *cmd], cwd=root, capture_output=True, check=False)
    if done.returncode:
        raise SyncError(f'cannot read revision {rev}: {done.stderr.decode().strip()}')
    return done.stdout


@contextlib.contextmanager
def revision_root(root: Path, rev: str) -> Iterator[Path]:
    """A temporary directory holding `ubiq.yaml` and the sync's record files as they are at `rev`.

    Only those files are read, with `git show`, and only regular files are written
    (symlinks are skipped), so nothing in the revision can point outside the
    directory. The repository itself is not touched.
    """
    with tempfile.TemporaryDirectory() as name:
        tmp = Path(name)

        def fetch(path: str) -> None:
            target = tmp / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_git(root, rev, 'show', f'{rev}:{path}'))

        fetch('ubiq.yaml')
        cfg = load_config(tmp)
        if cfg.sync is not None:
            listing = _git(root, rev, 'ls-tree', '-r', '-z', rev).decode().split('\0')
            for entry in filter(None, listing):
                meta, path = entry.split('\t', 1)
                if meta.startswith('100') and any(r.glob.matches(tmp / path) for r in cfg.sync.records):
                    fetch(path)
        yield tmp


def cmd_sync(args, transport: Transport = urllib_transport, pause: float = 1.0) -> int:
    """`ubiq sync github`: print the plan (default), `--apply` it, or `--check` for drift.

    `--ref REV` reads the records and `ubiq.yaml` as they are at REV instead of the
    working tree. A pull request checks drift against its base this way: drift is
    GitHub disagreeing with the base, and what the pull request itself changes is
    pending on merge, not drift.
    """
    root = Path(args.root).resolve()
    ref = getattr(args, 'ref', None)
    if not ref:
        return _sync(args, root, root, transport, pause)
    try:
        with revision_root(root, ref) as snapshot:
            return _sync(args, root, snapshot, transport, pause)
    except SyncError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2


def _sync(args, root: Path, source: Path, transport: Transport, pause: float) -> int:
    cfg = load_config(source)
    if cfg.sync is None:
        print(f"error: {GUIDANCE}", file=sys.stderr)
        return 2
    repo = args.repo or cfg.sync.repo or os.environ.get('GITHUB_REPOSITORY')
    if not repo:
        print('error: name the repository in sync.repo, --repo, or GITHUB_REPOSITORY', file=sys.stderr)
        return 2
    token = os.environ.get('GITHUB_TOKEN', '')
    if args.apply and not token:
        print('error: --apply needs GITHUB_TOKEN', file=sys.stderr)
        return 2
    if args.check and not token:
        print(f'skipped: --check needs GITHUB_TOKEN to read {repo}; the mirror was not compared',
              file=sys.stderr)
        return 0
    github = GitHub(repo, token, transport, pause)
    try:
        actions = plan(desired_from_config(cfg, _head(root, getattr(args, 'ref', None))), github.snapshot())
    except SyncError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    except OSError as exc:  # URLError and HTTPError are OSErrors.
        print(f'error: cannot read the records or the issues of {repo}: {exc}', file=sys.stderr)
        return 2
    if args.check:
        found = drift(actions)
        _dump(found)
        if found:
            print(f'drift: {len(found)} difference(s) between the records and {repo}', file=sys.stderr)
        return 1 if found else 0
    if not args.apply:
        _dump(actions)
        return 0
    warnings = [a for a in actions if a['action'] == 'warn']
    done: list[Action] = []
    try:
        github.apply(actions, done)
    finally:
        _dump({'completed': done, 'warnings': warnings})
    return 1 if warnings else 0
