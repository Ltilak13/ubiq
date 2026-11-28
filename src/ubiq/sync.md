---
symbols:
  SyncError:
    id: symbol:ubiq.sync.SyncError
    feature: github-sync
    term: SyncError
    form: bound
    scenarios: [tests/test_sync.py::test_unreadable_goal_is_a_sync_error]
    params:
      type: object
      additionalProperties: false
      properties: {}
    result: {}
    errors: false
  Desired:
    id: symbol:ubiq.sync.Desired
    feature: github-sync
    term: Desired
    form: bound
    scenarios: [tests/test_plan_records.py::test_each_step_is_an_item_with_its_links]
    params:
      type: object
      additionalProperties: false
      properties:
        kind: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str"}
        ident: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[str, str]"}
        marker: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str"}
        title: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str"}
        body: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str"}
        state: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str"}
        listed: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "tuple[int, ...]", "x-python-default": "()"}
        close_comment: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "''"}
        priority: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "''"}
        label_prefix: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "DEFAULT_LABEL_PREFIX"}
        requires: {"x-python-kind": "positional-or-keyword", "x-python-type": "tuple[int, ...] | None", "x-python-default": "None"}
        requires_prs: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "tuple[int, ...]", "x-python-default": "()"}
        requires_markers: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "tuple[str, ...]", "x-python-default": "()"}
        parent_issue: {"x-python-kind": "positional-or-keyword", "type": "integer", "x-python-type": "int", "x-python-default": "0"}
        parent: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "''"}
        creates: {"x-python-kind": "positional-or-keyword", "type": "boolean", "x-python-type": "bool", "x-python-default": "True"}
        close_reason: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "'completed'"}
        deferred: {"x-python-kind": "positional-or-keyword", "type": "boolean", "x-python-type": "bool", "x-python-default": "False"}
        regression: {"x-python-kind": "positional-or-keyword", "type": "boolean", "x-python-type": "bool", "x-python-default": "False"}
        confirm_closed: {"x-python-kind": "positional-or-keyword", "type": "boolean", "x-python-type": "bool", "x-python-default": "False"}
        prs: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "tuple[int, ...]", "x-python-default": "()"}
        required_prs: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "tuple[tuple[str, tuple[int, ...]], ...]", "x-python-default": "()"}
        comment: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "''"}
        comment_marker: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "''"}
        branch: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "''"}
      required: ["kind", "ident", "marker", "title", "body", "state"]
    result: {}
    errors: false
  Stack:
    id: symbol:ubiq.sync.Stack
    feature: tracking-fields
    term: Stack
    form: bound
    scenarios: [tests/test_pr_stacks.py::test_record_stacks_cover_records_that_mirror_no_issue]
    params:
      type: object
      additionalProperties: false
      properties:
        ident: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[str, str]"}
        prs: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "tuple[int, ...]"}
        required: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "tuple[tuple[str, tuple[int, ...]], ...]"}
      required: ["ident", "prs", "required"]
    result: {}
    errors: false
  Tracked:
    id: symbol:ubiq.sync.Tracked
    feature: tracking-fields
    term: Tracked
    form: bound
    scenarios: [tests/test_pr_stacks.py::test_an_explicit_implementing_pr_counts_without_a_closing_reference]
    params:
      type: object
      additionalProperties: false
      properties:
        issue: {"x-python-kind": "positional-or-keyword", "x-python-type": "int | None"}
        prs: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "tuple[int, ...]"}
        requires: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "tuple[str, ...]"}
      required: ["issue", "prs", "requires"]
    result: {}
    errors: false
  criterion_met:
    id: symbol:ubiq.sync.criterion_met
    feature: criterion-scenarios
    term: criterion met
    form: bound
    scenarios: [tests/test_criterion_scenarios.py::test_a_passing_scenario_closes_the_criterion_issue]
    params:
      type: object
      additionalProperties: false
      properties:
        goal: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[str, Any]"}
        ac: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str"}
        results: {"x-python-kind": "positional-or-keyword", "x-python-type": "Mapping[tuple[str, str], str] | None"}
      required: ["goal", "ac", "results"]
    result: {"x-python-type": "bool | None"}
    errors: false
  goal_issue_desired:
    id: symbol:ubiq.sync.goal_issue_desired
    feature: criterion-scenarios
    term: goal issue desired
    form: bound
    scenarios: [tests/test_criterion_scenarios.py::test_the_goal_issue_closes_when_every_criterion_holds]
    params:
      type: object
      additionalProperties: false
      properties:
        goals: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[Mapping[str, Any]]"}
        sha: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "''"}
        results: {"x-python-kind": "positional-or-keyword", "x-python-type": "Mapping[tuple[str, str], str] | None", "x-python-default": "None"}
      required: ["goals"]
    result: {"type": "array", "x-python-type": "list[Desired]"}
    errors: false
  resolve_priority:
    id: symbol:ubiq.sync.resolve_priority
    feature: tracking-fields
    term: resolve priority
    form: bound
    scenarios: [tests/test_priority_inheritance.py::test_resolve_priority_prefers_the_item]
    params:
      type: object
      additionalProperties: false
      properties:
        item: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[str, Any]"}
        container: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[str, Any]"}
      required: ["item", "container"]
    result: {"type": "string", "x-python-type": "str"}
    errors: false
  load_goal:
    id: symbol:ubiq.sync.load_goal
    feature: github-sync
    term: load goal
    form: bound
    scenarios: [tests/test_sync.py::test_wrapped_criterion_is_read_whole]
    params:
      type: object
      additionalProperties: false
      properties:
        path: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "Path"}
        root: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "Path"}
      required: ["path", "root"]
    result: {"type": "object", "x-python-type": "dict[str, Any]"}
    errors: {"type": "string", "enum": ["SyncError"]}
  goal_desired:
    id: symbol:ubiq.sync.goal_desired
    feature: github-sync
    term: goal desired
    form: bound
    scenarios: [tests/test_sync.py::test_unmet_criterion_without_issue_is_created_with_verifiable_body]
    params:
      type: object
      additionalProperties: false
      properties:
        goal: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[str, Any]"}
        sha: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "''"}
        label_prefix: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "DEFAULT_LABEL_PREFIX"}
        numbers: {"x-python-kind": "positional-or-keyword", "x-python-type": "Mapping[str, int] | None", "x-python-default": "None"}
        pulls: {"x-python-kind": "positional-or-keyword", "x-python-type": "Mapping[str, tuple[int, ...]] | None", "x-python-default": "None"}
        goal_issues: {"x-python-kind": "positional-or-keyword", "x-python-type": "Mapping[str, int] | None", "x-python-default": "None"}
        prioritized_only: {"x-python-kind": "positional-or-keyword", "type": "boolean", "x-python-type": "bool", "x-python-default": "False"}
        results: {"x-python-kind": "positional-or-keyword", "x-python-type": "Mapping[tuple[str, str], str] | None", "x-python-default": "None"}
      required: ["goal"]
    result: {"type": "array", "x-python-type": "list[Desired]"}
    errors: false
  tracked_records:
    id: symbol:ubiq.sync.tracked_records
    feature: tracking-fields
    term: tracked records
    form: bound
    scenarios: [tests/test_pr_stacks.py::test_tracked_records_read_pr_and_requires]
    params:
      type: object
      additionalProperties: false
      properties:
        cfg: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Config"}
      required: ["cfg"]
    result: {"type": "object", "x-python-type": "dict[str, Tracked]"}
    errors: false
  load_plan:
    id: symbol:ubiq.sync.load_plan
    feature: plan-records
    term: load plan
    form: bound
    scenarios: [tests/test_plan_records.py::test_load_plan_reads_frontmatter_and_rejects_unreadable]
    params:
      type: object
      additionalProperties: false
      properties:
        path: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "Path"}
        root: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "Path"}
      required: ["path", "root"]
    result: {"type": "object", "x-python-type": "dict[str, Any]"}
    errors: {"type": "string", "enum": ["SyncError"]}
  plan_desired:
    id: symbol:ubiq.sync.plan_desired
    feature: plan-records
    term: plan desired
    form: bound
    scenarios: [tests/test_plan_records.py::test_each_step_is_an_item_with_its_links, tests/test_plan_records.py::test_step_requires_become_blocked_by_links_through_fact_requires]
    params:
      type: object
      additionalProperties: false
      properties:
        plan_record: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[str, Any]"}
        label_prefix: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "DEFAULT_LABEL_PREFIX"}
        step_issues: {"x-python-kind": "positional-or-keyword", "x-python-type": "Mapping[str, int] | None", "x-python-default": "None"}
      required: ["plan_record"]
    result: {"type": "array", "x-python-type": "list[Desired]"}
    errors: false
  plan_issue_desired:
    id: symbol:ubiq.sync.plan_issue_desired
    feature: plan-records
    term: plan issue desired
    form: bound
    scenarios: [tests/test_status_labels.py::test_a_plans_own_issue_follows_the_plans_priority_even_when_proposed]
    params:
      type: object
      additionalProperties: false
      properties:
        plan_record: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[str, Any]"}
        label_prefix: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "DEFAULT_LABEL_PREFIX"}
      required: ["plan_record"]
    result: {"type": "array", "x-python-type": "list[Desired]"}
    errors: false
  decision_comment:
    id: symbol:ubiq.sync.decision_comment
    feature: decision-records
    term: decision comment
    form: bound
    scenarios: [tests/test_decision_records.py::test_superseded_comment_names_the_replacement_and_proposed_mirrors_nothing]
    params:
      type: object
      additionalProperties: false
      properties:
        decision: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[str, Any]"}
        replacement: {"x-python-kind": "positional-or-keyword", "x-python-type": "Mapping[str, Any] | None"}
      required: ["decision", "replacement"]
    result: {"type": "string", "x-python-type": "str"}
    errors: false
  decision_desired:
    id: symbol:ubiq.sync.decision_desired
    feature: decision-records
    term: decision desired
    form: bound
    scenarios: [tests/test_decision_records.py::test_accepted_decision_gets_one_comment_and_closes_the_question]
    params:
      type: object
      additionalProperties: false
      properties:
        decisions: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[Mapping[str, Any]]"}
        label_prefix: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "DEFAULT_LABEL_PREFIX"}
      required: ["decisions"]
    result: {"type": "array", "x-python-type": "list[Desired]"}
    errors: false
  tracked_issue_numbers:
    id: symbol:ubiq.sync.tracked_issue_numbers
    feature: tracking-fields
    term: tracked issue numbers
    form: bound
    scenarios: [tests/test_requires_links.py::test_records_resolve_names_through_their_issue_and_pr_entries]
    params:
      type: object
      additionalProperties: false
      properties:
        cfg: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Config"}
      required: ["cfg"]
    result: {"type": "object", "x-python-type": "dict[str, int]"}
    errors: false
  backed_issue_numbers:
    id: symbol:ubiq.sync.backed_issue_numbers
    feature: github-sync
    term: backed issue numbers
    form: bound
    scenarios: [tests/test_sync.py::test_every_issue_number_a_record_names_is_backed]
    params:
      type: object
      additionalProperties: false
      properties:
        cfg: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Config"}
      required: ["cfg"]
    result: {"type": "array", "x-python-type": "set[int]"}
    errors: false
  record_stacks:
    id: symbol:ubiq.sync.record_stacks
    feature: tracking-fields
    term: record stacks
    form: bound
    scenarios: [tests/test_pr_stacks.py::test_tracked_records_read_pr_and_requires]
    params:
      type: object
      additionalProperties: false
      properties:
        records: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[str, Tracked]"}
      required: ["records"]
    result: {"type": "array", "x-python-type": "list[Stack]"}
    errors: false
  load_feature:
    id: symbol:ubiq.sync.load_feature
    feature: github-sync
    term: load feature
    form: bound
    scenarios: [tests/test_feature_lifecycle.py::test_feature_without_a_summary_is_not_readable]
    params:
      type: object
      additionalProperties: false
      properties:
        path: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "Path"}
        root: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "Path"}
      required: ["path", "root"]
    result: {"type": "object", "x-python-type": "dict[str, Any]"}
    errors: false
  feature_desired:
    id: symbol:ubiq.sync.feature_desired
    feature: github-sync
    term: feature desired
    form: bound
    scenarios: [tests/test_feature_lifecycle.py::test_feature_desired_rejects_an_unknown_status]
    params:
      type: object
      additionalProperties: false
      properties:
        feature: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[str, Any]"}
        sha: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "''"}
        label_prefix: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "DEFAULT_LABEL_PREFIX"}
      required: ["feature"]
    result: {"type": "array", "x-python-type": "list[Desired]"}
    errors: false
  desired_from_config:
    id: symbol:ubiq.sync.desired_from_config
    feature: github-sync
    term: desired from config
    form: bound
    scenarios: [tests/test_sync.py::test_this_repository_creates_only_for_untracked_criteria]
    params:
      type: object
      additionalProperties: false
      properties:
        cfg: {"x-python-kind": "positional-or-keyword", "x-python-type": "Config"}
        sha: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "''"}
        records: {"x-python-kind": "positional-or-keyword", "x-python-type": "Mapping[str, Tracked] | None", "x-python-default": "None"}
        results: {"x-python-kind": "positional-or-keyword", "x-python-type": "Mapping[tuple[str, str], str] | None", "x-python-default": "None"}
      required: ["cfg"]
    result: {"type": "array", "x-python-type": "list[Desired]"}
    errors: {"type": "string", "enum": ["SyncError"]}
  fact_exists:
    id: symbol:ubiq.sync.fact_exists
    feature: github-sync
    term: fact exists
    form: bound
    scenarios: [tests/test_sync.py::test_unmet_criterion_without_issue_is_created_with_verifiable_body]
    params:
      type: object
      additionalProperties: false
      properties:
        item: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Desired"}
        tracked: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[int]"}
        issues: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[int, Issue]"}
      required: ["item", "tracked", "issues"]
    result: {"type": "array", "x-python-type": "list[Action]"}
    errors: false
  fact_state:
    id: symbol:ubiq.sync.fact_state
    feature: github-sync
    term: fact state
    form: bound
    scenarios: [tests/test_sync.py::test_met_criterion_closes_open_listed_and_marked_issues_only]
    params:
      type: object
      additionalProperties: false
      properties:
        item: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Desired"}
        tracked: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[int]"}
        issues: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[int, Issue]"}
      required: ["item", "tracked", "issues"]
    result: {"type": "array", "x-python-type": "list[Action]"}
    errors: false
  fact_not_planned:
    id: symbol:ubiq.sync.fact_not_planned
    feature: github-sync
    term: fact not planned
    form: bound
    scenarios: [tests/test_sync.py::test_issue_closed_not_planned_while_its_criterion_is_not_deferred_is_drift]
    params:
      type: object
      additionalProperties: false
      properties:
        item: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Desired"}
        tracked: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[int]"}
        issues: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[int, Issue]"}
      required: ["item", "tracked", "issues"]
    result: {"type": "array", "x-python-type": "list[Action]"}
    errors: false
  fact_confirm:
    id: symbol:ubiq.sync.fact_confirm
    feature: github-sync
    term: fact confirm
    form: bound
    scenarios: [tests/test_sync.py::test_an_issue_closed_before_the_sync_gets_its_met_at_comment_once]
    params:
      type: object
      additionalProperties: false
      properties:
        item: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Desired"}
        tracked: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[int]"}
        issues: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[int, Issue]"}
      required: ["item", "tracked", "issues"]
    result: {"type": "array", "x-python-type": "list[Action]"}
    errors: false
  confirmable:
    id: symbol:ubiq.sync.confirmable
    feature: github-sync
    term: confirmable
    form: bound
    scenarios: [tests/test_sync.py::test_an_issue_closed_before_the_sync_gets_its_met_at_comment_once]
    params:
      type: object
      additionalProperties: false
      properties:
        desired: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Iterable[Desired]"}
        snapshot: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[Issue]"}
      required: ["desired", "snapshot"]
    result: {"type": "array", "x-python-type": "list[int]"}
    errors: false
  fact_priority:
    id: symbol:ubiq.sync.fact_priority
    feature: tracking-fields
    term: fact priority
    form: bound
    scenarios: [tests/test_priority_label.py::test_changing_priority_is_one_label_change_that_leaves_other_labels]
    params:
      type: object
      additionalProperties: false
      properties:
        item: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Desired"}
        tracked: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[int]"}
        issues: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[int, Issue]"}
      required: ["item", "tracked", "issues"]
    result: {"type": "array", "x-python-type": "list[Action]"}
    errors: false
  BLOCKED_BEGIN:
    id: symbol:ubiq.sync.BLOCKED_BEGIN
    feature: tracking-fields
    term: BLOCKED BEGIN
    form: bound
    scenarios: [tests/test_requires_links.py::test_removing_the_requires_field_clears_its_generated_section]
    params:
      type: object
      additionalProperties: false
      properties: {}
    result: {}
    errors: false
  BLOCKED_END:
    id: symbol:ubiq.sync.BLOCKED_END
    feature: tracking-fields
    term: BLOCKED END
    form: bound
    scenarios: [tests/test_requires_links.py::test_removing_the_requires_field_clears_its_generated_section]
    params:
      type: object
      additionalProperties: false
      properties: {}
    result: {}
    errors: false
  set_blocked_by:
    id: symbol:ubiq.sync.set_blocked_by
    feature: tracking-fields
    term: set blocked by
    form: bound
    scenarios: [tests/test_requires_links.py::test_changing_and_dropping_a_pr_rewrites_only_between_the_markers]
    params:
      type: object
      additionalProperties: false
      properties:
        body: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str"}
        prs: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[int]"}
      required: ["body", "prs"]
    result: {"type": "string", "x-python-type": "str"}
    errors: false
  fact_requires:
    id: symbol:ubiq.sync.fact_requires
    feature: tracking-fields
    term: fact requires
    form: bound
    scenarios: [tests/test_requires_links.py::test_adding_a_requires_entry_links_the_blocker_by_its_numeric_id]
    params:
      type: object
      additionalProperties: false
      properties:
        item: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Desired"}
        tracked: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[int]"}
        issues: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[int, Issue]"}
      required: ["item", "tracked", "issues"]
    result: {"type": "array", "x-python-type": "list[Action]"}
    errors: false
  fact_blocked_line:
    id: symbol:ubiq.sync.fact_blocked_line
    feature: tracking-fields
    term: fact blocked line
    form: bound
    scenarios: [tests/test_requires_links.py::test_pr_entries_are_a_marked_section_and_never_a_link]
    params:
      type: object
      additionalProperties: false
      properties:
        item: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Desired"}
        tracked: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[int]"}
        issues: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[int, Issue]"}
      required: ["item", "tracked", "issues"]
    result: {"type": "array", "x-python-type": "list[Action]"}
    errors: false
  referenced_numbers:
    id: symbol:ubiq.sync.referenced_numbers
    feature: github-sync
    term: referenced numbers
    form: bound
    scenarios: [tests/test_sync.py::test_commit_messages_and_branch_names_name_issues]
    params:
      type: object
      additionalProperties: false
      properties:
        text: {"x-python-kind": "positional-or-keyword", "x-python-type": "str | None"}
        repo: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "''"}
      required: ["text"]
    result: {"type": "array", "x-python-type": "tuple[int, ...]"}
    errors: false
  branch_numbers:
    id: symbol:ubiq.sync.branch_numbers
    feature: github-sync
    term: branch numbers
    form: bound
    scenarios: [tests/test_sync.py::test_commit_messages_and_branch_names_name_issues]
    params:
      type: object
      additionalProperties: false
      properties:
        branch: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str"}
      required: ["branch"]
    result: {"type": "array", "x-python-type": "tuple[int, ...]"}
    errors: false
  closing_numbers:
    id: symbol:ubiq.sync.closing_numbers
    feature: github-sync
    term: closing numbers
    form: bound
    scenarios: [tests/test_pr_stacks.py::test_closing_keywords_in_the_body]
    params:
      type: object
      additionalProperties: false
      properties:
        body: {"x-python-kind": "positional-or-keyword", "x-python-type": "str | None"}
        repo: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "''"}
      required: ["body"]
    result: {"type": "array", "x-python-type": "tuple[int, ...]"}
    errors: false
  stack_of:
    id: symbol:ubiq.sync.stack_of
    feature: tracking-fields
    term: stack of
    form: bound
    scenarios: [tests/test_pr_stacks.py::test_a_wrong_base_is_a_stack_finding_and_drift]
    params:
      type: object
      additionalProperties: false
      properties:
        item: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Desired"}
      required: ["item"]
    result: {"type": "object", "x-python-type": "Stack"}
    errors: false
  stack_findings:
    id: symbol:ubiq.sync.stack_findings
    feature: tracking-fields
    term: stack findings
    form: bound
    scenarios: [tests/test_pr_stacks.py::test_a_wrong_base_is_a_stack_finding_and_drift]
    params:
      type: object
      additionalProperties: false
      properties:
        stack: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Stack"}
        pulls: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[int, Pull]"}
      required: ["stack", "pulls"]
    result: {"type": "array", "x-python-type": "list[Action]"}
    errors: false
  fact_in_review:
    id: symbol:ubiq.sync.fact_in_review
    feature: github-sync
    term: fact in review
    form: bound
    scenarios: [tests/test_pr_stacks.py::test_an_open_closing_pr_adds_the_label_and_drops_in_progress_only]
    params:
      type: object
      additionalProperties: false
      properties:
        ident: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[str, str]"}
        tracked: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[int]"}
        issues: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[int, Issue]"}
        in_review: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "set[int]"}
        started: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "set[int]"}
      required: ["ident", "tracked", "issues", "in_review", "started"]
    result: {"type": "array", "x-python-type": "list[Action]"}
    errors: false
  fact_stack:
    id: symbol:ubiq.sync.fact_stack
    feature: tracking-fields
    term: fact stack
    form: bound
    scenarios: [tests/test_pr_stacks.py::test_a_wrong_base_is_a_stack_finding_and_drift]
    params:
      type: object
      additionalProperties: false
      properties:
        item: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Desired"}
        tracked: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[int]"}
        issues: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[int, Issue]"}
        pulls: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[int, Pull]"}
      required: ["item", "tracked", "issues", "pulls"]
    result: {"type": "array", "x-python-type": "list[Action]"}
    errors: false
  fact_part_of:
    id: symbol:ubiq.sync.fact_part_of
    feature: github-sync
    term: fact part of
    form: bound
    scenarios: [tests/test_part_of.py::test_tracked_issue_that_is_not_a_sub_issue_is_linked_and_it_is_drift]
    params:
      type: object
      additionalProperties: false
      properties:
        item: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Desired"}
        tracked: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[int]"}
        issues: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[int, Issue]"}
      required: ["item", "tracked", "issues"]
    result: {"type": "array", "x-python-type": "list[Action]"}
    errors: false
  keyword_warnings:
    id: symbol:ubiq.sync.keyword_warnings
    feature: github-sync
    term: keyword warnings
    form: bound
    scenarios: [tests/test_sync.py::test_a_closing_keyword_on_an_unmet_criterions_own_issue_warns]
    params:
      type: object
      additionalProperties: false
      properties:
        items: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Iterable[Desired]"}
        by_marker: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[str, list[Issue]]"}
        pulls: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[int, Pull]"}
      required: ["items", "by_marker", "pulls"]
    result: {"type": "array", "x-python-type": "list[Action]"}
    errors: false
  unexpected_sub_issues:
    id: symbol:ubiq.sync.unexpected_sub_issues
    feature: github-sync
    term: unexpected sub issues
    form: bound
    scenarios: [tests/test_part_of.py::test_sub_issue_added_on_github_is_drift_and_unlinked]
    params:
      type: object
      additionalProperties: false
      properties:
        items: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[tuple[Desired, list[int]]]"}
        issues: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[int, Issue]"}
      required: ["items", "issues"]
    result: {"type": "array", "x-python-type": "list[Action]"}
    errors: false
  fact_comment:
    id: symbol:ubiq.sync.fact_comment
    feature: decision-records
    term: fact comment
    form: bound
    scenarios: [tests/test_decision_records.py::test_changed_record_updates_the_generated_comment_only]
    params:
      type: object
      additionalProperties: false
      properties:
        item: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Desired"}
        tracked: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[int]"}
        issues: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[int, Issue]"}
      required: ["item", "tracked", "issues"]
    result: {"type": "array", "x-python-type": "list[Action]"}
    errors: false
  plan:
    id: symbol:ubiq.sync.plan
    feature: github-sync
    term: plan
    form: bound
    scenarios: [tests/test_sync.py::test_planning_is_idempotent_after_its_own_actions]
    params:
      type: object
      additionalProperties: false
      properties:
        desired: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Iterable[Desired]"}
        snapshot: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[Issue]"}
        pulls: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[Pull]", "x-python-default": "()"}
        stacks: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Iterable[Stack]", "x-python-default": "()"}
        records: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Iterable[Tracked]", "x-python-default": "()"}
        backed: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Iterable[int] | None", "x-python-default": "None"}
        branches: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Iterable[str]", "x-python-default": "()"}
      required: ["desired", "snapshot"]
    result: {"type": "array", "x-python-type": "list[Action]"}
    errors: false
  derived_status:
    id: symbol:ubiq.sync.derived_status
    feature: github-sync
    term: derived status
    form: bound
    scenarios: [tests/test_sync.py::test_ignore_derived_drops_only_the_derived_status_labels]
    params:
      type: object
      additionalProperties: false
      properties:
        action: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Action"}
      required: ["action"]
    result: {"type": "boolean", "x-python-type": "bool"}
    errors: false
  drift:
    id: symbol:ubiq.sync.drift
    feature: github-sync
    term: drift
    form: bound
    scenarios: [tests/test_sync.py::test_drift_is_every_action_but_noop]
    params:
      type: object
      additionalProperties: false
      properties:
        actions: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Iterable[Action]"}
        ignore_derived: {"x-python-kind": "positional-or-keyword", "type": "boolean", "x-python-type": "bool", "x-python-default": "False"}
      required: ["actions"]
    result: {"type": "array", "x-python-type": "list[Action]"}
    errors: false
  urllib_transport:
    id: symbol:ubiq.sync.urllib_transport
    feature: github-sync
    term: urllib transport
    form: bound
    scenarios: []
    params:
      type: object
      additionalProperties: false
      properties:
        method: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str"}
        url: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str"}
        token: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str"}
        payload: {"x-python-kind": "positional-or-keyword", "type": ["object", "null"], "x-python-type": "dict | None", "x-python-default": "None"}
      required: ["method", "url", "token"]
    result: {"x-python-type": "Any"}
    errors: {"type": "string", "enum": ["OSError", "ValueError"]}
  GitHub:
    id: symbol:ubiq.sync.GitHub
    feature: github-sync
    term: GitHub
    form: bound
    scenarios: [tests/test_sync.py::test_snapshot_pages_and_drops_pull_requests]
    params:
      type: object
      additionalProperties: false
      properties:
        repo: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str"}
        token: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "''"}
        transport: {"x-python-kind": "positional-or-keyword", "x-python-type": "Transport", "x-python-default": "urllib_transport"}
        pause: {"x-python-kind": "positional-or-keyword", "type": "number", "x-python-type": "float", "x-python-default": "1.0"}
      required: ["repo"]
    result: {}
    errors: false
  GitHub.snapshot:
    id: symbol:ubiq.sync.GitHub.snapshot
    feature: github-sync
    term: GitHub snapshot
    form: bound
    scenarios: [tests/test_sync.py::test_snapshot_pages_and_drops_pull_requests]
    params:
      type: object
      additionalProperties: false
      properties:
        parents: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Iterable[int]", "x-python-default": "()"}
      required: []
    result: {"type": "array", "x-python-type": "list[Issue]"}
    errors: {"type": "string", "enum": ["OSError"]}
  GitHub.pulls:
    id: symbol:ubiq.sync.GitHub.pulls
    feature: github-sync
    term: GitHub pulls
    form: bound
    scenarios: [tests/test_part_of.py::test_create_then_attach_in_one_apply]
    params:
      type: object
      additionalProperties: false
      properties: {}
    result: {"type": "array", "x-python-type": "list[Pull]"}
    errors: false
  GitHub.branches:
    id: symbol:ubiq.sync.GitHub.branches
    feature: github-sync
    term: GitHub branches
    form: bound
    scenarios: [tests/test_status_labels.py::test_branches_pages]
    params:
      type: object
      additionalProperties: false
      properties: {}
    result: {"type": "array", "x-python-type": "list[str]"}
    errors: {"type": "string", "enum": ["OSError"]}
  GitHub.bot_markers:
    id: symbol:ubiq.sync.GitHub.bot_markers
    feature: github-sync
    term: GitHub bot markers
    form: bound
    scenarios: [tests/test_sync.py::test_an_issue_closed_before_the_sync_gets_its_met_at_comment_once]
    params:
      type: object
      additionalProperties: false
      properties:
        numbers: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Iterable[int]"}
      required: ["numbers"]
    result: {"type": "object", "x-python-type": "dict[int, set[str]]"}
    errors: false
  GitHub.comments:
    id: symbol:ubiq.sync.GitHub.comments
    feature: decision-records
    term: GitHub comments
    form: bound
    scenarios: [tests/test_decision_records.py::test_with_comments_reads_only_the_named_issues]
    params:
      type: object
      additionalProperties: false
      properties:
        number: {"x-python-kind": "positional-or-keyword", "type": "integer", "x-python-type": "int"}
      required: ["number"]
    result: {"type": "array", "x-python-type": "list[Issue]"}
    errors: false
  GitHub.with_comments:
    id: symbol:ubiq.sync.GitHub.with_comments
    feature: decision-records
    term: GitHub with comments
    form: bound
    scenarios: [tests/test_decision_records.py::test_with_comments_reads_only_the_named_issues]
    params:
      type: object
      additionalProperties: false
      properties:
        snapshot: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Sequence[Issue]"}
        numbers: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Iterable[int]"}
      required: ["snapshot", "numbers"]
    result: {"type": "array", "x-python-type": "list[Issue]"}
    errors: false
  GitHub.apply:
    id: symbol:ubiq.sync.GitHub.apply
    feature: github-sync
    term: GitHub apply
    form: bound
    scenarios: [tests/test_sync.py::test_apply_creates_an_issue_and_skips_noop_and_warn]
    params:
      type: object
      additionalProperties: false
      properties:
        actions: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "Iterable[Action]"}
        done: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "list[Action]"}
      required: ["actions", "done"]
    result: {"type": "null", "x-python-type": "None"}
    errors: {"type": "string", "enum": ["OSError"]}
  revision_root:
    id: symbol:ubiq.sync.revision_root
    feature: github-sync
    term: revision root
    form: bound
    scenarios: [tests/test_sync.py::test_ref_reads_only_the_records_and_ignores_symlinks]
    params:
      type: object
      additionalProperties: false
      properties:
        root: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "Path"}
        rev: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str"}
      required: ["root", "rev"]
    result: {"x-python-type": "Iterator[Path]"}
    errors: {"type": "string", "enum": ["SyncError"]}
  cmd_sync:
    id: symbol:ubiq.sync.cmd_sync
    feature: github-sync
    term: cmd sync
    form: bound
    scenarios: [tests/test_sync.py::test_dry_run_prints_the_plan_and_never_writes]
    params:
      type: object
      additionalProperties: false
      properties:
        args: {"x-python-kind": "positional-or-keyword"}
        transport: {"x-python-kind": "positional-or-keyword", "x-python-type": "Transport", "x-python-default": "urllib_transport"}
        pause: {"x-python-kind": "positional-or-keyword", "type": "number", "x-python-type": "float", "x-python-default": "1.0"}
      required: ["args"]
    result: {"type": "integer", "x-python-type": "int"}
    errors: false
