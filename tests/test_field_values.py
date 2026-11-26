"""Frontmatter field references: `= this.field` and `= [[record]].field` in code spans."""

import json

from test_ubiq import make_repo

from ubiq.cli import build, main
from ubiq.records import field_value
from ubiq.scan import value_of

DISCOUNT = "---\nterm: discount\npct: 10\nnote:\n---\n\nTakes `= this.pct` percent off.\n"
CONFIG = 'glossary: ["glossary/*.md"]\ndocs: ["**/*.md"]\n'


def check(root, capsys):
    status = main(["check", "--root", str(root), "--json"])
    return status, json.loads(capsys.readouterr().out)["diagnostics"]


def test_existing_fields_resolve_and_count_as_use(tmp_path, capsys):
    make_repo(tmp_path, {"discount.md": DISCOUNT},
              {"doc.md": "---\nowner: ops\n---\nSave `= [[discount]].pct`% (`= this.owner`).\n"},
              CONFIG)
    status, diags = check(tmp_path, capsys)
    assert status == 0, diags
    assert not [d for d in diags if d["code"] == "W001"]  # the cross-record ref uses the term


def test_missing_field_record_or_ambiguity_fails(tmp_path, capsys):
    dup = "---\nterm: dup\nns: {}\npct: 1\n---\n"
    doc = ("`= this.pct` `= [[discount]].rate` `= [[discont]].pct` `= [[discount]].note`\n"
           "`= [[dup]].pct` `= [[a:dup]].pct`\n"
           "```\n`= this.fenced`\n```\n<!-- `= this.hidden` --> `this.pct` `= this.pct + 1`\n")
    make_repo(tmp_path, {"discount.md": DISCOUNT, "a.md": dup.format("a"),
                         "b.md": dup.format("b")}, {"doc.md": doc}, CONFIG)
    status, diags = check(tmp_path, capsys)
    assert status == 1
    found = [d["message"].split(" — ", 1)[1] for d in diags if d["code"] == "E013"]
    # fences, comments, other code spans, and a qualified target are not reported
    assert found == ["this document has no frontmatter field 'pct'",
                     "record discount.md has no frontmatter field 'rate'",
                     "no record named 'discont'",
                     "record discount.md has no frontmatter field 'note'",  # null is absent
                     "'dup' names 2 records; qualify it"], found


def test_wiki_fragments_keep_their_meaning(tmp_path, capsys):
    """`[[term#heading]]` is a wiki-link, never a field ref."""
    make_repo(tmp_path, {"discount.md": DISCOUNT}, {"doc.md": "[[discount#pct]]\n"}, CONFIG)
    _, diags = check(tmp_path, capsys)
    assert not [d for d in diags if d["code"] == "E013"]


def test_severity_and_historical_docs(tmp_path, capsys):
    make_repo(tmp_path, {"discount.md": DISCOUNT},
              {"doc.md": "`= this.x`\n", "CHANGELOG.md": "`= [[discount]].gone`\n"},
              CONFIG + 'historical: ["CHANGELOG.md"]\nreferences: {value: {severity: warn}}\n')
    status, diags = check(tmp_path, capsys)
    assert status == 0
    assert [(d["code"], d["severity"]) for d in diags if d["code"] == "E013"] == [
        ("E013", "warning")]


def test_value_of_returns_frontmatter_values_for_renderers(tmp_path):
    overlay = "---\nsource: glossary/discount.md\npct: 15\n---\n"
    make_repo(tmp_path, {"discount.md": DISCOUNT},
              {"doc.md": "`= [[discount]].pct` `= this.owner`\n", ".ubiq/o.md": overlay},
              CONFIG + 'overlays: [".ubiq/o.md"]\n')
    (tmp_path / "doc.md").write_text("---\nowner: ops\n---\n`= [[discount]].pct` `= this.owner`\n")
    built = build(tmp_path)
    refs = [r for r in built.refs if r.kind == "value" and r.file.name == "doc.md"]
    assert [r.raw for r in refs] == ["`= [[discount]].pct`", "`= this.owner`"]
    assert [value_of(built.glossary, r) for r in refs] == ["15", "ops"]  # overlay wins
    assert field_value(tmp_path / "glossary" / "discount.md", "pct") == "10"
