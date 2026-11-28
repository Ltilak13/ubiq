"""Keep goal evidence traceable without claiming semantic corroboration."""
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from ubiq.schemas import load_data, load_schema

ROOT = Path(__file__).resolve().parents[1]
GOALS = (
    "domain-schema", "composable-knowledge", "human-agent-readability",
    "checkable-contracts-evidence", "safe-adoption-evolution", "no-code-spec",
    "code-records",
)
SCHEMA = load_schema(ROOT, ROOT / '.ubiq/schemas/goal.json')


@pytest.mark.parametrize('name', GOALS)
def test_goal_evidence_locations_and_criteria(name):
    goal = ROOT / 'docs/goals' / f'{name}-goal.md'
    data = load_data(goal, frontmatter=True)
    Draft202012Validator(SCHEMA).validate(data)
    labels = re.findall(r'^\d+\. (AC\d+):', goal.read_text(), re.MULTILINE)
    assert len(labels) == len(set(labels)), f'{goal}: duplicate acceptance label'
    assert set(labels) == set(data['criteria']), f'{goal}: criteria drift'
    for criterion in data['criteria'].values():
        for support in criterion.get('support', []):
            for kind in ('implementation', 'check'):
                evidence = support[kind]
                path = (ROOT / evidence['path']).resolve()
                assert path.is_relative_to(ROOT), f'{goal}: external evidence'
                assert path.is_file(), f'{goal}: missing {path}'
                assert evidence['anchor'] in path.read_text(), f'{goal}: stale {path}'


@pytest.mark.parametrize(('field', 'value'), [
    ('assessment', 'verified'),
    ('support', []),
    ('gap', ''),
])
def test_partial_assessment_requires_provisional_evidence(field, value):
    data = load_data(ROOT / 'docs/goals/domain-schema-goal.md', frontmatter=True)
    Draft202012Validator(SCHEMA).validate(data)
    data['criteria']['AC2'][field] = value
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(data)


REVIEW = {'by': 'Lucas', 'note': 'Checked.', 'at': 'a' * 40, 'date': '2026-11-28'}
MET = {'assessment': 'met', 'gap': 'None remaining.', 'review': REVIEW,
       'support': [{'feature': 'f', 'implementation': {'path': 'a', 'anchor': 'x'},
                    'check': {'path': 'b', 'anchor': 'y'}}]}


def _criterion(**fields):
    return {'name': 'g', 'status': 'proposed', 'criteria': {'AC1': fields}}


def test_met_assessment_with_review_and_adopted_issues_is_valid():
    Draft202012Validator(SCHEMA).validate(_criterion(**MET, issues=[3, 4]))


@pytest.mark.parametrize('fields', [
    {**MET, 'support': []},
    {key: value for key, value in MET.items() if key != 'review'},
    {**MET, 'review': {**REVIEW, 'note': ' '}},
    {**MET, 'review': {'by': 'Lucas'}},
    {**MET, 'review': {k: v for k, v in REVIEW.items() if k != 'at'}},
    {**MET, 'review': {**REVIEW, 'at': 'main'}},
    {**MET, 'review': {**REVIEW, 'date': 'today'}},
    {**MET, 'support': [{**MET['support'][0], 'feature': 'Not A Feature Name'}]},
    {'assessment': 'unassessed', 'support': [], 'gap': 'g', 'review': MET['review']},
    {**MET, 'issues': [3, 3]},
    {**MET, 'issues': [0]},
    {**MET, 'issues': ['#3']},
])
def test_met_assessment_requires_support_and_review(fields):
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(_criterion(**fields))


ASSESSED_IN = {'assessment': 'unassessed', 'support': [], 'gap': 'Owned elsewhere.',
               'assessed_in': {'goal': 'other-goal', 'criterion': 'AC2'}}


def test_a_criterion_assessed_elsewhere_carries_no_assessment_or_evidence_of_its_own():
    Draft202012Validator(SCHEMA).validate(_criterion(**ASSESSED_IN))
    for bad in ({**ASSESSED_IN, 'assessment': 'partial', 'support': MET['support']},
                {**ASSESSED_IN, 'support': MET['support']},
                {**ASSESSED_IN, 'assessed_in': {'goal': 'other-goal', 'criterion': '2'}}):
        with pytest.raises(ValidationError):
            Draft202012Validator(SCHEMA).validate(_criterion(**bad))


def test_assessed_in_names_an_existing_criterion_of_another_goal():
    goals = {p.name.removesuffix('.md'): load_data(p, frontmatter=True)
             for p in (ROOT / 'docs/goals').glob('*-goal.md')}
    found = 0
    for name, data in goals.items():
        for ac, criterion in data['criteria'].items():
            target = criterion.get('assessed_in')
            if target:
                found += 1
                assert target['goal'] != name, f'{name} {ac} names its own goal'
                assert target['criterion'] in goals[target['goal']]['criteria'], f'{name} {ac}'
                assert 'assessed_in' not in goals[target['goal']]['criteria'][target['criterion']]
    assert found