---

# sync.py

## `SyncError`

Failure to read a sync input or revision.

## `Desired`

One item that should be mirrored to GitHub.

## `resolve_priority`

Use the item's priority if present and otherwise inherit its container's priority.

## `load_goal`

Read a goal record and its acceptance-criterion text.

## `goal_desired`

Derive the desired GitHub issue state for each goal criterion.

## `load_plan`

Read the metadata and steps of a plan record.

## `plan_desired`

Derive the desired GitHub issue state for tracked plan steps.

## `plan_issue_desired`

Derive the desired priority label of a plan's own issue, which holds for a proposed plan.

## `desired_from_config`

Build the desired issue state from the configured record files.

## `fact_exists`

Plan creation for an open item without a tracked issue.

## `fact_state`

Plan closure for open issues tracking a completed item.

## `fact_not_planned`

Warn about a criterion issue closed as not planned while its record is not deferred.

## `fact_priority`

Plan priority label changes for open issues.

## `plan`

Compare desired and observed issue states to plan actions.

## `drift`

Select actions that would change or warn about the mirror.

## `urllib_transport`

Send one authenticated GitHub REST request and decode its response.

## `GitHub`

GitHub issue adapter with an injectable transport.

## `GitHub.snapshot`

Read all issue pages, excluding pull requests.

