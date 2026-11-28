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
is the model: it mirrors `priority` as one `<sync.label_prefix>Pn` label. Facts that
need the open pull requests include `fact_in_review`, which derives the
`status: in review` label, and `fact_stack`, which reports a pull request whose base is not its
required record's branch (a `stack` action; the sync reports and never retargets).

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

import yaml

from . import xref
from .config import Config, load_config
from .plan import PlanError, feature_status
from .records import DEFAULT_NS, normalize
from .scan import HTML_COMMENT_RE, _blank_fences, _blank_inline
from .schemas import _annotations, load_data

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
    A nonzero `parent_issue` identifies the issue that owns this item’s sub-issues.
    `creates` is false when an open item with no issue should stay without one.
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
    # `requires`, split: issue numbers of the tracked records it names (None when the
    # record sets no `requires`, which leaves links and the generated line unmanaged)
    # and the pull requests it lists as `pr: <n>`.
    requires: tuple[int, ...] | None = None
    requires_prs: tuple[int, ...] = ()
    # Links to other issues, for the facts that mirror them (blocked-by, sub-issue).
    # `requires_markers` holds the `marker` of each item this one waits on; `parent_issue`
    # is the number of the issue this one belongs under (0 for none). Plan steps set both.
    requires_markers: tuple[str, ...] = ()
    parent_issue: int = 0
    parent: str = ''
    creates: bool = True
    # A scenario-bound criterion whose scenario failed on this revision: when every
    # tracked issue is closed, open a new one instead of reopening (the sync never reopens).
    regression: bool = False
    # `pr`: the record's implementing pull requests, and for each record it `requires`
    # that has a `pr`, that record's name and pull requests (see `Stack`).
    prs: tuple[int, ...] = ()
    required_prs: tuple[tuple[str, tuple[int, ...]], ...] = ()


@dataclass(frozen=True)
class Stack:
    """A record's pull requests and the pull requests of the records it requires."""
    ident: Mapping[str, str]
    prs: tuple[int, ...]
    required: tuple[tuple[str, tuple[int, ...]], ...]


@dataclass(frozen=True)
class Tracked:
    """What a schema-bound frontmatter record says about its tracking."""
    issue: int | None
    prs: tuple[int, ...]
    requires: tuple[str, ...]


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


def _scenario_body(goal: Mapping[str, Any], ac: str, feature: str, marker: str, failed: bool) -> str:
    state = (f"## Regression\n\nA scenario tagged `@{ac}` failed on `main`.\n\n" if failed else '')
    return (f"Criterion from `{goal['path']}`:\n\n"
            f"> {goal['text'].get(ac, ac)}\n\n{state}"
            f"## Acceptance\n\nThe scenarios tagged `@{ac}` in `{feature}` accept this criterion. "
            "It is met when all of them pass on `main`; nobody marks it by hand.\n\n"
            "## Verify\n\n```sh\nubiq check\n"
            f"python3 -m pytest tests/scenarios -p ubiq.pytest_plugin --ubiq-results results.json\n"
            f"ubiq sync github --dry-run --results results.json\n```\n\n"
            "When the scenarios pass on `main`, the sync closes this issue.\n\n"
            f"<!-- {marker} -->\n")


def criterion_met(goal: Mapping[str, Any], ac: str,
                  results: Mapping[tuple[str, str], str] | None) -> bool | None:
    """Whether a criterion holds: True, False, or None when nothing can say yet.

    A scenario-bound criterion holds when its scenarios passed in `results`; without
    results its state is unknown. Any other criterion holds when its assessment is `met`.
    """
    criterion = goal['criteria'][ac]
    if criterion.get('scenario') is True:
        if results is None:
            return None
        return results.get((_feature_path(goal), ac)) == 'passed'
    return criterion.get('assessment') == 'met'


def _feature_path(goal: Mapping[str, Any]) -> str:
    return str(Path(goal['path']).with_suffix('.feature').as_posix())


def goal_issue_desired(goals: Sequence[Mapping[str, Any]], sha: str = '',
                       results: Mapping[tuple[str, str], str] | None = None) -> list[Desired]:
    """A goal's own `issue` closes when every one of its criteria holds.

    A criterion with `assessed_in` holds when the criterion it names does. The goal issue
    is never created here, and stays open while any criterion is unknown or unmet.
    """
    by_name = {g['name']: g for g in goals}

    def holds(goal: Mapping[str, Any], ac: str) -> bool | None:
        target = goal['criteria'][ac].get('assessed_in')
        if target:
            other = by_name.get(target['goal'])
            if other is None or target['criterion'] not in other['criteria']:
                return False
            return criterion_met(other, target['criterion'], results)
        return criterion_met(goal, ac, results)

    items = []
    for goal in goals:
        if not goal.get('issue'):
            continue
        done = all(holds(goal, ac) is True for ac in goal['criteria'])
        items.append(Desired(
            kind='goal', ident={'goal': goal['name']}, marker=f"ubiq-goal: {goal['name']}",
            title=goal['name'], body='', state='closed' if done else 'open',
            listed=(goal['issue'],), creates=False,
            close_comment=(f"Every criterion of goal `{goal['name']}` holds at {sha or 'the merged commit'}.\n\n"
                           f"<!-- ubiq-goal-closed: {goal['name']} -->") if done else ''))
    return items


