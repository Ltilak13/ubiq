"""`ubiq graph --format mermaid` and `<!-- ubiq:graph -->` blocks (W008)."""

import json

from test_graph import part, repo, skill

from ubiq.cli import main

BLOCK = """<!-- ubiq:graph {attrs} -->
```mermaid
{body}
```
<!-- /ubiq:graph -->
"""
NOTES = "skills/ship/notes.md"


def graph_repo(tmp_path, notes):
    return repo(tmp_path, {
        "skills/ship/SKILL.md": skill("ship", "Ship it.", uses=["push"]),
        "skills/push/SKILL.md": skill("push", "Follow [checkout](../_shared/checkout.md)."),
        "skills/_shared/checkout.md": part("checkout", "Check out the branch."),
        NOTES: notes,
    })


def mermaid_out(tmp_path, capsys, *argv):
    status = main(["graph", *argv, "--format", "mermaid", "--root", str(tmp_path)])
    return status, capsys.readouterr().out.splitlines()


def w008(tmp_path, capsys):
    main(["check", "--root", str(tmp_path), "--json"])
    out = json.loads(capsys.readouterr().out)
    return [d for d in out["diagnostics"] if d["code"] == "W008"]


def test_format_is_sorted_and_labels_mixed_kinds(tmp_path, capsys):
    graph_repo(tmp_path, "x\n")
    status, lines = mermaid_out(tmp_path, capsys, "--kind", "include")
    assert status == 0
    assert lines == ["flowchart LR", "  push --> checkout"]
    _, lines = mermaid_out(tmp_path, capsys)
    assert lines == ["flowchart LR", "  push -->|include| checkout", "  ship -->|invoke| push"]
    _, lines = mermaid_out(tmp_path, capsys, "ship", "--depth", "1")
    assert lines == ["flowchart LR", "  ship --> push"]


def test_rejects_json(tmp_path):
    graph_repo(tmp_path, "x\n")
    assert main(["graph", "--format", "mermaid", "--json", "--root", str(tmp_path)]) == 2


def test_matching_block_is_clean_and_stale_block_warns_with_line(tmp_path, capsys):
    notes = "intro\n\n" + BLOCK.format(attrs="target=ship depth=1", body="flowchart LR\n  ship --> push")
    graph_repo(tmp_path, notes)
    assert w008(tmp_path, capsys) == []
    (tmp_path / NOTES).write_text(
        "intro\n\n" + BLOCK.format(attrs="target=ship depth=1", body="flowchart LR\n  ship --> other"))
    found = w008(tmp_path, capsys)
    assert len(found) == 1
    assert found[0]["file"].endswith(NOTES) and found[0]["line"] == 4
    assert "ubiq graph ship --depth 1 --format mermaid" in found[0]["message"]


def test_invalid_markers_warn_and_fenced_examples_are_skipped(tmp_path, capsys):
    example = "~~~markdown\n" + BLOCK.format(attrs="target=ship", body="stale") + "~~~\n"
    graph_repo(tmp_path, example)
    assert w008(tmp_path, capsys) == []
    for attrs, text in [("target=nope", "no record"), ("kind=bogus", "unknown kind"),
                        ("color=red", "unknown attribute")]:
        (tmp_path / NOTES).write_text(BLOCK.format(attrs=attrs, body="x"))
        found = w008(tmp_path, capsys)
        assert len(found) == 1 and text in found[0]["message"] and found[0]["line"] == 1
    (tmp_path / NOTES).write_text("<!-- ubiq:graph target=ship -->\nno fence\n")
    assert "no closing" in w008(tmp_path, capsys)[0]["message"]


def test_reserved_and_colliding_names_get_unique_ids(tmp_path, capsys):
    repo(tmp_path, {
        "skills/a/SKILL.md": skill("a", "x", uses=["end"]),
        "skills/end/SKILL.md": skill("end", "x"),
    })
    status, lines = mermaid_out(tmp_path, capsys)
    assert status == 0
    assert lines == ["flowchart LR", '  skill_end["skill:end"]', "  a --> skill_end"]