## `GitHub.apply`

Perform planned writes and record completed actions.

## `revision_root`

Read configured records into a temporary tree for a Git revision.

## `cmd_sync`

Preview, check, or apply the proposed issue mirror.

## `Stack`

A record's pull requests and the pull requests of the records it requires.

## `Tracked`

What a schema-bound frontmatter record says about its tracking.

## `criterion_met`

Whether a criterion holds, counting its tagged scenario outcomes.

## `goal_issue_desired`

The desired state of each goal's own issue, closed when every criterion holds.

## `tracked_records`

Each schema-bound frontmatter record with its issue, pull requests, and requires.

## `tracked_issue_numbers`

Normalized record name to issue, for each tracked record that has one.

## `backed_issue_numbers`

Collect every issue number that a synced record names.

## `record_stacks`

A stack for each record that lists a pull request.

## `load_feature`

Read a feature record into its frontmatter plus its repository path.

## `feature_desired`

One desired issue for a feature record: open while planned, closed once shipped.

## `fact_confirm`

Post the "met at" comment owed to an issue that closed before the sync.

## `confirmable`

Closed issues whose bot comments must be read to confirm a "met at" comment.

## `BLOCKED_BEGIN`

Opening marker of the generated "Blocked by" section.

## `BLOCKED_END`

