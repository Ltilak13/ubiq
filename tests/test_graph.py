"""Composition edges (`ubiq graph`), their checks (E011, W003, W004), and `ubiq overlap`."""

import json
from pathlib import Path

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
                    if d["code"] in ("E011", "E012", "W003", "W004", "W005", "W007")]


def test_include_cycle_fails(tmp_path, capsys):
    repo(tmp_path, {
        "skills/_shared/a.md": part("a", "Then [b](b.md)."),
        "skills/_shared/b.md": part("b", "Then [a](a.md)."),
        "skills/x/SKILL.md": skill("x", "Follow [a](../_shared/a.md)."),
    })
    status, found = check(tmp_path, capsys)
    assert status == 1
    assert ("E011", "include cycle part:a -> part:b -> part:a") in found


def test_direct_self_include_fails(tmp_path, capsys):
    repo(tmp_path, {
        "skills/_shared/a.md": part("a", "Follow [a](a.md)."),
    })
    status, found = check(tmp_path, capsys)
    assert status == 1
    assert ("E011", "include cycle part:a -> part:a") in found


def test_self_references_and_local_fragments_are_not_dependencies(tmp_path, capsys):
    repo(tmp_path, {
        "skills/a/SKILL.md": skill("a", "See [section](SKILL.md#section).\n\n# Section\n",
                                    uses=["a"], user_only=True),
        "skills/_shared/b.md": part("b", "See [section](#section).\n\n# Section\n"),
    })
    status, found = check(tmp_path, capsys)
    assert status == 0
    assert found == []
    status, out = run(tmp_path, capsys, "graph")
    assert status == 0
    assert out["edges"] == []


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