def resolve_priority(item: Mapping[str, Any], container: Mapping[str, Any]) -> str:
    """An item's own `priority` wins; without one it takes its container's (plan or goal)."""
    return item.get('priority') or container.get('priority') or ''


def load_goal(path: Path, root: Path) -> dict[str, Any]:
    """Read a goal file into its name, repository path, criteria, and criterion lines."""
    path = Path(path).resolve()
    try:
        data = load_data(path, frontmatter=True)
        text = {m.group(1): ' '.join(m.group(0).split())
                for m in CRITERION_RE.finditer(path.read_text(encoding='utf-8'))}
        return {'name': data['name'], 'path': path.relative_to(Path(root).resolve()).as_posix(),
                'criteria': data['criteria'], 'text': text, 'issue': data.get('issue', 0), 'priority': data.get('priority', '')}
    except (ValueError, KeyError, OSError) as exc:
        raise SyncError(f"{path}: not a readable goal ({exc})") from exc


def goal_desired(goal: Mapping[str, Any], sha: str = '',
                 label_prefix: str = DEFAULT_LABEL_PREFIX,
                 numbers: Mapping[str, int] | None = None,
                 pulls: Mapping[str, tuple[int, ...]] | None = None,
                 goal_issues: Mapping[str, int] | None = None,
                 prioritized_only: bool = False,
                 results: Mapping[tuple[str, str], str] | None = None) -> list[Desired]:
    """One `Desired` per criterion: open until the criterion is `met`, then closed.

    A criterion with `scenario: true` is met when every scenario tagged with its label in
    `<goal>.feature` passed in `results` (`criterion_met`). Without results it stays open.
    A failed scenario marks a regression, which opens a new issue once all are closed.

    A criterion with `assessed_in` is assessed by the criterion it names, so it has none.
    With `prioritized_only` (`sync.create: prioritized`), a criterion opens a new issue
    only when it or its goal sets a `priority`; a listed or marked issue is still tracked
    and closed when the criterion is `met`.

    A criterion's `issue` is tracked like each number in its `issues` list. `numbers`
    maps a normalized record name to its issue, to resolve the criterion's `requires`;
    `pulls` maps it to the record's `pr`, for the stack check. `goal_issues` maps goal
    names to parent issue numbers for `part_of`.
    """
    goal_issues = {normalize(k): n for k, n in {goal['name']: goal.get('issue', 0), **(goal_issues or {})}.items()}
    items = []
    for ac, criterion in goal['criteria'].items():
        if 'assessed_in' in criterion:
            continue
        marker = f"ubiq-goal: {goal['name']} {ac}"
        title = goal['text'].get(ac, ac).split(': ', 1)[-1]
        bound = criterion.get('scenario') is True
        met = criterion_met(goal, ac, results) is True
        failed = bound and results is not None and results.get((_feature_path(goal), ac)) == 'failed'
        comment = ''
        if met and bound:
            comment = (f"Goal `{goal['name']}` {ac} is `met` at {sha or 'the merged commit'}: every "
                       f"scenario tagged `@{ac}` in `{_feature_path(goal)}` passed.\n\n"
                       + CLOSED_MARKER.format(name=goal['name'], ac=ac))
        elif met:
            review = criterion['review']
            comment = (f"Goal `{goal['name']}` {ac} is `met` at {sha or 'the merged commit'}. "
                       f"Review by {review['by']}: {review['note']}\n\n"
                       + CLOSED_MARKER.format(name=goal['name'], ac=ac))
        parent = (criterion.get('part_of') or [goal['name']])[0]
        items.append(Desired(
            kind='goal', ident={'goal': goal['name'], 'criterion': ac}, marker=marker,
            title=textwrap.shorten(f"{goal['name']} {ac}: {title}", 200),
            body=(_scenario_body(goal, ac, _feature_path(goal), marker, failed) if bound
                  else _goal_body(goal, ac, criterion, marker)),
            state='closed' if met else 'open', regression=failed,
            listed=tuple(dict.fromkeys([*criterion.get('issues', []), *([criterion['issue']]
                                                                       if 'issue' in criterion else [])])),
            close_comment=comment, priority=resolve_priority(criterion, goal),
            creates=failed or not prioritized_only or bool(resolve_priority(criterion, goal)),
            label_prefix=label_prefix, parent=parent, parent_issue=goal_issues.get(normalize(parent), 0),
            prs=xref.pr_numbers(criterion.get('pr', [])),
            required_prs=_required_prs(criterion, pulls or {}),
            **_requires(criterion, numbers or {})))
    return items


