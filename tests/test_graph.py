"""Composition edges (`ubiq graph`), their checks (E011, W003, W004), and `ubiq overlap`."""

import json

from test_ubiq import make_repo

from ubiq.cli import main

CFG = """glossary:
  - {glob: "skills/*/SKILL.md", term_field: name, ns: skill}
  - {glob: "skills/_shared/*.md", term_field: name, ns: part}
docs: ["skills/**/*.md"]
ref_fields: [uses]
edges:
  invoke: {blocked_by: disable-model-invocation}
  install: ["skills/*/SKILL.md"]
"""
SHARED = ("Read repository instructions, git status, remotes, and worktrees "
          "before you change the checkout or push anything.\n")


def skill(name, body="", uses=(), user_only=False, routes=()):
    meta = f"name: {name}\n"
    if uses:
        meta += f"uses: [{', '.join(uses)}]\n"
    if routes:
        meta += f"routes: [{', '.join(routes)}]\n"
    if user_only:
        meta += "disable-model-invocation: true\n"
    return f"---\n{meta}---\n\n{body}\n"


def part(name, body, inputs=""):
    return f"---\nname: {name}\n{inputs}---\n\n{body}\n"


def run(tmp_path, capsys, *argv):
    status = main([*argv, "--root", str(tmp_path), "--json"])
    return status, json.loads(capsys.readouterr().out)


def repo(tmp_path, docs, cfg=CFG):
    return make_repo(tmp_path, {}, docs, config=cfg)


def test_invoke_and_include_edges_with_callers(tmp_path, capsys):
    repo(tmp_path, {
        "skills/push/SKILL.md": skill("push", "Follow [checkout](../_shared/checkout.md)."),
        "skills/push/notes.md": "See [checkout](../_shared/checkout.md) again.\n",
        "skills/ship/SKILL.md": skill("ship", "Ship it.", uses=["push"]),
        "skills/_shared/checkout.md": part("checkout", "Check out the branch."),
        "skills/other/SKILL.md": skill("other", "Read [push](../push/SKILL.md)."),
    })
    status, out = run(tmp_path, capsys, "graph")
    assert status == 0
    edges = {(e["kind"], e["source"], e["target"], e["file"]) for e in out["edges"]}
    assert edges == {
        ("invoke", "skill:ship", "skill:push", "skills/ship/SKILL.md"),
        ("include", "skill:push", "part:checkout", "skills/push/SKILL.md"),
        # A sibling file belongs to the one record in its directory.
        ("include", "skill:push", "part:checkout", "skills/push/notes.md"),
    }  # a link to a skill (not a part) is a reference, not an include

    status, out = run(tmp_path, capsys, "graph", "part:checkout", "--callers")
    assert {(e["source"], e["target"]) for e in out["edges"]} == {
        ("skill:push", "part:checkout"), ("skill:ship", "skill:push")}
    status, out = run(tmp_path, capsys, "graph", "part:checkout", "--callers", "--depth", "1")
    assert {e["source"] for e in out["edges"]} == {"skill:push"}
    status, out = run(tmp_path, capsys, "graph", "nothing")
    assert status == 1 and "no record" in out["error"]


def check(tmp_path, capsys):
    status, out = run(tmp_path, capsys, "check")
    return status, [(d["code"], d["message"]) for d in out["diagnostics"]
                    if d["code"] in ("E011", "E012", "W003", "W004", "W005")]


def test_include_cycle_fails(tmp_path, capsys):
    repo(tmp_path, {
        "skills/_shared/a.md": part("a", "Then [b](b.md)."),
        "skills/_shared/b.md": part("b", "Then [a](a.md)."),
        "skills/x/SKILL.md": skill("x", "Follow [a](../_shared/a.md)."),
    })
    status, found = check(tmp_path, capsys)
    assert status == 1
    assert ("E011", "include cycle part:a -> part:b -> part:a") in found


def test_invoking_a_user_only_skill_warns(tmp_path, capsys):
    repo(tmp_path, {
        "skills/lead/SKILL.md": skill("lead", "Delegate.", uses=["spec", "tdd"]),
        "skills/spec/SKILL.md": skill("spec", "Write it.", user_only=True),
        "skills/tdd/SKILL.md": skill("tdd", "Test first."),
    })
    status, found = check(tmp_path, capsys)
    assert status == 0
    assert found == [("W003", ("skill:lead invokes skill:spec, which sets "
                               "disable-model-invocation: true — include its file or allow "
                               "model invocation"))]


