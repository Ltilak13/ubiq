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


def skill(name, body="", uses=(), user_only=False):
    meta = f"name: {name}\n"
    if uses:
        meta += f"uses: [{', '.join(uses)}]\n"
    if user_only:
        meta += "disable-model-invocation: true\n"
    return f"---\n{meta}---\n\n{body}\n"


def part(name, body):
    return f"---\nname: {name}\n---\n\n{body}\n"


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
                    if d["code"] in ("E011", "W003", "W004")]


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
    assert found == [("W003", "skill:lead invokes skill:spec, which sets "
                      "disable-model-invocation: true — include its file or allow model invocation")]


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
