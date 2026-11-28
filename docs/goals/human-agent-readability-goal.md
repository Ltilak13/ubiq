---
name: human-agent-readability-goal
status: proposed
criteria:
  AC1:
    assessment: deferred
    support: []
    gap: "Deferred under the work-in-progress limit in `docs/goals/README.md`: this goal is `proposed`, so no work on it is scheduled. Issue #98 is closed as not planned. To schedule it, reopen the issue, set a `priority`, and replace this gap with the specific missing evidence."
    issues: [98]
  AC2:
    assessment: deferred
    support: []
    gap: "Deferred under the work-in-progress limit in `docs/goals/README.md`: this goal is `proposed`, so no work on it is scheduled. Issue #99 is closed as not planned. To schedule it, reopen the issue, set a `priority`, and replace this gap with the specific missing evidence."
    issues: [99]
  AC3:
    assessment: deferred
    support: []
    gap: "Deferred under the work-in-progress limit in `docs/goals/README.md`: this goal is `proposed`, so no work on it is scheduled. Issue #100 is closed as not planned. To schedule it, reopen the issue, set a `priority`, and replace this gap with the specific missing evidence."
    issues: [100]
  AC4:
    assessment: deferred
    support: []
    gap: "Deferred under the work-in-progress limit in `docs/goals/README.md`: this goal is `proposed`, so no work on it is scheduled. Issue #101 is closed as not planned. To schedule it, reopen the issue, set a `priority`, and replace this gap with the specific missing evidence."
    issues: [101]
  AC5:
    assessment: deferred
    support: []
    gap: "Deferred under the work-in-progress limit in `docs/goals/README.md`: this goal is `proposed`, so no work on it is scheduled. Issue #102 is closed as not planned. To schedule it, reopen the issue, set a `priority`, and replace this gap with the specific missing evidence."
    issues: [102]
  AC6:
    assessment: deferred
    support: []
    gap: "Deferred under the work-in-progress limit in `docs/goals/README.md`: this goal is `proposed`, so no work on it is scheduled. Issue #103 is closed as not planned. To schedule it, reopen the issue, set a `priority`, and replace this gap with the specific missing evidence."
    issues: [103]
  AC7:
    assessment: deferred
    support: []
    gap: "Deferred under the work-in-progress limit in `docs/goals/README.md`: this goal is `proposed`, so no work on it is scheduled. Issue #104 is closed as not planned. To schedule it, reopen the issue, set a `priority`, and replace this gap with the specific missing evidence."
    issues: [104]

---

# Goal: human and agent usability

This goal defines outcomes and acceptance evidence. It does
not claim that Ubiq currently checks readability or produces Markdown previews.

## Objective

Make each file easy for humans and agents to find, understand, navigate, and
use correctly. Give both audiences the same semantic goals and equal weight
when evaluating changes.

Use the strengths of rendered Markdown and raw Markdown deliberately. A preview
can communicate through visual hierarchy, tables, and diagrams. Source can
communicate through explicit headings, metadata, readable links, and predictable
structure. Both forms must preserve the same meaning, conditions, and authority.

Humans also read source, and agents can consume rendered content. Evaluate the
audience and the reading form separately instead of assigning one form to each.

## Shared outcomes

| Outcome | Human evidence | Agent evidence |
| --- | --- | --- |
| Find the right file | Locate it from its title, purpose, and navigation | Retrieve it from its identity, metadata, and references |
| Understand its meaning | Explain its purpose, scope, and important terms | Answer the same questions with supporting locations |
| Act correctly | Identify prerequisites, conditions, steps, and completion criteria | Identify the same requirements without guessing implicit context |
| Follow relationships | Reach the authoritative definition or required procedure | Resolve the same target and distinguish reference from required reuse |
| Maintain it safely | Make a focused edit with a readable diff | Preserve identity, meaning, and references through the same edit |

Use the same questions and expected answers for both audiences. Measure their
effort separately. Faster reading does not compensate for a wrong answer or a
missed condition.

## Use each reading form well

Start with the file's purpose and scope. Organize sections around the questions
readers need to answer. Keep a condition beside the instruction it controls.
Distinguish examples from requirements and optional details from required steps.

