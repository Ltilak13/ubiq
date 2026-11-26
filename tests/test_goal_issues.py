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


def issue(number, state='open', marker=None):
    body = 'text' if marker is None else f'text\n<!-- ubiq-goal: demo-goal {marker} -->'
    return {'number': number, 'state': state, 'body': body}


def test_unmet_criterion_without_issue_is_created_with_verifiable_body():
    [action] = plan([goal(AC1=unmet())], [issue(9), issue(10, marker='AC2')])
    assert action['action'] == 'create'
    assert action['title'] == 'demo-goal AC1: Text of AC1.'
    for text in ('> 1. AC1: Text of AC1.', 'Needs review.', '`tests/test_a.py`: `def test_a(`',
                 '## Verify', 'ubiq check', 'python3 -m pytest tests/test_a.py',
                 '<!-- ubiq-goal: demo-goal AC1 -->'):
        assert text in action['body']


def test_listed_or_marked_issue_prevents_create_and_is_never_reopened():
    actions = plan([goal(AC1=unmet(issues=[5]), AC2=unmet())], [issue(7, 'closed', marker='AC2')])
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
