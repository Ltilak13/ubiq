"""Keep one GitHub issue per goal criterion: open while unmet, closed once met.

`plan()` decides from goal files and existing issues and has no side effects.
`main()` prints that plan (`--dry-run`, the default) or applies it through the
GitHub REST API with `GITHUB_TOKEN` (`--apply`). It only creates issues and
closes issues that carry this script's marker or that a criterion lists in
`issues:`. It never reopens an issue or edits a title.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from ubiq.schemas import load_data

ROOT = Path(__file__).resolve().parents[1]
MARKER = '<!-- ubiq-goal: {name} {ac} -->'
MARKER_RE = re.compile(r'<!-- ubiq-goal: (\S+) (AC\d+) -->')
CRITERION_RE = re.compile(r'^\d+\. (AC\d+): .+$', re.MULTILINE)


def load_goal(path):
    """Read a goal file into its name, repository path, criteria, and criterion lines."""
    path = Path(path).resolve()
    data = load_data(path, frontmatter=True)
    text = {m.group(1): m.group(0) for m in CRITERION_RE.finditer(path.read_text(encoding='utf-8'))}
    return {'name': data['name'], 'path': path.relative_to(ROOT).as_posix(),
            'criteria': data['criteria'], 'text': text}


def _body(goal, ac, criterion):
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
            "this issue.\n\n" + MARKER.format(name=goal['name'], ac=ac) + '\n')


def plan(goals, existing_issues, sha=''):
    """Return create, close, and noop actions for every criterion of every goal.

    `existing_issues` holds dicts with `number`, `state`, and `body`. Issues that
    neither carry a marker nor are listed in a criterion's `issues:` are ignored.
    """
    by_number = {i['number']: i for i in existing_issues}
    by_marker = {}
    for issue in existing_issues:
        for match in MARKER_RE.finditer(issue.get('body') or ''):
            by_marker.setdefault(match.groups(), []).append(issue)
    actions = []
    for goal in goals:
        for ac, criterion in goal['criteria'].items():
            head = {'goal': goal['name'], 'criterion': ac}
            listed = criterion.get('issues', [])
            marked = [i['number'] for i in by_marker.get((goal['name'], ac), [])]
            numbers = list(dict.fromkeys(listed + marked))
            if criterion['assessment'] == 'met':
                review = criterion['review']
                comment = (f"Goal `{goal['name']}` {ac} is `met` at {sha or 'the merged commit'}. "
                           f"Review by {review['by']}: {review['note']}")
                open_numbers = [n for n in numbers if by_number.get(n, {}).get('state') == 'open']
                actions += [{'action': 'close', **head, 'issue': n, 'comment': comment}
                            for n in open_numbers]
                if not open_numbers:
                    actions.append({'action': 'noop', **head, 'reason': 'met; no open issue',
                                    'issues': numbers})
            elif numbers:
                actions.append({'action': 'noop', **head, 'reason': 'tracked', 'issues': numbers})
            else:
                title = goal['text'].get(ac, ac).split(': ', 1)[-1]
                actions.append({'action': 'create', **head,
                                'title': f"{goal['name']} {ac}: {title}"[:200],
                                'body': _body(goal, ac, criterion)})
    return actions


def _api(method, url, token, payload=None):
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read() or b'null')


def fetch_issues(repo, token):
    """Return every issue (not pull request) in the repository, open or closed."""
    issues, page = [], 1
    while True:
        batch = _api('GET', f'https://api.github.com/repos/{repo}/issues'
                     f'?state=all&per_page=100&page={page}', token)
        issues += [i for i in batch if 'pull_request' not in i]
        if len(batch) < 100:
            return issues
        page += 1


def apply(actions, repo, token):
    base = f'https://api.github.com/repos/{repo}/issues'
    for action in actions:
        if action['action'] == 'create':
            issue = _api('POST', base, token, {'title': action['title'], 'body': action['body']})
            action['issue'] = issue['number']
        elif action['action'] == 'close':
            _api('POST', f"{base}/{action['issue']}/comments", token, {'body': action['comment']})
            _api('PATCH', f"{base}/{action['issue']}", token,
                 {'state': 'closed', 'state_reason': 'completed'})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('goals', nargs='*', type=Path,
                        help='goal files (default: docs/goals/*-goal.md)')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='print the plan as JSON (default)')
    mode.add_argument('--apply', action='store_true', help='create and close issues')
    parser.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY'),
                        help='owner/name (default: $GITHUB_REPOSITORY)')
    args = parser.parse_args(argv)
    if not args.repo:
        parser.error('--repo or GITHUB_REPOSITORY is required')
    token = os.environ.get('GITHUB_TOKEN', '')
    if args.apply and not token:
        parser.error('--apply needs GITHUB_TOKEN')
    sha = os.environ.get('GITHUB_SHA') or subprocess.run(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
    paths = args.goals or sorted((ROOT / 'docs/goals').glob('*-goal.md'))
    actions = plan([load_goal(p) for p in paths], fetch_issues(args.repo, token), sha)
    if args.apply:
        apply(actions, args.repo, token)
    json.dump(actions, sys.stdout, indent=2)
    print()


if __name__ == '__main__':
    main()