def test_links_that_resolve_in_only_one_layout_warn(tmp_path, capsys):
    repo(tmp_path, {
        # Source tree only: skills/_shared is not installed next to the skills.
        "skills/a/SKILL.md": skill("a", "Follow [checkout](../_shared/checkout.md)."),
        "skills/_shared/checkout.md": part("checkout", "Check out."),
        # Installed layout only: b installs next to c, but in the source tree
        # they sit in different buckets.
        # (A missing record link is already E002, so this one targets a plain file.)
        "skills/b/SKILL.md": skill("b", "Read [c](../c/guide.md) and [notes](notes.md)."),
        "skills/b/notes.md": "Local file.\n",
        "skills/x/c/SKILL.md": skill("c", "C."),
        "skills/x/c/guide.md": "Guide.\n",
    }, cfg=CFG.replace('install: ["skills/*/SKILL.md"]',
                       'install: ["skills/*/SKILL.md", "skills/x/*/SKILL.md"]')
             .replace('  - {glob: "skills/_shared/*.md"',
                      '  - {glob: "skills/x/*/SKILL.md", term_field: name, ns: skill}\n'
                      '  - {glob: "skills/_shared/*.md"'))
    status, found = check(tmp_path, capsys)
    assert status == 0
    assert found == [
        ("W004", "link ../_shared/checkout.md leaves a/ and resolves only in the source tree"),
        ("W004", "link ../c/guide.md leaves b/ and resolves only in the installed layout"),
    ]


def test_invoke_fields_must_be_ref_fields(tmp_path, capsys):
    repo(tmp_path, {"skills/a/SKILL.md": skill("a")},
         cfg=CFG.replace("{blocked_by: disable-model-invocation}", "{fields: [calls]}"))
    status, out = run(tmp_path, capsys, "check")
    assert status == 1
    assert out["diagnostics"][0]["code"] == "E008"
    assert "ref_fields" in out["diagnostics"][0]["message"]


def test_overlap_clusters_repeated_prose_across_records(tmp_path, capsys):
    repo(tmp_path, {
        "skills/a/SKILL.md": skill("a", "1. " + SHARED + "\nDo the a thing with care today."),
        "skills/b/SKILL.md": skill("b", "- " + SHARED.replace("git", "Git")),
        "skills/c/SKILL.md": skill("c", "Follow [pr](../_shared/pr.md).\n\n" + SHARED),
        "skills/_shared/pr.md": part("pr", SHARED),
        "skills/d/SKILL.md": skill("d", "Read instructions and status before you push anything "
                                        "to a remote branch that other people share."),
    })
    status, out = run(tmp_path, capsys, "overlap")
    assert status == 0
    assert out["count"] == 1
    cluster = out["clusters"][0]
    assert cluster["records"] == ["part:pr", "skill:a", "skill:b", "skill:c"]
    assert cluster["restates_include"] is True  # c includes pr and restates it
    assert [(b["file"], b["line"]) for b in cluster["blocks"]] == [
        ("skills/_shared/pr.md", 5), ("skills/a/SKILL.md", 5),
        ("skills/b/SKILL.md", 5), ("skills/c/SKILL.md", 7)]

    status, out = run(tmp_path, capsys, "overlap", "--min-similarity", "1")
    assert out["count"] == 1  # containment still joins an exact restatement


def test_shared_folders_and_the_root_do_not_own_other_docs(tmp_path, capsys):
    repo(tmp_path, {
        "README.md": skill("top"),
        "docs/guide.md": skill("guide"),
        "docs/x.md": "Follow [checkout](../skills/_shared/checkout.md).\n",
        "x.md": "Follow [checkout](skills/_shared/checkout.md).\n",
        "skills/_shared/checkout.md": part("checkout", "Check out."),
        "skills/a/SKILL.md": skill("a", "See [guide](../../docs/guide.md) and [top](../../README.md)."),
    }, cfg=CFG.replace('docs: ["skills/**/*.md"]', 'docs: ["**/*.md"]')
              .replace("glossary:\n", 'glossary:\n  - {glob: "README.md", term_field: name, ns: skill}\n'
                       '  - {glob: "docs/guide.md", term_field: name, ns: skill}\n'))
    status, out = run(tmp_path, capsys, "graph")
    assert status == 0
    assert out["edges"] == []


ROUTED = CFG.replace("ref_fields: [uses]", "ref_fields: [uses, routes]").replace(
    "edges:\n", "edges:\n  route: {fields: [routes]}\n")


