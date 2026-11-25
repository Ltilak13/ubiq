"""Keep goal evidence traceable without claiming semantic corroboration."""
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from ubiq.schemas import load_data

ROOT = Path(__file__).resolve().parents[1]
GOALS = ("domain-schema", "composable-skills", "human-agent-readability")
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
