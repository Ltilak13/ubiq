# Policy and goal usability check

This check asks whether a reader can identify a governing policy, inspect its
evidence, and distinguish evidence freshness from goal completion. It covers the
policy/goal example. The inventory example's behavioral tests are outside this check.

## Scope and provenance

The source baseline is commit `1290f08c4aca051f717683157239eafaa7dab4a2`, inspected
on November 25, 2026. Start at [query documentation](../query.md), then follow its
links. Pin trial results to this revision. If a participant reads a different
revision, record that revision and do not combine the observations silently.

The agent trial uses local Markdown source and linked YAML, JSON, and Python
files. A human may use GitHub Preview, Code, or Raw. Record the actual reading
form for each visit. A source read does not establish that a preview renders
correctly or that switching GitHub views works.

One agent trial is complete. The human response remains pending. The human participant took
part in designing this example. That familiarity limits conclusions about a new
reader. One participant per audience cannot establish population-level usability
or parity. The broader human and agent usability goal remains unassessed here.

## Participant questions

Give each participant these questions without the reviewer rubric below:

1. Which policy governs the domain-schema goal?
2. What evidence supports that declaration?
3. Does fresh evidence mean that the goal is complete?

Ask for answers in the participant's own words, with supporting file locations.
Record files and views visited, repeated visits, failed navigation attempts, and
anything confusing. Record elapsed time only when observed or reported. Do not
estimate time, token use, or reading effort after the trial.

The starting document contains explanations needed to answer the questions.
This measures retrieval and understanding of the documentation, not unaided recall.
Participants must not read this report's rubric before submitting their answers.
Record any exposure to the rubric or prior answers as contamination.

## Reviewer rubric

Keep this section out of the agent's trial prompt. Score each answer as correct,
incomplete, or incorrect. Missing required meaning is incomplete. A contradiction
of the required meaning is incorrect. Record the participant's answer before scoring.
A supporting location must actually contain the cited fact.

| Question | Required meaning | Supporting locations |
| --- | --- | --- |
| 1 | The goal evidence policy governs the domain-schema goal. The relationship runs from policy to goal. | [Policy declaration](../policies/goal-evidence.md); `policies[0].governs` and `relationships[0]` in the [model](../../.ubiq/knowledge/goal-governance.yaml) |
| 2 | The policy text states the relationship, and the model declares it with a source snapshot. Additional snapshots identify the goal, enforcement schema, and goal tests. These sources support declared structure and checks, not semantic proof of completion. | `domains`, `policies`, `goals`, and `relationships` in the [model](../../.ubiq/knowledge/goal-governance.yaml); enforcement explanation in the [policy](../policies/goal-evidence.md) |
| 3 | No. Fresh evidence means the cited source bytes and anchor match. The goal's acceptance assessments remain authoritative, and neither freshness nor a valid relationship establishes completion. | Final paragraph of the [policy](../policies/goal-evidence.md); “Ubiq's policy and goal example” in [query documentation](../query.md) |

Report correct, incomplete, and incorrect answers out of three for each participant.
Also report supported answers out of three. List each missing fact or unsupported
citation. Do not combine the human and agent results into one score.

The narrow trial passes only when all three answers are correct and supported,
with no required meaning lost. Navigation failures and effort remain separate
observations even when the participant eventually answers correctly. Passing
this trial does not satisfy all acceptance criteria of the usability goal.

## Observations

| Evidence | Status | Result |
| --- | --- | --- |
| Local source navigation | Checked at the baseline | Ten selected direct links resolve to existing files; this is not a browser or comprehension test |
| Isolated agent trial | Complete; narrow trial did not pass | Two correct answers, one incomplete answer, zero incorrect answers; all three submitted answers have supporting locations |
| Human response | Pending | No answers, score, elapsed time, or reading-effort result recorded yet |
| Rendered preview interaction | Not tested | No claim about GitHub rendering or view controls |

The source navigation check covered six links from query documentation: policy,
goal, model, schema-validation guide, model schema, and example tests. It also
covered four links from the policy: goal, goal schema, goal tests, and model.
All ten destinations existed. This confirms those source paths only.

For each completed participant trial, append its date, source revision, executor
or participant, prior exposure, reading form, submitted answers, supporting
locations, rubric results, and measured effort. Preserve failed attempts and any
retry reason. Keep unobserved fields explicitly unobserved.

## Agent trial result

One isolated trial ran on November 25, 2026, through the native Codex subagent
`/root/usability_trial` using the OpenAI provider. It read commit
`1290f08c4aca051f717683157239eafaa7dab4a2`. The participant received neither the
prior conversation nor this rubric. No retry occurred.

The following submitted-answer summaries preserve the participant's meaning.
They are not verbatim quotations. Scoring uses the rubric defined before the trial.

| Question | Submitted-answer summary | Cited source locations at the baseline | Assessment |
| --- | --- | --- | --- |
| 1 | The goal evidence policy, `ubiq:goal-evidence-policy`, governs `ubiq:domain-schema-goal` in the goal-assessment domain. | Policy lines 8–9; model lines 8–12 and 32–40 | Correct and supported |
| 2 | The policy explicitly states the relationship. The model records SHA-256 snapshots and anchors for the policy, enforcement schema, and tests. The schema requires assessment fields, a nonempty gap, and implementation/check support for partial assessments. Tests reject a verified assessment, empty support, and an empty gap. These declarations do not prove semantic correctness. The participant did not run checks or recompute hashes. | Model lines 13–22; goal schema lines 25–86 and 93–110; goal tests lines 18–46; policy declaration | Incomplete but supported: the answer omitted the goal source snapshot at model lines 28–31 |
| 3 | No. Freshness does not establish semantic truth or completion. The goal remains in progress, with AC2 and AC5 partial and the other criteria unassessed. | Policy lines 21–24; goal lines 1–58 and acceptance criteria at lines 193–211 | Correct and supported |

Result: **2/3 correct, 1/3 incomplete, 0/3 incorrect**. Supporting locations
corroborate the submitted claims in **3/3 answers**. Support does not compensate
for the omitted fact in question 2. The narrow trial did not pass, and the rubric
was not relaxed after seeing the answers.

The participant read six complete files as raw source using `git show`, grouped
into three shell tool calls:

1. `docs/query.md`
2. `docs/policies/goal-evidence.md`
3. `docs/goals/domain-schema-goal.md`
4. `.ubiq/knowledge/goal-governance.yaml`
5. `.ubiq/schemas/goal.json`
6. `tests/test_goals.py`

The participant reported zero repeated file visits, zero searches, and zero
navigation failures. Elapsed time and token use were not measured. No rendered
preview was used. These counts describe this trial's source access, not the
reading effort of a typical user.

The participant noted that grouped command output lacked filename headers.
That was tool-output friction, not an observed repository documentation defect.
No substantive ambiguity was reported. Reading the goal did not ensure that the
answer inventoried its evidence snapshot. A later trial could test an explicit
evidence-inventory prompt, but this result does not justify changing this trial's
question or rerunning it until it passes.

## Agent trial boundary

The executor is a native Codex subagent using the session's OpenAI provider.
It receives the participant questions and public repository paths in an isolated
context. It does not receive this conversation's answers or the reviewer rubric.
Repository text read through its tools is sent to the OpenAI model for the trial.

The trial budget is one invocation plus at most one retry for a tool failure.
A wrong answer does not authorize a retry. The coordinating agent enforces the
maximum of two invocations. No separate token, cost, or time cap is enforced.
The trial is read-only and must not modify files or invoke another agent.