def _requires(criterion: Mapping[str, Any], numbers: Mapping[str, int]) -> dict[str, Any]:
    """Split `requires` into blocker issue numbers and `pr: <n>` entries.

    A name that resolves to no tracked record (one without an `issue`) makes no link.
    """
    if 'requires' not in criterion:
        return {}
    prs: list[int] = []
    blockers: list[int] = []
    for value in criterion['requires']:
        pr = xref.pr_entry(value)
        if pr is not None:
            prs.append(pr)
        elif normalize(value) in numbers:
            blockers.append(numbers[normalize(value)])
    return {'requires': tuple(dict.fromkeys(blockers)), 'requires_prs': tuple(dict.fromkeys(prs))}


def _required_prs(item: Mapping[str, Any], pulls: Mapping[str, tuple[int, ...]]) -> tuple[tuple[str, tuple[int, ...]], ...]:
    """The records `item` requires that list a `pr`, as (name, pull requests)."""
    names = dict.fromkeys(normalize(v) for v in item.get('requires', ()) if xref.pr_entry(v) is None)
    return tuple((name, pulls[name]) for name in names if pulls.get(name))


def tracked_records(cfg: Config) -> dict[str, Tracked]:
    """Normalized record name -> its tracking fields, for each schema-bound frontmatter record."""
    found: dict[str, Tracked] = {}
    for spec in cfg.schemas:
        if spec.format != 'frontmatter':
            continue
        for pattern in spec.files:
            for path in sorted(pattern.walk(cfg.ignore)):
                try:
                    data = load_data(path, frontmatter=True)
                except (ValueError, OSError):
                    continue
                if not isinstance(data, dict) or not isinstance(data.get('name'), str):
                    continue
                number = data.get('issue')
                prs, requires = data.get('pr'), data.get('requires')
                found.setdefault(normalize(data['name']), Tracked(
                    number if isinstance(number, int) and not isinstance(number, bool) else None,
                    xref.pr_numbers(prs),
                    tuple(v for v in requires if isinstance(v, str)) if isinstance(requires, list) else ()))
    return found


def load_plan(path: Path, root: Path) -> dict[str, Any]:
    """Read a plan file into its name, repository path, status, issue, and steps."""
    path = Path(path).resolve()
    try:
        data = load_data(path, frontmatter=True)
        return {'name': data['name'], 'path': path.relative_to(Path(root).resolve()).as_posix(),
                'status': data['status'], 'issue': data['issue'], 'steps': data['steps'],
                'priority': data.get('priority', '')}
    except (ValueError, KeyError, OSError) as exc:
        raise SyncError(f"{path}: not a readable plan ({exc})") from exc


def _step_body(plan_record: Mapping[str, Any], step: str, spec: Mapping[str, Any], marker: str) -> str:
    rows = [('Plan', f"`{plan_record['path']}` (#{plan_record['issue']})"),
            ('Requires', ', '.join(f'`{r}`' for r in spec.get('requires', [])) or 'nothing'),
            ('Branch', f"`{spec['branch']}`" if spec.get('branch') else 'not started'),
            ('Base', f"`{spec['base']}`" if spec.get('base') else 'not set')]
    lines = '\n'.join(f'- {k}: {v}' for k, v in rows)
    return (f"Step `{step}` of plan `{plan_record['name']}`.\n\n{lines}\n\n"
            "The plan record is the source for these facts; update it in the pull request "
            f"that changes them.\n\n<!-- {marker} -->\n")


def plan_desired(plan_record: Mapping[str, Any], label_prefix: str = DEFAULT_LABEL_PREFIX) -> list[Desired]:
    """One `Desired` per plan step, a sub-issue of the plan's issue that waits on its `requires`.

    A `proposed` or `abandoned` plan mirrors nothing, and a `done` plan closes its issues.
    A step without its own `priority` takes the plan's (`resolve_priority`).
    A step that names a `pr` and no `issue` is tracked by that pull request, so it gets no
    issue. Its issue-backed steps become sub-issues of the plan issue.
    """
    if plan_record['status'] in ('proposed', 'abandoned'):
        return []
    steps = plan_record['steps']
    tracked = {name: spec for name, spec in steps.items() if spec.get('issue') or not spec.get('pr')}
    marker_of = {name: f"ubiq-plan: {plan_record['name']} {name}" for name in steps}
    done = plan_record['status'] == 'done'
    return [Desired(
        kind='plan-step', ident={'plan': plan_record['name'], 'step': name}, marker=marker_of[name],
        title=textwrap.shorten(f"{plan_record['name']}: {name}", 200),
        body=_step_body(plan_record, name, spec, marker_of[name]),
        state='closed' if done else 'open', listed=(spec['issue'],) if spec.get('issue') else (),
        close_comment=(f"Plan `{plan_record['name']}` is done.\n\n"
                       f"<!-- ubiq-plan-closed: {plan_record['name']} {name} -->") if done else '',
        label_prefix=label_prefix, priority=resolve_priority(spec, plan_record),
        requires_markers=tuple(_step_marker(r, tracked, marker_of)
                               for r in spec.get('requires', [])
                               if r in tracked or '/' in r),
        parent=plan_record['name'], parent_issue=plan_record['issue']) for name, spec in tracked.items()]


