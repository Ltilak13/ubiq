"""Keep goal evidence traceable without claiming semantic corroboration."""
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from ubiq.schemas import load_data

ROOT = Path(__file__).resolve().parents[1]
GOALS = (
    "domain-schema", "composable-knowledge", "human-agent-readability",
    "checkable-contracts-evidence", "safe-adoption-evolution",
)
SCHEMA = load_data(ROOT / '.ubiq/schemas/goal.json')


@pytest.mark.parametrize('name', GOALS)
def test_goal_evidence_locations_and_criteria(name):
    goal = ROOT / 'docs/goals' / f'{name}-goal.md'
    data = load_data(goal, frontmatter=True)
    Draft202012Validator(SCHEMA).validate(data)
    labels = re.findall(r'^\d+\. (AC\d+):', goal.read_text(), re.MULTILINE)
    assert len(labels) == len(set(labels)), f'{goal}: duplicate acceptance label'
    assert set(labels) == set(data['criteria']), f'{goal}: criteria drift'
    for criterion in data['criteria'].values():
        for support in criterion['support']:
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


MET = {'assessment': 'met', 'gap': 'None remaining.', 'review': {'by': 'Lucas', 'note': 'Checked.'},
       'support': [{'feature': 'f', 'implementation': {'path': 'a', 'anchor': 'x'},
                    'check': {'path': 'b', 'anchor': 'y'}}]}


def _criterion(**fields):
    return {'name': 'g', 'status': 'proposed', 'criteria': {'AC1': fields}}


def test_met_assessment_with_review_and_adopted_issues_is_valid():
    Draft202012Validator(SCHEMA).validate(_criterion(**MET, issues=[3, 4]))


@pytest.mark.parametrize('fields', [
    {**MET, 'support': []},
    {key: value for key, value in MET.items() if key != 'review'},
    {**MET, 'review': {'by': 'Lucas', 'note': ' '}},
    {**MET, 'review': {'by': 'Lucas'}},
    {'assessment': 'unassessed', 'support': [], 'gap': 'g', 'review': MET['review']},
    {**MET, 'issues': [3, 3]},
    {**MET, 'issues': [0]},
    {**MET, 'issues': ['#3']},
])
def test_met_assessment_requires_support_and_review(fields):
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(_criterion(**fields))