| Construct | Rendered Markdown | Raw Markdown |
| --- | --- | --- |
| Headings and spacing | Show hierarchy and support scanning | Expose section boundaries and useful search targets |
| Lists | Show sequence or parallel choices | Keep order, nesting, and conditions explicit |
| Tables | Compare facts with shared dimensions | Keep cells short enough to read without a wide viewport |
| Links | Use descriptive labels and usable destinations | Keep destinations inspectable and meaning clear without clicking |
| Code fences | Separate examples from prose | Preserve exact syntax and identify the example's language |
| Diagrams | Explain relationships or sequences visually | Provide readable diagram source or an equivalent textual account |
| Frontmatter | Make essential facts accessible when the preview hides metadata | Use named, typed fields with documented meanings |

Choose constructs for the content. A long procedure usually needs a list, while
a comparison benefits from a table. Avoid forcing every file into one layout.
Use meaningful labels and text alternatives so color or spatial position never
carries a required distinction alone.

Declare the Markdown dialect and preview environments used for acceptance.
Check renderer-specific features, including wiki-links, diagrams, and collapsible
sections, in those environments. A fallback must preserve required meaning when
an optional feature cannot render. Hidden comments must not contain instructions
that change the visible procedure.

Keep source readable during line-oriented search and review. Prefer focused
sections, stable headings, and short paragraphs. Avoid decorative markup or
wrapping changes that obscure a substantive edit.

## Keep one authoritative meaning

The [explicit domain models goal](domain-schema-goal.md) owns the division between
structured facts and explanatory prose. This goal adds a usability requirement:
readers must reach those facts from either reading form.

When a preview omits frontmatter, choose a supported way to expose required
facts. A derived display must identify its source and stay synchronized with it.
Do not require authors to maintain two independent copies of the same value.

A [[reference]] must lead to the intended [[glossary record]] in the supported
reading environments. A [[term]] keeps its meaning across metadata, prose, and
link labels. Presentation changes must preserve identities and relationships.

The [composable knowledge goal](composable-knowledge-goal.md) owns reuse through a
[[shared part]] and a [[composition edge]]. Evaluate the reading cost of that
reuse here: readers must know when to follow an included procedure and how to
return to the task. Count required file visits and navigation failures alongside
the reduction in duplicated text.

## Make quality measurable

Choose representative files, tasks, preview environments, and acceptance targets
before changing their layouts. Include a glossary record, a skill with shared
parts, a procedure with conditions, and a document with substantial metadata.
Include long tables, unsupported visual features, and ambiguous labels as
adverse cases.

Report results separately for human and agent readers, and for source and
preview. State the sample size, exclusions, and denominator for every rate.

- Correctness: questions answered correctly out of all agreed questions.
- Completeness: required facts and conditions found out of all required facts
  and conditions for the task.
- Navigation: authoritative targets reached out of all required targets.
- Effort: time, file visits, and search steps for humans; reads and input volume
  for agents. Record the agent and its available tools.
- Parity: conflicting or missing required meanings between source and preview.
- Maintenance: edits that preserve meaning and references out of all sampled
  edits, with independently maintained duplicate facts counted separately.

Use deterministic checks for structural defects that Ubiq can establish.
Keep comprehension assessments separate and report their uncertainty. Passing
a schema or link check alone does not establish readability.

## Acceptance evidence

The goal is achieved when:

1. AC1: Representative files have an agreed set of questions, expected answers, and
   supporting locations shared by human and agent evaluations.
2. AC2: Both audiences meet the agreed correctness, completeness, and navigation
   targets in source and the declared preview environments.
3. AC3: No required fact, condition, or instruction conflicts between the two forms
   in the acceptance sample. Unsupported features preserve required meaning.
4. AC4: Before-and-after examples demonstrate useful layout choices in both forms,
   with measured effort and correctness reported separately.
5. AC5: Metadata displays and alternative presentations trace to their authoritative
   facts, with checks or review evidence that detect drift.
6. AC6: A representative edit preserves identities, references, procedure order, and
   conditions while keeping the source diff readable.
7. AC7: Repeatable checks cover supported structural guarantees and adverse cases.
   Human and agent task results provide separate evidence of comprehension.

Set numerical targets and the evaluation sample during design. Implementation
choices remain open until the evidence identifies which changes help both
audiences. A new renderer or authoring format needs evidence beyond this goal.
