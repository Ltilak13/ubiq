"""Frontmatter field references: a Markdown link whose fragment names a field."""

import json

from test_ubiq import make_repo

from ubiq.cli import build, main
from ubiq.records import field_value, frontmatter_fields
from ubiq.scan import value_of

DISCOUNT = ("---\nterm: discount\naliases: [off]\npct: 10\nowner: ops\nnote:\n"
            "tags: [a, b]\nlimits: {max: 5}\n---\n\n## Pct\n\nTakes [10](#pct) percent off.\n")
CONFIG = 'glossary: ["glossary/*.md"]\ndocs: ["**/*.md"]\n'
LINK = "glossary/discount.md"


def check(root, capsys):
    status = main(["check", "--root", str(root), "--json"])
    return status, json.loads(capsys.readouterr().out)["diagnostics"]


def e013(diags):
    return [d["message"].split(" — ", 1)[1] for d in diags if d["code"] == "E013"]


def test_matching_labels_pass(tmp_path, capsys):
    doc = (f"---\nowner: ops\n---\nSave [ 10 ]({LINK}#pct)% on [a, b]({LINK}#tags) "
           f"(owner [ops](#owner)).\n")
    make_repo(tmp_path, {"discount.md": DISCOUNT}, {"doc.md": doc}, CONFIG)
    status, diags = check(tmp_path, capsys)
    assert status == 0, diags


def test_stale_null_and_non_text_fields_fail(tmp_path, capsys):
    doc = (f"---\npct: 5\n---\n# pct\n\n[4](#pct) [9]({LINK}#pct) [x]({LINK}#note) "
           f"[x]({LINK}#limits) [heading]({LINK}#Pct)\n"
           f"```\n[1]({LINK}#pct)\n```\n<!-- [2]({LINK}#pct) --> `[3]({LINK}#pct)`\n")
    make_repo(tmp_path, {"discount.md": DISCOUNT}, {"doc.md": doc}, CONFIG)
    status, diags = check(tmp_path, capsys)
    assert status == 1
    # A field wins over a same-named heading; a heading fragment is an ordinary
    # anchor; fences, comments, and code are not scanned.
    assert e013(diags) == [
        "label '4' ≠ pct '5' — update the label",
        "label '9' ≠ pct '10' — update the label",
        "glossary/discount.md has no value for field 'note'",
        "field 'limits' in glossary/discount.md is not text or a list of text; link a scalar field",
    ], diags


def test_misspelled_field_fragments_fail(tmp_path, capsys):
    doc = (f"---\npct: 5\n---\n## Real heading\n\n[5](#pcct) [10]({LINK}#pcct) "
           f"[ok](#real-heading) [ok]({LINK}#pct-1) [ok](plain.md#nothing)\n")
    make_repo(tmp_path, {"discount.md": DISCOUNT + "\n## Pct\n"},
              {"doc.md": doc, "plain.md": "# Plain\n"}, CONFIG)
    status, diags = check(tmp_path, capsys)
    assert status == 1
    # Files without frontmatter keep unchecked fragments.
    assert e013(diags) == ["no field or heading 'pcct' in doc.md",
                           "no field or heading 'pcct' in glossary/discount.md"], diags


def test_severity_and_historical_docs(tmp_path, capsys):
    make_repo(tmp_path, {"discount.md": DISCOUNT},
              {"doc.md": f"[1]({LINK}#pct)\n", "CHANGELOG.md": f"[2]({LINK}#pct)\n"},
              CONFIG + 'historical: ["CHANGELOG.md"]\nreferences: {value: {severity: warn}}\n')
    status, diags = check(tmp_path, capsys)
    assert status == 0
    assert [(d["file"], d["severity"]) for d in diags if d["code"] == "E013"] == [
        ("doc.md", "warning")]


def test_lenient_records_read_leniently(tmp_path, capsys):
    record = "---\nterm: rate\ntitle: a: b\npct: 3\n---\n"
    make_repo(tmp_path, {"rate.md": record}, {"doc.md": "[3](glossary/rate.md#pct)\n"},
              CONFIG + "frontmatter: lenient\n")
    status, diags = check(tmp_path, capsys)
    assert status == 0, diags


def test_refs_lists_same_file_and_cross_record_links(tmp_path, capsys):
    make_repo(tmp_path, {"discount.md": DISCOUNT}, {"doc.md": f"[10]({LINK}#pct)\n"}, CONFIG)
    main(["refs", "discount", "--root", str(tmp_path), "--kind", "value", "--json"])
    refs = json.loads(capsys.readouterr().out)["references"]
    assert [(r["file"], r["raw"]) for r in refs] == [
        ("doc.md", f"[10]({LINK}#pct)"), (LINK, "[10](#pct)")]


def test_overlay_fields_win_unless_null(tmp_path):
    overlay = "---\nsource: glossary/discount.md\npct: 15\nowner:\naliases: [cut]\n---\n"
    make_repo(tmp_path, {"discount.md": DISCOUNT},
              {"doc.md": f"[15]({LINK}#pct)\n", ".ubiq/o.md": overlay},
              CONFIG + 'overlays: [".ubiq/o.md"]\n')
    built = build(tmp_path)
    record = tmp_path / LINK
    fields = frontmatter_fields(record, built.glossary)
    assert (fields["pct"], fields["owner"], fields["aliases"]) == ("15", "ops", ["off", "cut"])
    assert field_value(record, "pct") == "10"
    [ref] = [r for r in built.refs if r.kind == "value" and r.file.name == "doc.md"]
    assert value_of(built.glossary, ref) == "15"
