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
        requires_markers: {"x-python-kind": "positional-or-keyword", "type": "array", "x-python-type": "tuple[str, ...]", "x-python-default": "()"}
        parent_issue: {"x-python-kind": "positional-or-keyword", "type": "integer", "x-python-type": "int", "x-python-default": "0"}
      required: ["kind", "ident", "marker", "title", "body", "state"]
    result: {}
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
      required: ["goal"]
    result: {"type": "array", "x-python-type": "list[Desired]"}
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
    scenarios: [tests/test_plan_records.py::test_each_step_is_an_item_with_its_links]
    params:
      type: object
      additionalProperties: false
      properties:
        plan_record: {"x-python-kind": "positional-or-keyword", "type": "object", "x-python-type": "Mapping[str, Any]"}
        label_prefix: {"x-python-kind": "positional-or-keyword", "type": "string", "x-python-type": "str", "x-python-default": "DEFAULT_LABEL_PREFIX"}
      required: ["plan_record"]
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
      required: ["desired", "snapshot"]
    result: {"type": "array", "x-python-type": "list[Action]"}
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
      properties: {}
    result: {"type": "array", "x-python-type": "list[Issue]"}
    errors: {"type": "string", "enum": ["OSError"]}
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

## `load_goal`

Read a goal record and its acceptance-criterion text.

## `goal_desired`

Derive the desired GitHub issue state for each goal criterion.

## `load_plan`

Read the metadata and steps of a plan record.

## `plan_desired`

Derive the desired GitHub issue state for tracked plan steps.

## `desired_from_config`

Build the desired issue state from the configured record files.

## `fact_exists`

Plan creation for an open item without a tracked issue.

## `fact_state`

Plan closure for open issues tracking a completed item.

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
