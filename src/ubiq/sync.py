"""Mirror records to GitHub issues (`ubiq sync github`).

The sync is a diff. `desired_from_config` reads the records and returns what
GitHub should hold (`Desired`). `plan` compares that with a snapshot of the
repository's issues and returns actions; only `noop` actions mean the mirror is
in sync, and any other action is drift. `plan` is pure. `GitHub` is the thin
adapter: it reads the snapshot and performs actions through an injectable
transport.

Each mirrored fact is one function in `FACTS`: given a desired item and the
issues that track it, return the actions that make GitHub match. A later fact
(blocked-by link, sub-issue) adds one function there and one handler in
`GitHub.handlers`; the matching, drift, and CLI code do not change. `fact_priority`
is the model: it mirrors `priority` as one `<sync.label_prefix>Pn` label.

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
import urllib.error
import urllib.parse
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

DEFAULT_LABEL_PREFIX = 'priority: '

Action = dict[str, Any]
Issue = Mapping[str, Any]


class SyncError(Exception):
    """A record the sync cannot read."""


@dataclass(frozen=True)
class Desired:
    """What GitHub should hold for one record item (today, one goal criterion).

    `ident` is copied into every action about the item. `marker` is the text
    inside the generated body marker that finds the issue again. `state` is
    `closed` when the record is done, else `open`. `priority` (`P1`, `P2`, `P3`, or
    empty when the record sets none) is mirrored as the label `label_prefix + priority`.
    `parent` names the record this one is part of (its goal, or the criterion's `part_of`)
    and `parent_issue` is that record's issue number, or 0 when it has none: the item's
    issues are then sub-issues of that issue.
    Later tickets add fields here (requires) and one fact function each.
    """
    kind: str
    ident: Mapping[str, str]
    marker: str
    title: str
    body: str
    state: str
    listed: tuple[int, ...] = ()
    close_comment: str = ''
    priority: str = ''
    label_prefix: str = DEFAULT_LABEL_PREFIX
    parent: str = ''
    parent_issue: int = 0


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
                'criteria': data['criteria'], 'text': text, 'issue': data.get('issue', 0)}
    except (ValueError, KeyError, OSError) as exc:
        raise SyncError(f"{path}: not a readable goal ({exc})") from exc


def goal_desired(goal: Mapping[str, Any], sha: str = '',
                 label_prefix: str = DEFAULT_LABEL_PREFIX,
                 goal_issues: Mapping[str, int] | None = None) -> list[Desired]:
    """One `Desired` per criterion: open until the criterion is `met`, then closed.

    A criterion's `issue` is tracked like each number in its `issues` list. A criterion
    is part of its goal, or of the goal its `part_of` names; `goal_issues` maps goal
    names to their `issue`, which becomes the parent of the criterion's issues.
    """
    goal_issues = {goal['name']: goal.get('issue', 0), **(goal_issues or {})}
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
        parent = (criterion.get('part_of') or [goal['name']])[0]
        items.append(Desired(
            kind='goal', ident={'goal': goal['name'], 'criterion': ac}, marker=marker,
            title=textwrap.shorten(f"{goal['name']} {ac}: {title}", 200),
            body=_goal_body(goal, ac, criterion, marker),
            state='closed' if met else 'open',
            listed=tuple(dict.fromkeys([*criterion.get('issues', []), *([criterion['issue']]
                                                                       if 'issue' in criterion else [])])),
            close_comment=comment, priority=criterion.get('priority', ''),
            label_prefix=label_prefix, parent=parent, parent_issue=goal_issues.get(parent, 0)))
    return items


def desired_from_config(cfg: Config, sha: str = '') -> list[Desired]:
    """Desired state for every record file that `sync.records` selects."""
    assert cfg.sync is not None
    goals = [load_goal(path, cfg.root) for record in cfg.sync.records if record.kind == 'goal'
             for path in sorted(record.glob.walk(cfg.ignore))]
    issues = {g['name']: g['issue'] for g in goals}
    return [item for g in goals for item in goal_desired(g, sha, cfg.sync.label_prefix, issues)]


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
    labels = [item.label_prefix + item.priority] if _mirrors_priority(item) else []
    return [{'action': 'create', **item.ident, 'title': item.title, 'body': item.body,
             **({'labels': labels} if labels else {}),
             **({'parent_issue': item.parent_issue} if item.parent_issue else {})}]


def fact_state(item: Desired, tracked: Sequence[int], issues: Mapping[int, Issue]) -> list[Action]:
    """A done record closes its open issues. Never reopen: an open record leaves state alone."""
    if item.state != 'closed':
        return []
    return [{'action': 'close', **item.ident, 'issue': n, 'comment': item.close_comment}
            for n in tracked if issues.get(n, {}).get('state') == 'open']


def _mirrors_priority(item: Desired) -> bool:
    # An empty prefix would own every label, so it owns none.
    return bool(item.priority and item.label_prefix.strip())


def _label_names(issue: Issue) -> list[str]:
    return [label['name'] if isinstance(label, Mapping) else str(label)
            for label in issue.get('labels') or []]


def fact_priority(item: Desired, tracked: Sequence[int], issues: Mapping[int, Issue]) -> list[Action]:
    """An open issue carries exactly one label with the prefix: `label_prefix + priority`.

    Only labels that start with the prefix are added or removed; every other label is
    left alone, and so is the issue when the record sets no `priority`. A label that
    someone changed on GitHub is a `label` action, which is drift. Names compare
    without regard to case, as GitHub does.
    """
    if not _mirrors_priority(item) or item.state != 'open':
        return []
    prefix, want = item.label_prefix.casefold(), (item.label_prefix + item.priority)
    actions: list[Action] = []
    for n in tracked:
        issue = issues.get(n)
        if issue is None or issue.get('state') != 'open':
            continue
        names = _label_names(issue)
        remove = [x for x in names if x.casefold().startswith(prefix) and x.casefold() != want.casefold()]
        add = [] if any(x.casefold() == want.casefold() for x in names) else [want]
        if add or remove:
            actions.append({'action': 'label', **item.ident, 'issue': n, 'add': add, 'remove': remove})
    return actions


def fact_part_of(item: Desired, tracked: Sequence[int], issues: Mapping[int, Issue]) -> list[Action]:
    """Each issue that tracks the record is a sub-issue of the parent record's issue.

    An issue missing from the parent's `sub_issues` (the snapshot's list of its children)
    is a `link`; GitHub allows one parent per issue, so the link replaces any other parent.
    A record whose parent has no `issue` plans nothing, and a parent that is not an issue
    gets a `warn`. A sub-issue that GitHub holds but no record asks for is `unlink`,
    planned across items by `unexpected_sub_issues`.
    """
    if not item.parent_issue:
        return []
    parent = issues.get(item.parent_issue)
    if parent is None:
        return [{'action': 'warn', **item.ident, 'issue': item.parent_issue,
                 'reason': f'parent issue of {item.parent} is not an issue'}]
    children = set(parent.get('sub_issues') or ())
    return [{'action': 'link', **item.ident, 'issue': n, 'parent': item.parent_issue,
             'sub_issue_id': issues[n].get('id')}
            for n in tracked if n in issues and n != item.parent_issue and n not in children]


def unexpected_sub_issues(desired: Sequence[Desired], issues: Mapping[int, Issue],
                          tracked: Mapping[int, Sequence[int]]) -> list[Action]:
    """Sub-issues on a parent issue that no record puts there: added by hand on GitHub.

    `tracked` maps each item's index in `desired` to its issue numbers. An issue that a
    record moves to another parent is not unexpected: its `link` replaces the old parent.
    """
    expected = {n for i, item in enumerate(desired) if item.parent_issue for n in tracked[i]}
    found: list[Action] = []
    for parent in sorted({d.parent_issue for d in desired if d.parent_issue in issues}):
        for n in issues[parent].get('sub_issues') or ():
            if n not in expected:
                found.append({'action': 'unlink', 'issue': n, 'parent': parent,
                              'sub_issue_id': issues.get(n, {}).get('id'),
                              'reason': 'sub-issue is not part_of the parent record'})
    return found


# Each mirrored fact: (item, tracked issue numbers, issues by number) -> actions.
FACTS: tuple[Callable[[Desired, Sequence[int], Mapping[int, Issue]], list[Action]], ...] = (
    fact_exists, fact_state, fact_priority, fact_part_of)


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
    desired = list(desired)
    tracked_by_item: dict[int, list[int]] = {}
    for index, item in enumerate(desired):
        marked = [i['number'] for i in by_marker.get(item.marker, [])]
        tracked = list(dict.fromkeys([*item.listed, *marked]))
        tracked_by_item[index] = tracked
        actions += [{'action': 'warn', **item.ident, 'issue': n, 'reason': 'listed number is not an issue'}
                    for n in item.listed if n not in by_number]
        found = [a for fact in FACTS for a in fact(item, tracked, by_number)]
        actions += found
        if not found:
            reason = 'met; no open issue' if item.state == 'closed' else 'tracked'
            actions.append({'action': 'noop', **item.ident, 'reason': reason, 'issues': tracked})
    return actions + unexpected_sub_issues(desired, by_number, tracked_by_item)


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
            'create': self._create, 'close': self._close, 'label': self._label,
            'link': self._link, 'unlink': self._unlink}

    def _call(self, method: str, url: str, payload: dict | None = None) -> Any:
        return self.transport(method, url, self.token, payload)

    def snapshot(self, parents: Iterable[int] = ()) -> list[Issue]:
        """Every issue (not pull request) in the repository, open or closed.

        For each number in `parents` that is an issue, `sub_issues` lists the numbers
        of its sub-issues.
        """
        issues: list[Issue] = []
        page = 1
        while True:
            batch = self._call('GET', f'{self.base}?state=all&per_page=100&page={page}')
            issues += [i for i in batch if 'pull_request' not in i]
            if len(batch) < 100:
                break
            page += 1
        by_number: dict[int, Any] = {i['number']: i for i in issues}
        for parent in dict.fromkeys(parents):
            if parent in by_number:
                by_number[parent]['sub_issues'] = self._sub_issues(parent)
        return issues

    def _sub_issues(self, parent: int) -> list[int]:
        found: list[int] = []
        page = 1
        while True:
            batch = self._call('GET', f'{self.base}/{parent}/sub_issues?per_page=100&page={page}')
            found += [i['number'] for i in batch]
            if len(batch) < 100:
                return found
            page += 1

    def _attach(self, parent: int, sub_issue_id: Any) -> None:
        # One parent per issue: replace_parent moves an issue that has another parent.
        self._call('POST', f'{self.base}/{parent}/sub_issues',
                   {'sub_issue_id': sub_issue_id, 'replace_parent': True})

    def _link(self, action: Action) -> None:
        self._attach(action['parent'], action['sub_issue_id'])

    def _unlink(self, action: Action) -> None:
        try:
            self._call('DELETE', f"{self.base}/{action['parent']}/sub_issue",
                       {'sub_issue_id': action['sub_issue_id']})
        except urllib.error.HTTPError as exc:
            if exc.code != 404:  # already gone is the state we want
                raise

    def _create(self, action: Action) -> None:
        payload = {'title': action['title'], 'body': action['body']}
        if action.get('labels'):
            payload['labels'] = action['labels']
        issue = self._call('POST', self.base, payload)
        action['issue'] = issue['number']
        if action.get('parent_issue'):
            self._attach(action['parent_issue'], issue['id'])

    def _label(self, action: Action) -> None:
        url = f"{self.base}/{action['issue']}/labels"
        for name in action['remove']:
            try:
                self._call('DELETE', f"{url}/{urllib.parse.quote(name, safe='')}")
            except urllib.error.HTTPError as exc:
                if exc.code != 404:  # already gone is the state we want
                    raise
        if action['add']:
            self._call('POST', url, {'labels': action['add']})

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

        _git(root, rev, 'rev-parse', '--verify', '--quiet', f'{rev}^{{commit}}')
        if _git(root, rev, 'ls-tree', '--name-only', rev, 'ubiq.yaml').strip():
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
    if cfg.sync is None and getattr(args, 'ref', None):
        print(f'skipped: {args.ref} has no sync section in ubiq.yaml, so it mirrors nothing', file=sys.stderr)
        return 0
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
        desired = desired_from_config(cfg, _head(root, getattr(args, 'ref', None)))
        actions = plan(desired, github.snapshot(d.parent_issue for d in desired if d.parent_issue))
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