def test_route_edges_are_shown_but_not_followed(tmp_path, capsys):
    repo(tmp_path, {
        "skills/a/SKILL.md": skill("a", "Run b.", uses=["b"]),
        "skills/b/SKILL.md": skill("b", "B."),
        # c is not for this; it sends the reader to a.
        "skills/c/SKILL.md": skill("c", "Not for that; use a.", routes=["a"]),
        "skills/d/SKILL.md": skill("d", "Run c.", uses=["c"]),
    }, cfg=ROUTED)
    status, out = run(tmp_path, capsys, "graph")
    assert status == 0
    assert {(e["kind"], e["source"], e["target"]) for e in out["edges"]} == {
        ("invoke", "skill:a", "skill:b"), ("route", "skill:c", "skill:a"),
        ("invoke", "skill:d", "skill:c")}
    _, out = run(tmp_path, capsys, "graph", "b", "--callers")
    # c routes to a without calling it, so the walk stops at c and never reaches d.
    assert [(e["source"], e["target"]) for e in out["edges"]] == [
        ("skill:a", "skill:b"), ("skill:c", "skill:a")]
    _, out = run(tmp_path, capsys, "graph", "--kind", "route")
    assert [e["kind"] for e in out["edges"]] == ["route"]


def test_a_field_cannot_both_invoke_and_route(tmp_path, capsys):
    repo(tmp_path, {"skills/a/SKILL.md": skill("a")},
         cfg=ROUTED.replace("{blocked_by: disable-model-invocation}",
                            "{fields: [uses, routes]}"))
    status, out = run(tmp_path, capsys, "check")
    assert status == 1
    assert out["diagnostics"][0]["code"] == "E008"
    assert "both invoke and route" in out["diagnostics"][0]["message"]


DRIFT = ROUTED.replace("edges:\n", "delimiters: [{pattern: /, only_known: true}]\n"
                       'overlays: ["overlays/*.md"]\n'
                       "edges:\n  drift: {ns: [skill]}\n")


def test_drift_between_references_and_declared_edges(tmp_path, capsys):
    repo(tmp_path, {
        "skills/lead/SKILL.md": skill(
            "lead",
            "Run /tdd, then [[review]]. Write it [[test-first]].\n\n"
            "Not for tickets; use [[tickets]].\n\n"
            # Plain words never count as undeclared: "research" is prose here.
            "Do some research first. Finish with the ship-it skill.\n",
            uses=["tdd", "ship-it", "spec"], routes=["tickets"]),
        "skills/lead/notes.md": "Also read [checkout](../_shared/checkout.md).\n",
        # Overlay prose describes edges; it is not the skill's own text.
        "overlays/lead.md": "---\nsource: skills/lead/SKILL.md\n---\n\n[[lead]] uses [[spec]].\n",
        "skills/_shared/checkout.md": part("checkout", "Check out."),
        "skills/tdd/SKILL.md": skill("tdd", "Test."),
        "skills/review/SKILL.md": skill("review", "Review."),
        "skills/tickets/SKILL.md": skill("tickets", "Tickets."),
        "skills/research/SKILL.md": skill("research", "Research."),
        "skills/ship-it/SKILL.md": skill("ship-it", "Ship."),
        "skills/spec/SKILL.md": skill("spec", "Spec."),
        # Naming a caller is not drift: ship-it's edge comes from lead.
        "skills/ship-it/notes.md": "Called by [[lead]].\n",
        # A glossary definition contrasting skills is not a skill.
        "glossary/tdd-term.md": "---\nterm: test-first\nuses: [spec]\n---\n\nSee [[tdd]] and [[review]].\n",
    }, cfg=DRIFT.replace("glossary:\n", 'glossary:\n  - "glossary/*.md"\n')
                .replace('docs: ["skills/**/*.md"]', 'docs: ["skills/**/*.md", "glossary/*.md"]'))
    status, found = check(tmp_path, capsys)
    assert status == 0
    assert [f for f in found if f[0] == "W005"] == [
        ("W005", "skill:lead declares invoke skill:spec but never names it"),
        ("W005", ("skill:lead references skill:review but declares no edge to it "
                  "— add it to uses or routes")),
    ]


INPUTS = "inputs:\n  mode: [new, existing, branch]\n"