Closing marker of the generated "Blocked by" section.

## `set_blocked_by`

Rewrite the generated "Blocked by" section of an issue body.

## `fact_requires`

An open issue is blocked by exactly the issues its record requires.

## `fact_blocked_line`

An open issue body holds the generated "Blocked by" section for its pull requests.

## `referenced_numbers`

Issue numbers a commit message names by reference or closing keyword.

## `branch_numbers`

Issue numbers a branch name carries as `issue-<n>`.

## `closing_numbers`

Issue numbers a pull request body closes in the repository.

## `stack_of`

The stack of a desired item.

## `stack_findings`

Report a pull request based elsewhere than on a required record's pull request.

## `fact_in_review`

Keep the derived `status: in review` label while a pull request is open, and `status: in progress` while only a branch exists.

## `fact_stack`

The stack findings for one desired item.

## `fact_part_of`

Each tracking issue is a sub-issue of its parent record's issue.

## `keyword_warnings`

Warn when a pull request closes an unmet criterion's own issue by keyword.

## `unexpected_sub_issues`

Sub-issues on a parent issue that no record puts there.

## `derived_status`

Whether a label action changes only the derived status labels.

## `GitHub.pulls`

The open pull requests, with their bases, heads, and closing intent.

## `GitHub.branches`

The names of the repository's branches, which mark an issue `status: in progress`.

## `GitHub.bot_markers`

For each issue, the markers in comments the sync's bot wrote.

## `decision_comment`

The generated comment body for an accepted or superseded decision.

## `decision_desired`

One desired item per decision, tracking the issue its question names.

## `fact_comment`

Each question issue holds exactly one generated decision comment that matches its record.

## `GitHub.comments`

Every comment on one issue.

## `GitHub.with_comments`

The snapshot with comments read for the named issues.