def two_repos(tmp_path, external, cfg=CFG):
    (tmp_path / "upstream").mkdir(exist_ok=True)
    (tmp_path / "local").mkdir(exist_ok=True)
    upstream = make_repo(tmp_path / "upstream", {}, {
        # Users invoke to-tickets themselves, so breakdown reads one of its sections.
        "skills/engineering/to-tickets/SKILL.md": skill("to-tickets", SECTION, user_only=True),
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
        "skills/plan/SKILL.md": skill("plan", "Run [[breakdown]].", uses=["breakdown"]),
    }, cfg=cfg.replace('install: ["skills/*/SKILL.md"]',
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


def test_installed_fragments_preserve_entity_generated_suffixes(tmp_path, capsys):
    repo(tmp_path, {
        # A file without frontmatter, since E013 checks fragments into the others.
        "skills/a/SKILL.md": skill("a", "[space](../b/notes.md#section&#32;)\n"
                                  "[bracket](../b/notes.md#section&gt;)\n"),
        "skills/b/SKILL.md": skill("b"),
        "skills/b/notes.md": "# Section\n",
    })
    _, found = check(tmp_path, capsys)
    assert found == [
        ("W004", "link ../b/notes.md#section%20 names no heading in b/notes.md"),
        ("W004", "link ../b/notes.md#section%3E names no heading in b/notes.md"),
    ]


def test_installed_fragments_may_name_frontmatter_fields(tmp_path, capsys):
    repo(tmp_path, {
        "skills/a/SKILL.md": skill("a", "Run [b](../b/SKILL.md#name), [c](../b/SKILL.md#nmae), "
                                   "and [sec](../b/SKILL.md#section).\n"),
        "skills/b/SKILL.md": skill("b", "# Section\n"),
    })
    _, out = run(tmp_path, capsys, "check")
    # E013 reports the misspelled field, so W004 does not report it again.
    message = "field value [c](../b/SKILL.md#nmae) — no field or heading 'nmae' in ../b/SKILL.md"
    assert [(d["code"], d["message"]) for d in out["diagnostics"] if d["code"] != "W001"] == [
        ("E013", message)]


def test_an_unreadable_external_repository_leaves_its_links_unchecked(tmp_path, capsys):
    two_repos(tmp_path, "../missing")
    status, out = run(tmp_path / "local", capsys, "check")
    found = [(d["code"], d["message"]) for d in out["diagnostics"] if d["code"] != "W001"]
    assert status == 0
    assert found == [("W004", (f"external repository {tmp_path / 'local' / '../missing'} "
                               "was not found; links into it are not checked"))]
    status, out = run(tmp_path / "local", capsys, "graph")
    assert status == 0
    assert [(e["source"], e["target"]) for e in out["edges"]] == [("skill:plan", "skill:breakdown")]


def test_a_link_into_another_repository_is_an_include_edge(tmp_path, capsys):
    two_repos(tmp_path, "../upstream")
    local = tmp_path / "local"
    status, out = run(local, capsys, "graph")
    assert status == 0
    # The link to review lands on the local skill, and a link to a skill here is
    # a reference, so neither review makes an edge.
    assert [(e["kind"], e["source"], e["target"], e["file"], e["line"]) for e in out["edges"]] == [
        ("invoke", "skill:plan", "skill:breakdown", "skills/plan/SKILL.md", 3),
        ("include", "skill:breakdown", "upstream/skill:to tickets", "skills/breakdown/SKILL.md", 5),
        ("include", "skill:breakdown", "upstream/skill:to tickets", "skills/breakdown/SKILL.md", 7)]
    assert main(["graph", "breakdown", "--root", str(local)]) == 0
    assert ("skill:breakdown -include-> upstream/skill:to tickets  skills/breakdown/SKILL.md:5"
            in capsys.readouterr().out)

    # Nothing here defines to-tickets, so the name reaches the other repository.
    _, out = run(local, capsys, "graph", "to-tickets", "--callers")
    assert out["target"] == "upstream/skill:to tickets"
    assert sorted({(e["source"], e["target"]) for e in out["edges"]}) == [
        ("skill:breakdown", "upstream/skill:to tickets"), ("skill:plan", "skill:breakdown")]
    # A name defined here wins, as its directory does once installed.
    _, out = run(local, capsys, "graph", "review")
    assert out["target"] == "skill:review"
    _, out = run(local, capsys, "graph", "upstream/review")
    assert out["target"] == "upstream/skill:review"

    # It is an include, not an invoke: to-tickets being user-only is no W003, and
    # the link names the record, so drift has nothing to report about it. Only
    # the section link to the local review is a reference without an edge.
    drift = CFG.replace("edges:\n", "edges:\n  drift: {ns: [skill]}\n")
    review = "skill:breakdown references skill:review but declares no edge to it — add it to uses"
    for cfg, found in ((CFG, []), (drift, [("W005", review)])):
        two_repos(tmp_path, "../upstream", cfg)
        _, out = run(local, capsys, "check")
        assert [(d["code"], d["message"]) for d in out["diagnostics"]
                if d["code"] in ("W003", "W005")] == found


def test_external_repositories_with_one_directory_name_keep_distinct_records(tmp_path, capsys):
    two_repos(tmp_path, "../upstream, ../other/upstream")
    (tmp_path / "other/upstream").mkdir(parents=True)
    other = make_repo(tmp_path / "other/upstream", {}, {
        "skills/engineering/extra/SKILL.md": skill("extra", "# Extra")}, config=UPSTREAM)
    (tmp_path / "local/skills/breakdown/notes.md").write_text("Read [extra](../extra/SKILL.md).\n")
    _, out = run(tmp_path / "local", capsys, "graph", "--kind", "include")
    assert {e["target"] for e in out["edges"]} == {
        f"{tmp_path.resolve()}/upstream/skill:to tickets", f"{other.resolve()}/skill:extra"}


def test_an_include_link_that_resolves_nowhere_fails_across_repositories(tmp_path, capsys):
    """Another repository's directories never excuse a missing part (spec guarantee)."""
    for name in ("upstream", "local"):
        (tmp_path / name).mkdir()
    make_repo(tmp_path / "upstream", {}, {
        "skills/x/_shared/SKILL.md": skill("shared", "Upstream part.")}, config=UPSTREAM)
    docs = {"skills/a/SKILL.md": skill(
        "a", "Follow [gone](../_shared/gone.md).\n\nFollow [there](../_shared/SKILL.md).\n\n"
             "Read [theirs](../theirs/SKILL.md).\n")}
    unresolved = "unresolved reference {} — no defining record"
    for external, links in (
            # Unreadable: other links stay unchecked, include links do not.
            ("../missing", ["[gone](../_shared/gone.md)", "[there](../_shared/SKILL.md)"]),
            # Readable: an include link that resolves once installed is W004's.
            ("../upstream", ["[gone](../_shared/gone.md)", "[theirs](../theirs/SKILL.md)"])):
        repo(tmp_path / "local", docs, cfg=CFG.replace(
            'install: ["skills/*/SKILL.md"]', f'install: ["skills/*/SKILL.md"]\n  external: [{external}]'))
        status, out = run(tmp_path / "local", capsys, "check")
        assert status == 1, external
        assert sorted(d["message"] for d in out["diagnostics"] if d["code"] == "E002") == [
            unresolved.format(link) for link in links], external


def with_severity(cfg, kind, value):
    """`cfg` with `edges.<kind>.severity` set."""
    sections = {"invoke": "{blocked_by: disable-model-invocation", "route": "{fields: [routes]"}
    if kind in sections:
        return cfg.replace(sections[kind], f"{sections[kind]}, severity: {value}")
    return cfg.replace("edges:\n", f"edges:\n  {kind}: {{severity: {value}}}\n")


def test_edge_kind_severity_sets_its_constraints(tmp_path, capsys):
    repo(tmp_path, {
        "skills/_shared/a.md": part("a", "Then [b](b.md)."),
        "skills/_shared/b.md": part("b", "Then [a](a.md)."),
        "skills/_shared/checkout.md": part("checkout", "Check out.", INPUTS),
        "skills/lead/SKILL.md": skill(
            "lead", "Follow [checkout](../_shared/checkout.md), then [a](../_shared/a.md). "
                    "Ask [[review]].", uses=["spec"], routes=["tickets"]),
        "skills/spec/SKILL.md": skill("spec", "Spec.", user_only=True),
        "skills/tickets/SKILL.md": skill("tickets", "Tickets."),
        "skills/review/SKILL.md": skill("review", "Review."),
    }, cfg=DRIFT)

    def kind_of(code, message):
        if code in ("E011", "E012"):
            return "include"
        if code == "W003" or "declares invoke" in message:
            return "invoke"
        return "route" if "declares route" in message else None

    _, out = run(tmp_path, capsys, "check")
    default = {(d["code"], d["message"]): d["severity"] for d in out["diagnostics"]
               if d["code"] in ("E011", "E012", "W003", "W004", "W005")}
    # Every kind has a constraint here, and W004 and a missing edge (W005) have none.
    assert sorted({kind_of(*key) or "" for key in default}) == ["", "include", "invoke", "route"]
    for kind in ("include", "invoke", "route"):
        for value in ("error", "warn", "off"):
            (tmp_path / "ubiq.yaml").write_text(with_severity(DRIFT, kind, value))
            _, out = run(tmp_path, capsys, "check")
            found = {(d["code"], d["message"]): d["severity"] for d in out["diagnostics"]
                     if (d["code"], d["message"]) in default}
            level = "error" if value == "error" else "warning"
            assert found == {key: level if kind_of(*key) == kind else severity
                             for key, severity in default.items()
                             if not (value == "off" and kind_of(*key) == kind)}, (kind, value)
    (tmp_path / "ubiq.yaml").write_text(with_severity(DRIFT, "invoke", "error"))
    assert main(["check", "--root", str(tmp_path)]) == 1
    assert "W003 (error) skill:lead invokes skill:spec" in capsys.readouterr().out


def test_an_invoke_cycle_is_allowed_and_walks_end(tmp_path, capsys):
    # Two workflows that hand off to each other.
    repo(tmp_path, {
        "skills/plan/SKILL.md": skill("plan", "Hand off to build.", uses=["build"]),
        "skills/build/SKILL.md": skill("build", "Hand back to plan.", uses=["plan"]),
    })
    status, found = check(tmp_path, capsys)
    assert status == 0 and found == []
    for view in ([], ["--callers"]):
        status, out = run(tmp_path, capsys, "graph", "plan", *view)
        assert sorted((e["source"], e["target"]) for e in out["edges"]) == [
            ("skill:build", "skill:plan"), ("skill:plan", "skill:build")]


def test_nested_includes(tmp_path, capsys):
    repo(tmp_path, {
        "skills/ship/SKILL.md": skill("ship", "Follow [publish](../_shared/publish.md)."),
        "skills/_shared/publish.md": part(
            "publish", "Follow [checkout](checkout.md) in `existing` mode, then push."),
        "skills/_shared/checkout.md": part("checkout", "Check out.", INPUTS),
    })
    status, found = check(tmp_path, capsys)
    # A part that includes a part is no cycle, and its include names an input too.
    assert status == 0
    assert [f for f in found if f[0] != "W004"] == []
    status, out = run(tmp_path, capsys, "graph", "ship")
    assert [(e["source"], e["target"]) for e in out["edges"]] == [
        ("skill:ship", "part:publish"), ("part:publish", "part:checkout")]
    status, out = run(tmp_path, capsys, "graph", "ship", "--depth", "1")
    assert [e["target"] for e in out["edges"]] == ["part:publish"]
    status, out = run(tmp_path, capsys, "graph", "checkout", "--callers")
    assert [e["source"] for e in out["edges"]] == ["part:publish", "skill:ship"]


def test_overlap_threshold_boundary(tmp_path, capsys):
    words = [f"word{i}" for i in range(20)]
    near = [*words[:10], "other", *words[11:]]
    repo(tmp_path, {
        "skills/a/SKILL.md": skill("a", " ".join(words)),
        "skills/b/SKILL.md": skill("b", " ".join(near)),
    })
    # 17 shingles each; changing one word changes 4, so Jaccard is 13/21 = 0.619
    # and containment 13/17 = 0.76 stays under its own 0.8 bar.
    _, out = run(tmp_path, capsys, "overlap", "--min-similarity", "0.61")
    assert out["count"] == 1
    _, out = run(tmp_path, capsys, "overlap", "--min-similarity", "0.62")
    assert out["count"] == 0


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


GRILL = 'Call the Skill tool twice, for "grilling" and "domain-modeling".'
BOTH = ["grilling", "domain-modeling"]


def test_composite_suggestion_requires_each_callers_full_coverage(tmp_path, capsys):
    first = "Read repository instructions and inspect every changed source file before writing code."
    second = "Publish the release artifact after verifying its checksum against the signed manifest."
    repo(tmp_path, {
        "skills/step/SKILL.md": skill("step", "Work."),
        "skills/composite/SKILL.md": skill("composite", first + "\n\n" + second, uses=["step"]),
        "skills/full/SKILL.md": skill("full", first + " " + second, uses=["step"]),
        "skills/partial/SKILL.md": skill("partial", first, uses=["step"]),
    })
    _, out = run(tmp_path, capsys, "overlap")
    suggestion = next(r for c in out["clusters"] for r in c["restates_composite"]
                      if r["composite"] == "skill:composite")
    assert suggestion["records"] == ["skill:full"]


def test_overlap_labels_a_restated_composite(tmp_path, capsys):
    gwd = tmp_path / "skills/grill-with-docs/SKILL.md"
    repo(tmp_path, {
        "skills/grilling/SKILL.md": skill("grilling", "Ask."),
        "skills/domain-modeling/SKILL.md": skill("domain-modeling", "Name."),
        "skills/grill-with-docs/SKILL.md": skill("grill-with-docs", GRILL, uses=BOTH,
                                                 user_only=True),
        # They hold every edge of grill-with-docs and restate all of its text.
        "skills/triage/SKILL.md": skill("triage", "Grill if needed: " + GRILL + "\n\n"
                                        "Move issues through a small state machine of triage "
                                        "roles and their labels.", uses=BOTH),
        "skills/wayfinder/SKILL.md": skill("wayfinder", "Always " + GRILL + "\n\n"
                                           "Chart a map of open decisions before any ticket is "
                                           "worked by an agent.", uses=BOTH),
        # Holds only one of its edges.
        "skills/teach/SKILL.md": skill("teach", GRILL + "\n\nExplain one concept at a time and "
                                       "check what the learner already knows first.",
                                       uses=["grilling"]),
        # Already invokes it.
        "skills/lead/SKILL.md": skill("lead", GRILL, uses=["grill-with-docs", *BOTH]),
        # Restated in full but invokes nothing, so it is not a composite.
        "skills/echo/SKILL.md": skill("echo", GRILL),
    })
    _, out = run(tmp_path, capsys, "overlap")
    assert out["count"] == 1
    cluster = out["clusters"][0]
    assert len(cluster["records"]) == 6
    assert cluster["restates_composite"] == [
        {"composite": "skill:grill with docs", "records": ["skill:triage", "skill:wayfinder"],
         "blocked": True}]

    assert main(["overlap", "--root", str(tmp_path)]) == 0
    assert ("(skill:triage, skill:wayfinder could invoke skill:grill with docs, but it sets "
            "disable-model-invocation: true (W003))") in capsys.readouterr().out

    gwd.write_text(skill("grill-with-docs", GRILL, uses=BOTH), encoding="utf-8")
    _, out = run(tmp_path, capsys, "overlap")
    assert [c["blocked"] for c in out["clusters"][0]["restates_composite"]] == [False]


INFORMATIONAL = DRIFT.replace("ref_fields: [uses, routes]", "ref_fields: [uses, routes, references]").replace(
    "edges:\n", "edges:\n  reference: {fields: [references]}\n")


def test_informational_references_are_validated_but_not_dependencies(tmp_path, capsys):
    repo(tmp_path, {
        "skills/a/SKILL.md": skill("a", "Example: [[b]]."),
        "skills/b/SKILL.md": skill("b", "Run [[c]].", uses=["c"], user_only=True),
        "skills/c/SKILL.md": skill("c", "C."),
        "overlays/a.md": "---\nsource: skills/a/SKILL.md\nreferences: [b]\n---\n",
    }, cfg=INFORMATIONAL)
    status, out = run(tmp_path, capsys, "check")
    assert status == 0
    assert not [d for d in out["diagnostics"] if d["code"] in ("W003", "W005")]
    _, out = run(tmp_path, capsys, "graph", "a")
    assert [(e["kind"], e["target"]) for e in out["edges"]] == [("reference", "skill:b")]
    _, out = run(tmp_path, capsys, "graph", "c", "--callers")
    assert [(e["kind"], e["source"]) for e in out["edges"]] == [
        ("invoke", "skill:b"), ("reference", "skill:a")]
    # Classification does not hide misspelled targets or stale declarations.
    sidecar = tmp_path / "overlays/a.md"
    sidecar.write_text(sidecar.read_text().replace("[b]", "[missing]"))
    status, out = run(tmp_path, capsys, "check")
    assert status == 1 and any(d["code"] == "E006" for d in out["diagnostics"])
    sidecar.write_text(sidecar.read_text().replace("[missing]", "[c]"))
    _, out = run(tmp_path, capsys, "check")
    assert any(d["code"] == "W005" and "declares reference" in d["message"]
               for d in out["diagnostics"])
    # A real invocation still enforces the target's invocation restriction.
    sidecar.write_text(sidecar.read_text().replace("references: [c]", "uses: [b]"))
    _, out = run(tmp_path, capsys, "check")
    assert any(d["code"] == "W003" for d in out["diagnostics"])


def test_reference_fields_require_resolution_and_unique_classification(tmp_path, capsys):
    for fields in ("[missing]", "[routes]"):
        repo(tmp_path, {"skills/a/SKILL.md": skill("a")},
             cfg=INFORMATIONAL.replace("reference: {fields: [references]}",
                                       f"reference: {{fields: {fields}}}"))
        status, out = run(tmp_path, capsys, "check")
        assert status == 1 and out["diagnostics"][0]["code"] == "E008"


def test_reference_classification_cannot_share_explicit_invoke_field(tmp_path, capsys):
    cfg = INFORMATIONAL.replace("{blocked_by: disable-model-invocation}", "{fields: [uses]}")
    cfg = cfg.replace("reference: {fields: [references]}", "reference: {fields: [uses]}")
    repo(tmp_path, {}, cfg=cfg)
    status, out = run(tmp_path, capsys, "check")
    assert status == 1 and out["diagnostics"][0]["code"] == "E008"


def test_reference_severity_preserves_target_validation(tmp_path, capsys):
    for severity in ("warn", "error", "off"):
        cfg = INFORMATIONAL.replace("reference: {fields: [references]}",
                                    f"reference: {{fields: [references], severity: {severity}}}")
        repo(tmp_path, {
            "skills/a/SKILL.md": skill("a", "A."),
            "skills/b/SKILL.md": skill("b", "B."),
            "overlays/a.md": "---\nsource: skills/a/SKILL.md\nreferences: [b, missing]\n---\n",
        }, cfg=cfg)
        status, out = run(tmp_path, capsys, "check")
        assert status == 1 and any(d["code"] == "E006" for d in out["diagnostics"])
        drift = [d for d in out["diagnostics"] if d["code"] == "W005"]
        if severity == "off":
            assert not drift
        else:
            assert len(drift) == 1 and drift[0]["severity"] == ("warning" if severity == "warn" else "error")


def test_bundled_skills_include_schema_workflow(capsys):
    root = Path(__file__).resolve().parents[1]
    status, out = run(root, capsys, "graph")
    assert status == 0
    callers = {
        (edge["source"], edge["file"])
        for edge in out["edges"]
        if edge["kind"] == "include" and edge["target"] == "part:schema change workflow"
    }
    assert {
        ("skill:apply ubiq", "skills/apply-ubiq/SKILL.md"),
        ("skill:maintain ubiq", "skills/maintain-ubiq/SKILL.md"),
    } <= callers
