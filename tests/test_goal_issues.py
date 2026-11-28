"""Plan goal issue actions without touching GitHub."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('goal_issues', ROOT / 'scripts/goal_issues.py')
goal_issues = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(goal_issues)
plan = goal_issues.plan

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


def test_unmet_criterion_without_issue_is_created_with_verifiable_body():
    [action] = plan([goal(AC1=unmet())], [issue(9), issue(10, marker='AC2')])
    assert action['action'] == 'create'
    assert action['title'] == 'demo-goal AC1: Text of AC1.'
    for text in ('> 1. AC1: Text of AC1.', 'Needs review.', '`tests/test_a.py`: `def test_a(`',
                 '## Verify', 'ubiq check', 'python3 -m pytest tests/test_a.py',
                 '<!-- ubiq-goal: demo-goal AC1 -->'):
        assert text in action['body']


def test_listed_or_marked_issue_prevents_create_and_is_never_reopened():
    existing = [issue(5, 'closed'), issue(7, 'closed', marker='AC2')]
    actions = plan([goal(AC1=unmet(issues=[5]), AC2=unmet())], existing)
    assert [(a['action'], a['issues']) for a in actions] == [('noop', [5]), ('noop', [7])]


def test_met_criterion_closes_open_listed_and_marked_issues_only():
    existing = [issue(5), issue(6, 'closed'), issue(7, marker='AC1'), issue(8)]
    actions = plan([goal(AC1=met(issues=[5, 6]))], existing, sha='abc123')
    assert [(a['action'], a['issue']) for a in actions] == [('close', 5), ('close', 7)]
    for text in ('demo-goal', 'AC1', 'Lucas', 'Assertions match the criterion.', 'abc123'):
        assert text in actions[0]['comment']


def test_met_criterion_with_nothing_open_is_noop():
    [action] = plan([goal(AC1=met(issues=[5]))], [issue(5, 'closed')])
    assert action['action'] == 'noop'


def test_no_code_spec_goal_creates_only_for_untracked_criteria():
    loaded = goal_issues.load_goal(ROOT / 'docs/goals/no-code-spec-goal.md')
    actions = plan([loaded], [])
    created = {a['criterion'] for a in actions if a['action'] == 'create'}
    assert created == {ac for ac, c in loaded['criteria'].items() if not c.get('issues')}
    assert not [a for a in actions if a['action'] == 'close']


def test_marker_from_untrusted_author_is_ignored_but_listed_issue_is_trusted():
    spoofed = [issue(7, 'closed', marker='AC1', login='someone'), issue(8, login='someone')]
    actions = plan([goal(AC1=unmet(), AC2=unmet(issues=[8]))], spoofed)
    assert [a['action'] for a in actions] == ['create', 'noop']


def test_marker_matches_goal_name_and_exact_label():
    other = {**goal(AC1=unmet()), 'name': 'other-goal'}
    existing = [issue(7, marker='AC1', goal_name='other-goal'), issue(8, marker='AC10')]
    actions = plan([goal(AC1=unmet(), AC10=unmet()), other], existing)
    assert [(a['goal'], a['criterion'], a['action']) for a in actions] == [
        ('demo-goal', 'AC1', 'create'), ('demo-goal', 'AC10', 'noop'), ('other-goal', 'AC1', 'noop')]


def test_unknown_listed_number_warns():
    actions = plan([goal(AC1=unmet(issues=[5, 99]))], [issue(5)])
    assert [(a['action'], a.get('issue')) for a in actions] == [('warn', 99), ('noop', None)]


def test_wrapped_criterion_is_read_whole(tmp_path, monkeypatch):
    monkeypatch.setattr(goal_issues, 'ROOT', tmp_path)
    path = tmp_path / 'demo-goal.md'
    path.write_text('---\nname: demo-goal\nstatus: proposed\ncriteria:\n  AC1:\n'
                    '    assessment: unassessed\n    support: []\n    gap: g\n---\n\n'
                    '1. AC1: First line\n   continues here.\n2. AC2: Next.\n')
    assert goal_issues.load_goal(path)['text']['AC1'] == '1. AC1: First line continues here.'


def test_fetch_issues_pages_and_drops_pull_requests(monkeypatch):
    first = [{'number': n, **({'pull_request': {}} if n % 2 else {})} for n in range(100)]
    pages = iter([first, [{'number': 100}]])
    monkeypatch.setattr(goal_issues, '_api', lambda *args, **kwargs: next(pages))
    numbers = [i['number'] for i in goal_issues.fetch_issues('o/r', '')]
    assert numbers == list(range(0, 101, 2))


def test_apply_closes_before_commenting_and_skips_a_repeated_comment(monkeypatch):
    [close] = plan([goal(AC1=met(issues=[5]))], [issue(5)], sha='abc123')
    calls = []

    def fake_api(method, url, token, payload=None):
        calls.append((method, url.rsplit('/issues', 1)[-1]))
        return [{'body': close['comment']}] if method == 'GET' and repeated else {}
    monkeypatch.setattr(goal_issues, '_api', fake_api)
    for repeated, expected in ((False, ['PATCH /5', 'GET /5/comments?per_page=100', 'POST /5/comments']),
                               (True, ['PATCH /5', 'GET /5/comments?per_page=100'])):
        calls.clear()
        done = []
        goal_issues.apply([close], 'o/r', 't', done, pause=0)
        assert [f'{m} {u}' for m, u in calls] == expected
        assert done == [close]