def _step_marker(required: str, tracked: Mapping[str, Any], marker_of: Mapping[str, str]) -> str:
    """The marker of a required step: one in this plan, or `<plan>/<step>` in another."""
    if required in tracked:
        return marker_of[required]
    other, _, step = required.partition('/')
    return f"ubiq-plan: {other} {step}"


def tracked_issue_numbers(cfg: Config) -> dict[str, int]:
    """Normalized record name -> `issue`, for each schema-bound frontmatter record that has both."""
    return {name: t.issue for name, t in tracked_records(cfg).items() if t.issue is not None}


def record_stacks(records: Mapping[str, Tracked]) -> list[Stack]:
    """A `Stack` for each record that lists a `pr`; a record's name is its ident."""
    pulls = {name: t.prs for name, t in records.items()}
    return [Stack({'record': name}, t.prs, _required_prs({'requires': t.requires}, pulls))
            for name, t in records.items() if t.prs]


def load_feature(path: Path, root: Path) -> dict[str, Any]:
    """Read a feature record into its frontmatter plus its repository path."""
    path = Path(path).resolve()
    try:
        data = dict(load_data(path, frontmatter=True))
        missing = [k for k in ('name', 'summary') if not isinstance(data.get(k), str)]
        if missing:
            raise KeyError(', '.join(missing))
        data['path'] = path.relative_to(Path(root).resolve()).as_posix()
        return data
    except (ValueError, KeyError, OSError) as exc:
        raise SyncError(f"{path}: not a readable feature ({exc})") from exc


def feature_desired(feature: Mapping[str, Any], sha: str = '',
                    label_prefix: str = DEFAULT_LABEL_PREFIX) -> list[Desired]:
    """One `Desired` for a feature record: open while `planned`, closed once `shipped`.

    A record with no `status` is shipped. `issue` is tracked like a goal criterion's.
    """
    name = feature['name']
    marker = f"ubiq-feature: {name}"
    try:
        shipped = feature_status(feature) == 'shipped'
    except PlanError as exc:
        raise SyncError(f"{feature['path']}: {exc}") from exc
    requires = ', '.join(f"`{r}`" for r in feature.get('requires') or []) or 'none'
    body = (f"Feature `{name}`, planned in `{feature['path']}`.\n\n{feature['summary']}\n\n"
            f"Specified in `{feature.get('docs', '')}`. Requires: {requires}.\n\n"
            "When the feature ships, set `status: shipped` in the record. The merge closes "
            f"this issue.\n\n<!-- {marker} -->\n")
    comment = (f"Feature `{name}` is `shipped` at {sha or 'the merged commit'}.\n\n"
               f"<!-- ubiq-feature-closed: {name} -->")
    return [Desired(
        kind='feature', ident={'feature': name}, marker=marker,
        title=textwrap.shorten(f"{name}: {feature['summary']}", 200), body=body,
        state='closed' if shipped else 'open',
        listed=(feature['issue'],) if 'issue' in feature else (),
        close_comment=comment if shipped else '', priority=feature.get('priority', ''),
        label_prefix=label_prefix)]


def desired_from_config(cfg: Config, sha: str = '',
                        records: Mapping[str, Tracked] | None = None,
                        results: Mapping[tuple[str, str], str] | None = None) -> list[Desired]:
    """Desired state for every record file that `sync.records` selects.

    `results` holds scenario outcomes (`scenarios.load_results`); without them, scenario-bound
    criteria and the goals that contain them are left open.
    """
    assert cfg.sync is not None
    items: list[Desired] = []
    if records is None:
        records = tracked_records(cfg)
    numbers = {name: t.issue for name, t in records.items() if t.issue is not None}
    pulls = {name: t.prs for name, t in records.items()}
    goals = [load_goal(path, cfg.root) for record in cfg.sync.records if record.kind == 'goal'
             for path in sorted(record.glob.walk(cfg.ignore))]
    goal_issues = {g['name']: g['issue'] for g in goals}
    for goal in goals:
        items += goal_desired(goal, sha, cfg.sync.label_prefix, numbers, pulls, goal_issues,
                              prioritized_only=cfg.sync.create == 'prioritized', results=results)
    items += goal_issue_desired(goals, sha, results)
    for record in cfg.sync.records:
        for path in sorted(record.glob.walk(cfg.ignore)):
            if record.kind == 'plan':
                items += plan_desired(load_plan(path, cfg.root), cfg.sync.label_prefix)
            elif record.kind == 'feature':
                items += feature_desired(load_feature(path, cfg.root), sha, cfg.sync.label_prefix)
    return items + _part_of_records(cfg)