def test_includes_name_a_declared_input(tmp_path, capsys):
    repo(tmp_path, {
        "skills/_shared/checkout.md": part("checkout", "Check out.", INPUTS),
        "skills/_shared/bad.md": part("bad", "Bad.", "inputs: [new, existing]\n"),
        "skills/_shared/scope.md": part("scope", "Scope."),
        "skills/ok/SKILL.md": skill(
            "ok", "1. Follow [checkout](../_shared/checkout.md) in `existing` mode.\n"
                  "2. Apply [scope](../_shared/scope.md), then [checkout](../_shared/checkout.md)"
                  " in `new` mode."),
        "skills/typo/SKILL.md": skill(
            "typo", "Follow [checkout](../_shared/checkout.md) in `exist` mode.\n"
                    "Later, follow [checkout](../_shared/checkout.md) in `new` mode."),
        # The mode after the next link belongs to that link, not this one.
        "skills/none/SKILL.md": skill(
            "none", "Follow [checkout](../_shared/checkout.md), then [bad](../_shared/bad.md) in `new` mode."),
    })
    status, found = check(tmp_path, capsys)
    assert status == 1
    assert sorted(f for f in found if f[0] == "E012") == [
        ("E012", "part:bad inputs: expected a mapping of input names to lists of values"),
        ("E012", ("skill:none includes part:checkout without a mode; write `<value>` mode "
                  "after the link: new, existing, branch")),
        ("E012", ("skill:typo includes part:checkout with mode `exist`; expected one of "
                  "new, existing, branch")),
    ]


SECTION = "# To tickets\n\n### 3. Draft vertical slices\n\nSlice it.\n"
UPSTREAM = 'glossary:\n  - {glob: "skills/*/*/SKILL.md", term_field: name, ns: skill}\n' \
           'docs: ["skills/**/*.md"]\nedges:\n  install: ["skills/*/*/SKILL.md"]\n'


def two_repos(tmp_path, external):
    (tmp_path / "upstream").mkdir()
    (tmp_path / "local").mkdir()
    upstream = make_repo(tmp_path / "upstream", {}, {
        "skills/engineering/to-tickets/SKILL.md": skill("to-tickets", SECTION),
        "skills/engineering/review/SKILL.md": skill("review", "Upstream review."),
    }, config=UPSTREAM)
    local = repo(tmp_path / "local", {
        "skills/breakdown/SKILL.md": skill(
            "breakdown",
            "Read [section 3](../to-tickets/SKILL.md#3-draft-vertical-slices).\n\n"
            "Read [a lost section](../to-tickets/SKILL.md#4-quiz).\n\n"
            # A local skill wins the installed name over the upstream one.
            "Run [review](../review/SKILL.md#steps-1).\n\n"
            "Read [gone](../gone/SKILL.md).\n"),
        "skills/review/SKILL.md": skill("review", "Local review.\n\n## Steps\n\nGo.\n\n## Steps\n\nAgain."),
    }, cfg=CFG.replace('install: ["skills/*/SKILL.md"]',
                       f'install: ["skills/*/SKILL.md"]\n  external: [{external}]'))
    return upstream, local


def test_links_into_another_repository_resolve_once_installed(tmp_path, capsys):
    two_repos(tmp_path, "../upstream")
    status, out = run(tmp_path / "local", capsys, "check")
    found = [(d["code"], d["message"]) for d in out["diagnostics"] if d["code"][0] in "EW"
             and d["code"] != "W001"]
    # Only the link to a name nobody installs is E002; links into the other
    # repository are W004's to check, fragments included.
    assert status == 1
    assert found == [
        ("E002", "unresolved reference [gone](../gone/SKILL.md) — no defining record"),
        ("W004", "link ../to-tickets/SKILL.md#4-quiz names no heading in to-tickets/SKILL.md"),
    ]


def test_an_unreadable_external_repository_leaves_its_links_unchecked(tmp_path, capsys):
    two_repos(tmp_path, "../missing")
    status, out = run(tmp_path / "local", capsys, "check")
    found = [(d["code"], d["message"]) for d in out["diagnostics"] if d["code"] != "W001"]
    assert status == 0
    assert found == [("W004", (f"external repository {tmp_path / 'local' / '../missing'} "
                               "was not found; links into it are not checked"))]


def test_callers_of_one_part_are_not_overlap(tmp_path, capsys):
    label = "the shared repository checkout procedure for pull requests"
    repo(tmp_path, {
        "skills/_shared/checkout.md": part("checkout", "Check out."),
        "skills/a/SKILL.md": skill("a", f"Follow [{label}](../_shared/checkout.md) now."),
        "skills/b/SKILL.md": skill("b", f"Then run [{label}](../_shared/checkout.md) first."),
        "skills/c/SKILL.md": skill("c", f"Then run [{label}](../c/notes.md) first."),
        "skills/c/notes.md": "Notes.\n",
    })
    # The include link is the call; only c, whose link is not an include, keeps
    # the label as prose, and no other block shares it.
    _, out = run(tmp_path, capsys, "overlap", "--unit", "line", "--min-similarity", "0.3")
    assert out["count"] == 0
