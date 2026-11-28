"""Plan and apply the GitHub issue mirror without touching GitHub (`ubiq sync github`)."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from ubiq.cli import main
from ubiq.config import InvalidConfig, load_config
from ubiq.sync import (
    GitHub,
    SyncError,
    cmd_sync,
    desired_from_config,
    drift,
    goal_desired,
    load_goal,
    plan,
)

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = [{'feature': 'f', 'implementation': {'path': 'src/a.py', 'anchor': 'def a('},
            'check': {'path': 'tests/test_a.py', 'anchor': 'def test_a('}}]
REVIEW = {'by': 'Lucas', 'note': 'Assertions match the criterion.'}


def goal(**criteria):
    return {'name': 'demo-goal', 'path': 'docs/goals/demo-goal.md', 'criteria': criteria,
            'text': {ac: f'{n}. {ac}: Text of {ac}.' for n, ac in enumerate(criteria, 1)}}


def unmet(**extra):
    return {'assessment': 'partial', 'support': SUPPORT, 'gap': 'Needs review.', **extra}


def met(**extra):
    return {'assessment': 'met', 'support': SUPPORT, 'gap': 'None.', 'review': REVIEW, **extra}


def issue(number, state='open', marker=None, goal_name='demo-goal', login='github-actions[bot]'):
    body = 'text' if marker is None else f'text\n<!-- ubiq-goal: {goal_name} {marker} -->'
    return {'number': number, 'state': state, 'body': body, 'user': {'login': login}}


def run(goals, existing, sha=''):
    return plan([d for g in goals for d in goal_desired(g, sha)], existing)


def test_unmet_criterion_without_issue_is_created_with_verifiable_body():
    [action] = run([goal(AC1=unmet())], [issue(9), issue(10, marker='AC2')])
    assert action['action'] == 'create'
    assert action['title'] == 'demo-goal AC1: Text of AC1.'
    for text in ('> 1. AC1: Text of AC1.', 'Needs review.', '`tests/test_a.py`: `def test_a(`',
                 '## Verify', 'ubiq check', 'python3 -m pytest tests/test_a.py',
                 '<!-- ubiq-goal: demo-goal AC1 -->'):
        assert text in action['body']


def test_prioritized_only_creates_for_a_criterion_or_goal_with_a_priority():
    def created(g):
        items = goal_desired(g, prioritized_only=True)
        return [a['criterion'] for a in plan(items, []) if a['action'] == 'create']
    assert created(goal(AC1=unmet(), AC2=unmet(priority='P2'))) == ['AC2']
    assert created({**goal(AC1=unmet()), 'priority': 'P3'}) == ['AC1']
    [item] = goal_desired(goal(AC1=unmet(issues=[9])), prioritized_only=True)
    assert plan([item], [issue(9)])[0]['action'] == 'noop'


def test_a_criterion_assessed_elsewhere_is_not_mirrored():
    elsewhere = unmet(assessed_in={'goal': 'other-goal', 'criterion': 'AC1'})
    assert [d.ident['criterion'] for d in goal_desired(goal(AC1=unmet(), AC2=elsewhere))] == ['AC1']


def test_listed_or_marked_issue_prevents_create_and_is_never_reopened():
    existing = [issue(5, 'closed'), issue(7, 'closed', marker='AC2')]
    actions = run([goal(AC1=unmet(issues=[5]), AC2=unmet())], existing)
    assert [(a['action'], a['issues']) for a in actions] == [('noop', [5]), ('noop', [7])]


def test_met_criterion_closes_open_listed_and_marked_issues_only():
    existing = [issue(5), issue(6, 'closed'), issue(7, marker='AC1'), issue(8)]
    actions = run([goal(AC1=met(issues=[5, 6]))], existing, sha='abc123')
    assert [(a['action'], a['issue']) for a in actions] == [('close', 5), ('close', 7)]
    for text in ('demo-goal', 'AC1', 'Lucas', 'Assertions match the criterion.', 'abc123'):
        assert text in actions[0]['comment']


def test_met_criterion_with_nothing_open_is_noop():
    [action] = run([goal(AC1=met(issues=[5]))], [issue(5, 'closed')])
    assert action['action'] == 'noop'


def test_met_criterion_without_any_issue_is_noop_not_create():
    [action] = run([goal(AC1=met())], [])
    assert (action['action'], action['issues']) == ('noop', [])


def test_marker_from_untrusted_author_is_ignored_but_listed_issue_is_trusted():
    spoofed = [issue(7, 'closed', marker='AC1', login='someone'), issue(8, login='someone')]
    actions = run([goal(AC1=unmet(), AC2=unmet(issues=[8]))], spoofed)
    assert [a['action'] for a in actions] == ['create', 'noop']


def test_marker_matches_goal_name_and_exact_label():
    other = {**goal(AC1=unmet()), 'name': 'other-goal'}
    existing = [issue(7, marker='AC1', goal_name='other-goal'), issue(8, marker='AC10')]
    actions = run([goal(AC1=unmet(), AC10=unmet()), other], existing)
    assert [(a['goal'], a['criterion'], a['action']) for a in actions] == [
        ('demo-goal', 'AC1', 'create'), ('demo-goal', 'AC10', 'noop'), ('other-goal', 'AC1', 'noop')]


def test_unknown_listed_number_warns():
    actions = run([goal(AC1=unmet(issues=[5, 99]))], [issue(5)])
    assert [(a['action'], a.get('issue')) for a in actions] == [('warn', 99), ('noop', None)]


def test_planning_is_idempotent_after_its_own_actions():
    goals = [goal(AC1=unmet(), AC2=met(issues=[5]), AC3=unmet(issues=[6]))]
    first = run(goals, [issue(5), issue(6)])
    assert [a['action'] for a in first] == ['create', 'close', 'noop']
    # The state GitHub holds once the actions ran: the new issue carries its marker, the old one is closed.
    after = [issue(5, 'closed'), issue(6), issue(100, marker='AC1')]
    assert {a['action'] for a in run(goals, after)} == {'noop'}
    assert drift(run(goals, after)) == []


def test_drift_is_every_action_but_noop():
    actions = run([goal(AC1=unmet(), AC2=met(issues=[5]), AC3=unmet(issues=[9]))], [issue(5), issue(6)])
    assert [a['action'] for a in drift(actions)] == ['create', 'close', 'warn']
    assert drift(run([goal(AC1=unmet(issues=[5]))], [issue(5)])) == []


def test_hand_closed_issue_of_an_unmet_criterion_is_not_drift():
    # The sync never reopens, so a closed issue does not differ from what it would do.
    assert drift(run([goal(AC1=unmet(issues=[5]))], [issue(5, 'closed')])) == []


def test_wrapped_criterion_is_read_whole(tmp_path):
    path = tmp_path / 'demo-goal.md'
    path.write_text('---\nname: demo-goal\nstatus: proposed\ncriteria:\n  AC1:\n'
                    '    assessment: unassessed\n    support: []\n    gap: g\n---\n\n'
                    '1. AC1: First line\n   continues here.\n2. AC2: Next.\n')
    assert load_goal(path, tmp_path)['text']['AC1'] == '1. AC1: First line continues here.'


def test_unreadable_goal_is_a_sync_error(tmp_path):
    path = tmp_path / 'broken-goal.md'
    path.write_text('no frontmatter\n')
    with pytest.raises(SyncError, match='broken-goal.md'):
        load_goal(path, tmp_path)


def test_this_repository_creates_only_for_untracked_criteria():
    actions = plan(desired_from_config(load_config(ROOT)), [])
    created = {(a['goal'], a['criterion']) for a in actions if a['action'] == 'create' and 'goal' in a}
    loaded = [load_goal(p, ROOT) for p in sorted((ROOT / 'docs/goals').glob('*-goal.md'))]
    untracked = {(g['name'], ac) for g in loaded for ac, c in g['criteria'].items()
                 if c.get('assessment') != 'met' and not c.get('issues') and 'assessed_in' not in c
                 and (c.get('priority') or g['priority'])}
    assert created == untracked
    assert not [a for a in actions if a['action'] == 'close' and 'goal' in a]


# -- adapter, through a fake transport ---------------------------------------------

class Fake:
    """Records every call and answers from a dict keyed by (method, path after /issues)."""

    def __init__(self, answers=None):
        self.calls, self.answers = [], answers or {}

    def __call__(self, method, url, token, payload=None):
        key = (method, url.split('/issues', 1)[-1])
        self.calls.append((*key, token, payload))
        return self.answers.get(key, {})


def test_snapshot_pages_and_drops_pull_requests():
    first = [{'number': n, **({'pull_request': {}} if n % 2 else {})} for n in range(100)]
    fake = Fake({('GET', '?state=all&per_page=100&page=1'): first,
                 ('GET', '?state=all&per_page=100&page=2'): [{'number': 100}]})
    numbers = [i['number'] for i in GitHub('o/r', 't', fake, 0).snapshot()]
    assert numbers == list(range(0, 101, 2))
    assert [c[1] for c in fake.calls] == ['?state=all&per_page=100&page=1',
                                           '?state=all&per_page=100&page=2']
    assert {c[2] for c in fake.calls} == {'t'}


def test_apply_closes_before_commenting_and_skips_a_repeated_comment():
    [close] = run([goal(AC1=met(issues=[5]))], [issue(5)], sha='abc123')
    for repeated, expected in ((False, ['PATCH /5', 'GET /5/comments?per_page=100', 'POST /5/comments']),
                               (True, ['PATCH /5', 'GET /5/comments?per_page=100'])):
        fake = Fake({('GET', '/5/comments?per_page=100'): [{'body': close['comment']}] if repeated else []})
        done = []
        GitHub('o/r', 't', fake, 0).apply([close], done)
        assert [f'{m} {u}' for m, u, *_ in fake.calls] == expected
        assert done == [close]


def test_apply_creates_an_issue_and_skips_noop_and_warn():
    [create] = run([goal(AC1=unmet())], [])
    fake = Fake({('POST', ''): {'number': 42}})
    done = []
    GitHub('o/r', 't', fake, 0).apply([create, {'action': 'noop'}, {'action': 'warn'}], done)
    assert [(m, u) for m, u, *_ in fake.calls] == [('POST', '')]
    assert fake.calls[0][3] == {'title': create['title'], 'body': create['body']}
    assert done == [create] and create['issue'] == 42


# -- command -----------------------------------------------------------------------

READ = ('GET', '?state=all&per_page=100&page=1')
RECORDS = '    - {glob: "goals/*-goal.md", kind: goal}\n'


def write_repo(root, sync=f'sync:\n  repo: o/r\n  records:\n{RECORDS}', issues=''):
    (root / 'goals').mkdir()
    (root / 'goals/demo-goal.md').write_text(
        '---\nname: demo-goal\nstatus: proposed\ncriteria:\n  AC1:\n    assessment: unassessed\n'
        f'    support: []\n    gap: g\n{issues}---\n\n1. AC1: First.\n')
    (root / 'ubiq.yaml').write_text(sync)
    return root


def flags(root, **extra):
    base = {'root': str(root), 'repo': None, 'apply': False, 'check': False, 'dry_run': False}
    return SimpleNamespace(**{**base, **extra})


def test_dry_run_prints_the_plan_and_never_writes(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('GITHUB_TOKEN', 't')
    fake = Fake({READ: []})
    assert cmd_sync(flags(write_repo(tmp_path)), fake, 0) == 0
    [action] = json.loads(capsys.readouterr().out)
    assert action['action'] == 'create'
    assert {c[0] for c in fake.calls} == {'GET'}


def test_check_exits_nonzero_on_drift_and_zero_when_in_sync(tmp_path, monkeypatch, capsys):
    root = write_repo(tmp_path)
    monkeypatch.setenv('GITHUB_TOKEN', 't')
    assert cmd_sync(flags(root, check=True), Fake({READ: []}), 0) == 1
    out = capsys.readouterr()
    assert json.loads(out.out)[0]['action'] == 'create'
    assert 'drift: 1 difference' in out.err
    assert cmd_sync(flags(root, check=True), Fake({READ: [issue(3, marker='AC1')]}), 0) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_check_without_a_token_skips_with_a_message(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)
    fake = Fake()
    assert cmd_sync(flags(write_repo(tmp_path), check=True), fake, 0) == 0
    assert 'skipped: --check needs GITHUB_TOKEN' in capsys.readouterr().err
    assert not fake.calls


def test_apply_needs_a_token(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)
    assert cmd_sync(flags(write_repo(tmp_path), apply=True), Fake(), 0) == 2
    assert 'GITHUB_TOKEN' in capsys.readouterr().err


def test_repository_comes_from_the_flag_then_config_then_environment(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('GITHUB_REPOSITORY', 'env/repo')
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)
    urls = []

    def spy(method, url, token, payload=None):
        urls.append(url.split('/issues')[0].split('/pulls')[0].rsplit('repos/', 1)[-1])
        return []
    (tmp_path / 'a').mkdir()
    (tmp_path / 'b').mkdir()
    configured = write_repo(tmp_path / 'a')
    bare = write_repo(tmp_path / 'b', f'sync:\n  records:\n{RECORDS}')
    cmd_sync(flags(configured), spy, 0)
    cmd_sync(flags(configured, repo='flag/repo'), spy, 0)
    cmd_sync(flags(bare), spy, 0)
    assert urls == ['o/r', 'o/r', 'flag/repo', 'flag/repo', 'env/repo', 'env/repo']  # issues, pulls
    capsys.readouterr()
    monkeypatch.delenv('GITHUB_REPOSITORY')
    assert cmd_sync(flags(bare), spy, 0) == 2
    assert 'sync.repo' in capsys.readouterr().err


def test_a_failed_read_is_reported_not_raised(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)

    def refuse(method, url, token, payload=None):
        raise OSError('HTTP Error 403: rate limit exceeded')
    assert cmd_sync(flags(write_repo(tmp_path)), refuse, 0) == 2
    assert 'rate limit' in capsys.readouterr().err


def test_an_unreadable_record_is_reported(tmp_path, monkeypatch, capsys):
    root = write_repo(tmp_path)
    (root / 'goals/bad-goal.md').write_text('no frontmatter\n')
    monkeypatch.setenv('GITHUB_TOKEN', 't')
    assert cmd_sync(flags(root), Fake({READ: []}), 0) == 2
    assert 'bad-goal.md' in capsys.readouterr().err


def test_unconfigured_repository_gets_guidance(tmp_path, capsys):
    (tmp_path / 'ubiq.yaml').write_text('docs: ["*.md"]\n')
    assert main(['sync', 'github', '--root', str(tmp_path)]) == 2
    assert 'sync:' in capsys.readouterr().err


def test_apply_exits_nonzero_on_a_warning_after_the_other_actions(tmp_path, monkeypatch, capsys):
    root = write_repo(tmp_path, issues='    issues: [99]\n')
    monkeypatch.setenv('GITHUB_TOKEN', 't')
    assert cmd_sync(flags(root, apply=True), Fake({READ: []}), 0) == 1
    assert json.loads(capsys.readouterr().out)['warnings'][0]['issue'] == 99


@pytest.mark.parametrize('text, message', [
    ('sync: []\n', 'expected a mapping'),
    ('sync: {records: []}\n', r'sync\.records'),
    ('sync: {records: [{glob: "a/*.md", kind: nope}]}\n', r'sync\.records\[0\]\.kind'),
    ('sync: {repo: nope, records: [{glob: "a", kind: goal}]}\n', r'sync\.repo'),
    ('sync: {records: [{glob: "/a", kind: goal}]}\n', 'repository-relative'),
    ('sync: {repos: x, records: [{glob: "a", kind: goal}]}\n', 'did you mean repo'),
])
def test_sync_section_is_validated(tmp_path, text, message):
    (tmp_path / 'ubiq.yaml').write_text(text)
    with pytest.raises(InvalidConfig, match=message):
        load_config(tmp_path)


def test_old_script_forwards_to_the_command():
    done = subprocess.run([sys.executable, str(ROOT / 'scripts/goal_issues.py'), '--check'],
                          capture_output=True, text=True, check=False,
                          env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT / 'src')})
    # No GITHUB_TOKEN in this environment, so check mode skips and says so.
    assert done.returncode == 0 and 'skipped' in done.stderr


def test_pull_request_that_meets_a_criterion_is_pending_not_drift(tmp_path, monkeypatch, capsys):
    root = write_repo(tmp_path, issues='    issues: [5]\n')
    monkeypatch.setenv('GITHUB_TOKEN', 't')

    def vcs(*cmd):
        subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *cmd], cwd=root,
                       check=True, capture_output=True)
    vcs('init', '-q', '-b', 'main')
    vcs('add', '.')
    vcs('commit', '-q', '-m', 'base')
    vcs('checkout', '-q', '-b', 'pr')
    (root / 'goals/demo-goal.md').write_text(
        '---\nname: demo-goal\nstatus: proposed\ncriteria:\n  AC1:\n    assessment: met\n'
        '    support: []\n    gap: g\n    issues: [5]\n    review: {by: Lucas, note: checked}\n'
        '---\n\n1. AC1: First.\n')
    vcs('commit', '-qam', 'meet AC1')
    remote = Fake({READ: [issue(5)]})
    # Against the base the mirror matches: no drift, so the check passes.
    assert cmd_sync(flags(root, check=True, ref='main'), remote, 0) == 0
    assert json.loads(capsys.readouterr().out) == []
    # The head's plan is the preview: closing issue 5 is pending on merge.
    assert cmd_sync(flags(root), remote, 0) == 0
    assert [(a['action'], a['issue']) for a in json.loads(capsys.readouterr().out)] == [('close', 5)]
    # The head's own check would call that drift, which is why the base is checked.
    assert cmd_sync(flags(root, check=True), remote, 0) == 1
    capsys.readouterr()
    assert cmd_sync(flags(root, check=True, ref='nope'), remote, 0) == 2
    assert 'nope' in capsys.readouterr().err


def test_pull_request_workflow_checks_base_code_and_previews_head_code(tmp_path):
    workflow = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())['jobs']
    preview = workflow['sync-preview']
    prepare, check = workflow['sync-check']['steps'][-2:]
    assert preview['steps'][0]['with']['ref'] == '${{ github.event.pull_request.head.sha }}'
    assert prepare['env']['BASE_SHA'] == '${{ github.event.pull_request.base.sha }}'

    root = tmp_path / 'repo'
    root.mkdir()
    write_repo(root)
    shutil.copytree(ROOT / 'src/ubiq', root / 'src/ubiq', ignore=shutil.ignore_patterns('__pycache__'))

    def git(*args):
        return subprocess.check_output(
            ['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *args],
            cwd=root, text=True,
        ).strip()

    git('init', '-q', '-b', 'main')
    git('commit', '-q', '--allow-empty', '-m', 'pre-sync')
    before_sync = git('rev-parse', 'HEAD')
    git('add', '.')
    git('commit', '-q', '-m', 'base')
    base_sha = git('rev-parse', 'HEAD')
    with (root / 'src/ubiq/sync.py').open('a') as planner:
        planner.write("""