def _part_of_records(cfg: Config) -> list[Desired]:
    record_issues: dict[tuple[str, str], set[int]] = {}
    children: set[tuple[str, int, str, str]] = set()
    by_path: dict[Path, set[str]] = {}
    for spec in cfg.schemas:
        if spec.format != 'frontmatter':
            continue
        try:
            namespaces = {a.ref.ns for a in _annotations(cfg.root, spec.schema)
                          if a.ref.edge == 'part_of' and a.steps == (('key', 'part_of'),)}
        except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError, RecursionError):
            namespaces = set()
        for pattern in spec.files:
            for path in pattern.walk(cfg.ignore):
                by_path.setdefault(path, set()).update(namespaces)
    for path, parent_namespaces in sorted(by_path.items()):
        try:
            data = load_data(path, frontmatter=True)
        except (OSError, ValueError, yaml.YAMLError):
            continue  # Schema validation reports unreadable records.
        if not isinstance(data, dict):
            continue
        name, number = data.get('name'), data.get('issue')
        if not isinstance(name, str) or type(number) is not int or number < 1:
            continue
        for rule in cfg.glossary:
            if rule.glob.matches(path):
                key = (normalize(rule.ns or DEFAULT_NS), normalize(name))
                record_issues.setdefault(key, set()).add(number)
        parents = data.get('part_of')
        if (len(parent_namespaces) == 1 and isinstance(parents, list)
                and len(parents) == 1 and isinstance(parents[0], str)):
            children.add((name, number, parents[0], next(iter(parent_namespaces))))
    items = []
    for name, number, parent, namespace in sorted(children):
        parent_numbers = record_issues.get((normalize(namespace), normalize(parent)), set())
        if len(parent_numbers) == 1:
            items.append(Desired('record', {'record': name}, '', '', '', 'open', listed=(number,),
                                 parent=parent, parent_issue=next(iter(parent_numbers))))
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
    if item.state != 'open' or not item.creates:
        return []
    if tracked and not (item.regression and all(issues.get(n, {}).get('state') == 'closed' for n in tracked)):
        return []
    labels = [item.label_prefix + item.priority] if _mirrors_priority(item) else []
    body = set_blocked_by(item.body, item.requires_prs)
    title = textwrap.shorten(f"Regression: {item.title}", 200) if tracked else item.title
    return [{'action': 'create', **item.ident, 'title': title, 'body': body,
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


# -- requires: blocked-by links and the generated "Blocked by" line ----------------

BLOCKED_BEGIN = '<!-- ubiq-blocked-by:begin -->'
BLOCKED_END = '<!-- ubiq-blocked-by:end -->'
BLOCKED_SPAN_RE = re.compile(f'{re.escape(BLOCKED_BEGIN)}.*?{re.escape(BLOCKED_END)}', re.DOTALL)


def set_blocked_by(body: str, prs: Sequence[int]) -> str:
    """`body` with the generated section naming `prs`; text outside the markers is untouched.

    GitHub rejects a pull request as a blocker, so a `pr: <n>` entry is only text. An
    existing section is replaced in place, or removed when `prs` is empty; a missing
    one is appended after the body.
    """
    if not prs:
        return BLOCKED_SPAN_RE.sub('', body, count=1)
    section = (f"{BLOCKED_BEGIN}\nBlocked by: {', '.join(f'#{n}' for n in prs)} "
               f"(pull requests, generated from `requires`)\n{BLOCKED_END}")
    if BLOCKED_SPAN_RE.search(body):
        return BLOCKED_SPAN_RE.sub(lambda _: section, body, count=1)
    return (body if body.endswith('\n') else body + '\n') + '\n' + section + '\n'


def fact_requires(item: Desired, tracked: Sequence[int], issues: Mapping[int, Issue]) -> list[Action]:
    """An open issue is blocked by exactly the issues its record `requires`.

    Missing links are `link` actions and extra links are `unlink` actions (drift). A
    record that sets no `requires` leaves links alone. A required record whose issue is
    not in the snapshot is a `warn`.
    """
    if item.requires is None or item.state != 'open':
        return []
    actions: list[Action] = []
    for n in tracked:
        issue = issues.get(n)
        if issue is None or issue.get('state') != 'open':
            continue
        have = {b['number']: b for b in issue.get('blocked_by') or []}
        want = [b for b in item.requires if b != n]
        for b in want:
            blocker = issues.get(b)
            if blocker is None or 'id' not in blocker:
                actions.append({'action': 'warn', **item.ident, 'issue': b,
                                'reason': 'required record has no issue'})
            elif b not in have:
                actions.append({'action': 'link', **item.ident, 'issue': n, 'blocked_by': b,
                                'issue_id': blocker['id']})
        actions += [{'action': 'unlink', **item.ident, 'issue': n, 'blocked_by': b, 'issue_id': link.get('id')}
                    for b, link in have.items() if b not in want]
    return actions


def fact_blocked_line(item: Desired, tracked: Sequence[int], issues: Mapping[int, Issue]) -> list[Action]:
    """An open issue's body holds the generated "Blocked by" section for the `pr:` entries."""
    if item.state != 'open':
        return []
    actions: list[Action] = []
    for n in tracked:
        issue = issues.get(n)
        if issue is None or issue.get('state') != 'open':
            continue
        body = issue.get('body') or ''
        new = set_blocked_by(body, item.requires_prs)
        if new != body:
            actions.append({'action': 'body', **item.ident, 'issue': n, 'body': new})
    return actions


# -- pull requests: the stack check and the derived `status: in review` label --------

STATUS_PREFIX = 'status: '
IN_REVIEW = STATUS_PREFIX + 'in review'
IN_PROGRESS = STATUS_PREFIX + 'in progress'
# `Closes #12`, `fixed: #12`, `Resolves owner/repo#12`: GitHub's closing keywords.
CLOSING_RE = re.compile(r'\b(?:close[sd]?|fix(?:e[sd]?)?|resolve[sd]?)\b:?[ \t]+(?:([\w.-]+/[\w.-]+))?#(\d+)',
                        re.IGNORECASE)

Pull = Mapping[str, Any]


def closing_numbers(body: str | None, repo: str = '') -> tuple[int, ...]:
    """Issue numbers that a pull request body closes in `repo` (a bare `#n` or `repo#n`)."""
    prose = _blank_inline(_blank_fences(body or ''))
    prose = HTML_COMMENT_RE.sub('', prose)
    prose = re.sub(r'(?m)^[ \t]{0,3}>[^\n]*', '', prose)
    return tuple(dict.fromkeys(int(m.group(2)) for m in CLOSING_RE.finditer(prose)
                               if not m.group(1) or m.group(1).casefold() == repo.casefold()))


def stack_of(item: Desired) -> Stack:
    return Stack(item.ident, item.prs, item.required_prs)


def stack_findings(stack: Stack, pulls: Mapping[int, Pull]) -> list[Action]:
    """A `stack` action when an open pull request of the record is based elsewhere than
    on the head branch of an open pull request of a record it requires.

    A record whose required records have no open pull request makes no claim (those
    merged, and the pull request targets the trunk). A pull request has one base, so with
    several required records the base may be any of their heads. Report only: the sync
    never retargets a pull request.
    """
    wanted = {r: pulls[r]['head'] for _, prs in stack.required for r in prs
              if r in pulls and r not in stack.prs}
    if not wanted:
        return []
    names = [name for name, prs in stack.required if any(r in wanted for r in prs)]
    return [{'action': 'stack', **stack.ident, 'pr': n, 'base': pulls[n]['base'],
             'expected': sorted(set(wanted.values())), 'requires': names,
             'reason': "pull request base is not the head branch of a required record's pull request"}
            for n in stack.prs if n in pulls and pulls[n]['base'] not in wanted.values()]


def fact_in_review(ident: Mapping[str, str], tracked: Sequence[int], issues: Mapping[int, Issue],
                   in_review: set[int]) -> list[Action]:
    """An open issue carries `status: in review` while an implementing pull request is open.

    The label is derived, so it is stored nowhere in the record. Adding it removes
    `status: in progress`; every other `status: ` label is left alone. A closed issue
    only loses the label. It is independent of `sync.label_prefix`.
    """
    actions: list[Action] = []
    for n in tracked:
        issue = issues.get(n)
        if issue is None:
            continue
        names = _label_names(issue)
        has = any(x.casefold() == IN_REVIEW for x in names)
        reviewing = issue.get('state') == 'open' and n in in_review
        if reviewing and not has:
            remove = [x for x in names if x.casefold() == IN_PROGRESS]
            actions.append({'action': 'label', **ident, 'issue': n, 'add': [IN_REVIEW], 'remove': remove})
        elif has and not reviewing:
            remove = [x for x in names if x.casefold() == IN_REVIEW]
            actions.append({'action': 'label', **ident, 'issue': n, 'add': [], 'remove': remove})
    return actions


def fact_stack(item: Desired, tracked: Sequence[int], issues: Mapping[int, Issue],
               pulls: Mapping[int, Pull]) -> list[Action]:
    return stack_findings(stack_of(item), pulls)


# Each pull-request fact: (item, tracked issue numbers, issues, open pulls by number) -> actions.
PR_FACTS: tuple[Callable[[Desired, Sequence[int], Mapping[int, Issue], Mapping[int, Pull]], list[Action]], ...] = (
    fact_stack,)

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


def unexpected_sub_issues(items: Sequence[tuple[Desired, list[int]]], issues: Mapping[int, Issue]) -> list[Action]:
    """Sub-issues on a parent issue that no record puts there: added by hand on GitHub.

    An issue that a record moves to another parent is not unexpected: its `link` replaces the old parent.
    """
    expected = {n for item, tracked in items if item.parent_issue for n in tracked}
    found: list[Action] = []
    for parent in sorted({d.parent_issue for d, _ in items if d.parent_issue in issues}):
        for n in issues[parent].get('sub_issues') or ():
            if n not in expected:
                found.append({'action': 'unlink', 'issue': n, 'parent': parent,
                              'sub_issue_id': issues.get(n, {}).get('id'),
                              'reason': 'sub-issue is not part_of the parent record'})
    return found


# Each mirrored fact: (item, tracked issue numbers, issues by number) -> actions.
FACTS: tuple[Callable[[Desired, Sequence[int], Mapping[int, Issue]], list[Action]], ...] = (
    fact_exists, fact_state, fact_priority, fact_part_of, fact_requires, fact_blocked_line)


def plan(desired: Iterable[Desired], snapshot: Sequence[Issue],
         pulls: Sequence[Pull] = (), stacks: Iterable[Stack] = (),
         records: Iterable[Tracked] = ()) -> list[Action]:
    """Return create, close, label, stack, noop, and warn actions for every desired item.

    `snapshot` holds dicts with `number`, `state`, `body`, and `user.login`. `pulls`
    holds the open pull requests (`number`, `head`, `base`, `closes`, optional
    `closing_intent` for stacked pull requests). `stacks` are further records whose
    pull requests are checked. `records` supplies explicit issue/PR pairings.
    Markers count only in issues opened by `BOT`. Issues that are neither listed
    by a record nor marked by `BOT` only receive derived status updates. A listed number that is not an
    existing issue (a pull request, a typo) gets a `warn`. Applying the result
    and planning again returns only `noop` actions.
    """
    by_number = {i['number']: i for i in snapshot}
    by_marker = _marked(snapshot)
    open_pulls = {p['number']: p for p in pulls}
    in_review = {n for pull in open_pulls.values()
                 for source in ('closes', 'closing_intent') for n in pull.get(source, ())}
    in_review.update(record.issue for record in records
                     if record.issue is not None and any(pr in open_pulls for pr in record.prs))
    items = []
    for item in desired:
        marked = [i['number'] for i in by_marker.get(item.marker, [])]
        tracked = list(dict.fromkeys([*item.listed, *marked]))
        items.append((item, tracked))
        if any(pr in open_pulls for pr in item.prs):
            in_review.update(tracked)
    actions: list[Action] = []
    tracked_issues: set[int] = set()
    for item, tracked in items:
        tracked_issues.update(tracked)
        actions += [{'action': 'warn', **item.ident, 'issue': n, 'reason': 'listed number is not an issue'}
                    for n in item.listed if n not in by_number]
        found = [a for fact in FACTS for a in fact(item, tracked, by_number)]
        found += fact_in_review(item.ident, tracked, by_number, in_review)
        found += [a for pr_fact in PR_FACTS for a in pr_fact(item, tracked, by_number, open_pulls)]
        actions += found
        if not found:
            reason = 'met; no open issue' if item.state == 'closed' else 'tracked'
            actions.append({'action': 'noop', **item.ident, 'reason': reason, 'issues': tracked})
    actions += unexpected_sub_issues(items, by_number)
    untracked = [n for n in by_number if n not in tracked_issues]
    if untracked:
        actions += fact_in_review({}, untracked, by_number, in_review)
    for stack in stacks:
        actions += stack_findings(stack, open_pulls)
    return actions


def derived_status(action: Action) -> bool:
    """A `label` action that only adds or removes the derived `status: in review`/`in progress`.

    Those labels follow the open pull requests, not the records, so they can lag a pull
    request that has just opened or closed until the sync applies.
    """
    changed = [x.casefold() for x in (*action.get('add', ()), *action.get('remove', ()))]
    return action['action'] == 'label' and bool(changed) and all(x in (IN_REVIEW, IN_PROGRESS) for x in changed)


def drift(actions: Iterable[Action], ignore_derived: bool = False) -> list[Action]:
    """The actions that differ from GitHub: everything but `noop`, and with
    `ignore_derived`, also not the derived status labels (`derived_status`)."""
    return [a for a in actions if a['action'] != 'noop' and not (ignore_derived and derived_status(a))]


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
            'link': self._link, 'unlink': self._unlink, 'body': self._body}

    def _call(self, method: str, url: str, payload: dict | None = None) -> Any:
        return self.transport(method, url, self.token, payload)

    def snapshot(self, parents: Iterable[int] = ()) -> list[Issue]:
        """Every issue (not pull request) in the repository, open or closed."""
        issues: list[Issue] = []
        page = 1
        while True:
            batch = self._call('GET', f'{self.base}?state=all&per_page=100&page={page}')
            issues += [self._with_links(i) for i in batch if 'pull_request' not in i]
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

    def pulls(self) -> list[Pull]:
        """Every open pull request, with separate closing and stacked-review references."""
        found: list[Pull] = []
        same_repo_heads: set[str] = set()
        pending_intent: list[tuple[dict[str, Any], tuple[int, ...]]] = []
        page = 1
        while True:
            batch = self._call('GET', f'https://api.github.com/repos/{self.repo}/pulls'
                                      f'?state=open&per_page=100&page={page}')
            for pull in batch:
                head = pull['head']['ref']
                base = pull['base']['ref']
                head_repo = (pull['head'].get('repo') or {}).get('full_name', '')
                if head_repo.casefold() == self.repo.casefold():
                    same_repo_heads.add(head)
                default = (pull['base'].get('repo') or {}).get('default_branch', base)
                references = closing_numbers(pull.get('body'), self.repo)
                entry: dict[str, Any] = {'number': pull['number'], 'head': head, 'base': base,
                                         'closes': references if base == default else ()}
                found.append(entry)
                if base != default and references:
                    pending_intent.append((entry, references))
            if len(batch) < 100:
                break
            page += 1
        for entry, references in pending_intent:
            if entry['base'] in same_repo_heads:
                entry['closing_intent'] = references
        return found

    def _with_links(self, issue: dict) -> dict:
        """`issue` plus `blocked_by`: the issues that block it, read only when it has any."""
        if not (issue.get('issue_dependencies_summary') or {}).get('blocked_by'):
            return issue
        links: list[Issue] = []
        page = 1
        while True:
            batch = self._call('GET', f"{self.base}/{issue['number']}/dependencies/blocked_by"
                                      f'?per_page=100&page={page}')
            links += batch
            if len(batch) < 100:
                return {**issue, 'blocked_by': [{'number': b['number'], 'id': b.get('id')} for b in links]}
            page += 1

    def _link(self, action: Action) -> None:
        if 'parent' in action:
            self._attach(action['parent'], action['sub_issue_id'])
            return
        self._call('POST', f"{self.base}/{action['issue']}/dependencies/blocked_by",
                   {'issue_id': action['issue_id']})

    def _unlink(self, action: Action) -> None:
        try:
            if 'parent' in action:
                self._call('DELETE', f"{self.base}/{action['parent']}/sub_issue",
                           {'sub_issue_id': action['sub_issue_id']})
                return
            self._call('DELETE', f"{self.base}/{action['issue']}/dependencies/blocked_by/{action['issue_id']}")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:  # already gone is the state we want
                raise

    def _body(self, action: Action) -> None:
        self._call('PATCH', f"{self.base}/{action['issue']}", {'body': action['body']})

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
    """A temporary directory holding `ubiq.yaml` and the records used by sync as they are at `rev`.

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
            patterns = [record.glob for record in cfg.sync.records]
            patterns.extend(pattern for spec in cfg.schemas if spec.format == 'frontmatter'
                            for pattern in spec.files)
            schemas = {spec.schema.partition('#')[0] for spec in cfg.schemas}
            listing = _git(root, rev, 'ls-tree', '-r', '-z', rev).decode().split('\0')
            for entry in filter(None, listing):
                meta, path = entry.split('\t', 1)
                if meta.startswith('100') and (path in schemas or any(pattern.matches(tmp / path) for pattern in patterns)):
                    fetch(path)
        yield tmp


def cmd_sync(args, transport: Transport = urllib_transport, pause: float = 1.0) -> int:
    """`ubiq sync github`: print the plan (default), `--apply` it, or `--check` for drift.

    `--ref REV` reads the records and `ubiq.yaml` at REV using the running
    version of ubiq. Pull request CI runs the base revision's version of ubiq
    from a worktree at that revision.
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
        records = tracked_records(cfg)
        results = None
        if getattr(args, 'results', None):
            from .scenarios import load_results
            try:
                results = load_results(Path(args.results), root)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                print(f'error: --results: {exc}', file=sys.stderr)
                return 2
        desired = desired_from_config(cfg, _head(root, getattr(args, 'ref', None)), records, results)
        snapshot = github.snapshot(d.parent_issue for d in desired if d.parent_issue)
        actions = plan(desired, snapshot, github.pulls(), record_stacks(records), records.values())
    except SyncError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    except OSError as exc:  # URLError and HTTPError are OSErrors.
        print(f'error: cannot read the records or the issues of {repo}: {exc}', file=sys.stderr)
        return 2
    if args.check:
        found = drift(actions, getattr(args, 'ignore_derived', False))
        _dump(found)
        if found:
            print(f'drift: {len(found)} difference(s) between the records and {repo}', file=sys.stderr)
        return 1 if found else 0
    if not args.apply:
        _dump(actions)
        return 0
    warnings = [a for a in actions if a['action'] in ('warn', 'stack')]
    done: list[Action] = []
    try:
        github.apply(actions, done)
    finally:
        _dump({'completed': done, 'warnings': warnings})
    return 1 if warnings else 0
