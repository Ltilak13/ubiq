---
symbols:
  BUNDLED:
    id: symbol:ubiq.plan.BUNDLED
    feature: feature-planning
    term: BUNDLED
    form: bound
    scenarios: [tests/test_plan.py::test_shipped_features_form_a_valid_order]
    params:
      type: object
      additionalProperties: false
      properties: {}
    result: {}
    errors: false
  PlanError:
    id: symbol:ubiq.plan.PlanError
    feature: feature-planning
    term: PlanError
    form: bound
    scenarios: [tests/test_plan.py::test_missing_requirement_fails]
    params:
      type: object
      additionalProperties: false
      properties: {}
    result: {}
    errors: false
  Feature:
    id: symbol:ubiq.plan.Feature
    feature: feature-planning
    term: Feature
    form: bound
    scenarios: [tests/test_plan.py::test_order_follows_requirements_with_alphabetical_ties]
    params:
      type: object
      additionalProperties: false
      properties:
        name: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str"}
        summary: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str"}
        requires: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "tuple[str, ...]", "x-python-default": "()"}
        codes: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "tuple[str, ...]", "x-python-default": "()"}
        config: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "tuple[str, ...]", "x-python-default": "()"}
        docs: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "''"}
        status: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "'shipped'"}
        issue: {"x-python-kind": "positional-or-keyword", "x-python-type": "int | None", "x-python-default": "None"}
      required: ["name", "summary"]
    result: {}
    errors: false
  feature_status:
    id: symbol:ubiq.plan.feature_status
    feature: feature-planning
    term: feature status
    form: bound
    scenarios: [tests/test_feature_lifecycle.py::test_bad_status_is_a_plan_error]
    params:
      type: object
      additionalProperties: false
      properties:
        meta: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[str, object]"}
      required: ["meta"]
    result: {"type": "string", "x-python-type": "str"}
    errors: false
  load_features:
    id: symbol:ubiq.plan.load_features
    feature: feature-planning
    term: load features
    form: bound
    scenarios: [tests/test_plan.py::test_shipped_features_form_a_valid_order]
    params:
      type: object
      additionalProperties: false
      properties:
        directory: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "Path", "x-python-default": "BUNDLED"}
      required: []
    result: {"type": "array", "x-python-type": "list[Feature]"}
    errors: {"type": "string", "enum": ["PlanError"]}
  order:
    id: symbol:ubiq.plan.order
    feature: feature-planning
    term: order
    form: bound
    scenarios: [tests/test_plan.py::test_order_follows_requirements_with_alphabetical_ties]
    params:
      type: object
      additionalProperties: false
      properties:
        features: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Iterable[Feature]"}
      required: ["features"]
    result: {"type": "array", "x-python-type": "list[Feature]"}
    errors: {"type": "string", "enum": ["PlanError"]}
  used_features:
    id: symbol:ubiq.plan.used_features
    feature: feature-planning
    term: used features
    form: bound
    scenarios: [tests/test_plan.py::test_used_features_come_from_config_and_requirements]
    params:
      type: object
      additionalProperties: false
      properties:
        features: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[Feature]"}
        root: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "Path"}
        declared: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Iterable[str]", "x-python-default": "()"}
      required: ["features", "root"]
    result: {"type": "array", "x-python-type": "set[str]"}
    errors: false
  next_steps:
    id: symbol:ubiq.plan.next_steps
    feature: feature-planning
    term: next steps
    form: bound
    scenarios: [tests/test_plan.py::test_next_steps_skip_used_and_unmet_features]
    params:
      type: object
      additionalProperties: false
      properties:
        ordered: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[Feature]"}
        used: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "set[str]"}
      required: ["ordered", "used"]
    result: {"type": "array", "x-python-type": "list[Feature]"}
    errors: false
  cmd_plan:
    id: symbol:ubiq.plan.cmd_plan
    feature: feature-planning
    term: cmd plan
    form: bound
    scenarios: [tests/test_plan.py::test_plan_lists_every_feature_in_order]
    params:
      type: object
      additionalProperties: false
      properties:
        args: {"x-python-kind": "positional-or-keyword"}
      required: ["args"]
    result: {"type": "integer", "x-python-type": "int"}
    errors: false
---

# plan.py

## `BUNDLED`

Location of the feature records shipped with Ubiq.

## `PlanError`

Failure to read or order feature records.

## `Feature`

Inputs for feature adoption and ordering.

## `load_features`

Load and sort the feature records from one directory.

## `order`

Sort features after their requirements with alphabetical ties.

## `used_features`

Find the selected features and their transitive requirements.

## `next_steps`

List unused features whose requirements are all in use.

## `cmd_plan`

Print adoption order or the next available features.

## `feature_status`

A feature record's status: `planned`, or `shipped` when absent.