def extra_label(item, tracked, issues):
    return [{'action': 'label', **item.ident, 'issue': number} for number in tracked]

FACTS = (*FACTS, extra_label)
""")
    git('commit', '-qam', 'add a mirrored fact')

    stubs = tmp_path / 'stubs'
    stubs.mkdir()
    (stubs / 'sitecustomize.py').write_text("""
import io
import os
import urllib.request

def snapshot(request, timeout):
    assert request.get_method() == 'GET'
    if '/pulls?' in request.full_url:
        return io.BytesIO(b'[]')
    assert '/issues?' in request.full_url
    return io.BytesIO(os.environ['ISSUE_SNAPSHOT'].encode())

urllib.request.urlopen = snapshot
""")
    python = stubs / 'python'
    python.write_text("""#!/usr/bin/env bash
if [[ "$1" == "-m" && "$2" == "pip" ]]; then
  printf '%s\n' "$PWD" >> "$INSTALL_LOG"
  exit 0
fi
PYTHONPATH="$PYTHONPATH:$STUBS" exec "$TEST_PYTHON" "$@"
""")
    python.chmod(0o755)
    summary = tmp_path / 'summary.md'
    install_log = tmp_path / 'install.txt'
    env = {
        **os.environ,
        'FENCE': '```',
        'GITHUB_SHA': 'synthetic-merge',
        'GITHUB_STEP_SUMMARY': str(summary),
        'GITHUB_TOKEN': 'test',
        'HEAD_SHA': git('rev-parse', 'HEAD'),
        'INSTALL_LOG': str(install_log),
        'ISSUE_SNAPSHOT': json.dumps([issue(5, marker='AC1')]),
        'PATH': f"{stubs}{os.pathsep}{os.environ['PATH']}",
        'PYTHONPATH': str(root / 'src'),
        'STUBS': str(stubs),
        'TEST_PYTHON': sys.executable,
    }

    def step(script, cwd, env):
        return subprocess.run(['bash', '-eo', 'pipefail', '-c', script],
                              cwd=cwd, env=env, text=True, capture_output=True, check=False)

    result = step(preview['steps'][-1]['run'], root, env)
    assert result.returncode == 0, result.stderr
    pending = json.loads(summary.read_text().split('```json\n', 1)[1].split('```', 1)[0])
    assert [(action['action'], action['issue']) for action in pending] == [('label', 5)]

    runner_temp = tmp_path / 'runner'
    runner_temp.mkdir()
    base_tree = runner_temp / 'ubiq-sync-base'
    env.update(BASE_SHA=base_sha, RUNNER_TEMP=str(runner_temp))
    prepared = step(prepare['run'], root, env)
    assert prepared.returncode == 0, prepared.stderr
    assert install_log.read_text().splitlines() == [str(base_tree)]

    result = step(check['run'], base_tree, env)
    assert result.returncode == 0 and json.loads(result.stdout) == [], result
    result = step(check['run'], base_tree, {**env, 'ISSUE_SNAPSHOT': '[]'})
    assert result.returncode == 1 and json.loads(result.stdout)[0]['action'] == 'create', result

    runner_temp = tmp_path / 'before-sync'
    runner_temp.mkdir()
    env.update(BASE_SHA=before_sync, RUNNER_TEMP=str(runner_temp))
    prepared = step(prepare['run'], root, env)
    assert prepared.returncode == 0, prepared.stderr
    result = step(check['run'], runner_temp / 'ubiq-sync-base', env)
    assert result.returncode == 0 and 'does not mirror GitHub issues' in result.stdout, result


def test_ref_reads_only_the_records_and_ignores_symlinks(tmp_path, monkeypatch, capsys):
    root = write_repo(tmp_path)
    monkeypatch.setenv('GITHUB_TOKEN', 't')
    outside = tmp_path.parent / f'{tmp_path.name}-outside'
    outside.mkdir()
    (root / 'goals/linked-goal.md').symlink_to(outside / 'goal.md')  # absolute, dangling, matches the glob
    (root / '.agents').mkdir()
    (root / '.agents/skill').symlink_to(outside)  # absolute, escapes the checkout

    def vcs(*cmd):
        subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *cmd], cwd=root,
                       check=True, capture_output=True)
    vcs('init', '-q', '-b', 'main')
    vcs('add', '.')
    vcs('commit', '-q', '-m', 'base')
    assert cmd_sync(flags(root, check=True, ref='main'), Fake({READ: [issue(3, marker='AC1')]}), 0) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_ref_without_a_sync_section_skips(tmp_path, monkeypatch, capsys):
    root = write_repo(tmp_path, sync='docs: ["*.md"]\n')
    monkeypatch.setenv('GITHUB_TOKEN', 't')
    (tmp_path / 'bare').mkdir()

    def vcs(*cmd):
        subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *cmd], cwd=root,
                       check=True, capture_output=True)
    vcs('init', '-q', '-b', 'main')
    vcs('add', '.')
    vcs('commit', '-q', '-m', 'base')
    vcs('rm', '-q', 'ubiq.yaml')
    vcs('commit', '-q', '-m', 'no config')
    remote = Fake()
    # A base that predates the sync section (a stacked pull request) mirrors nothing: no drift.
    assert cmd_sync(flags(root, check=True, ref='main~1'), remote, 0) == 0
    assert 'has no sync section' in capsys.readouterr().err
    assert cmd_sync(flags(root, check=True, ref='main'), remote, 0) == 0
    assert 'has no sync section' in capsys.readouterr().err and not remote.calls


def test_sync_create_setting_is_validated(tmp_path):
    from ubiq.config import InvalidConfig
    write_repo(tmp_path, sync=f'sync:\n  repo: o/r\n  create: prioritized\n  records:\n{RECORDS}')
    assert load_config(tmp_path).sync.create == 'prioritized'
    (tmp_path / 'ubiq.yaml').write_text(f'sync:\n  repo: o/r\n  create: sometimes\n  records:\n{RECORDS}')
    with pytest.raises(InvalidConfig, match='sync.create'):
        load_config(tmp_path)


def test_ignore_derived_drops_only_the_derived_status_labels():
    from ubiq.sync import drift
    review = {'action': 'label', 'issue': 1, 'add': ['status: in review'], 'remove': ['status: in progress']}
    unreview = {'action': 'label', 'issue': 2, 'add': [], 'remove': ['Status: In Review']}
    priority = {'action': 'label', 'issue': 3, 'add': ['priority: P1'], 'remove': []}
    mixed = {'action': 'label', 'issue': 4, 'add': ['status: in review', 'priority: P2'], 'remove': []}
    create = {'action': 'create', 'title': 't'}
    noop = {'action': 'noop'}
    actions = [review, unreview, priority, mixed, create, noop]
    assert drift(actions) == [review, unreview, priority, mixed, create]
    assert drift(actions, ignore_derived=True) == [priority, mixed, create]


def test_check_ignore_derived_passes_when_only_in_review_labels_lag(tmp_path, monkeypatch, capsys):
    root = write_repo(tmp_path, issues='    issues: [7]\n')
    snapshot = [{'number': 7, 'state': 'open', 'body': '', 'labels': [], 'user': {'login': 'x'}}]
    pulls = [{'number': 9, 'head': {'ref': 'h', 'repo': {'full_name': 'o/r'}},
              'base': {'ref': 'main', 'repo': {'default_branch': 'main'}}, 'body': 'Closes #7'}]

    def transport(method, url, token, payload=None):
        if '/pulls' in url:
            return pulls if 'page=1' in url else []
        if '/issues?' in url:
            return snapshot if 'page=1' in url else []
        return {}
    monkeypatch.setenv('GITHUB_TOKEN', 't')
    from ubiq.sync import cmd_sync
    assert cmd_sync(flags(root, check=True), transport, pause=0) == 1
    capsys.readouterr()
    assert cmd_sync(flags(root, check=True, ignore_derived=True), transport, pause=0) == 0
