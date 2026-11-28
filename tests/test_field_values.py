"""Frontmatter field references: a Markdown link whose fragment names a field."""

import json

import pytest
from test_ubiq import make_repo

from ubiq.cli import build, main
from ubiq.records import frontmatter_fields
from ubiq.scan import value_of

DISCOUNT = ("---\nterm: discount\naliases: [off]\npct: 10\nowner: ops\nnote:\n"
            "tags: [a, b]\nlimits: {max: 5}\n---\n\n## Rates\n\nTakes [10](#pct) percent off.\n")
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


def test_labels_compare_as_plain_text(tmp_path, capsys):
    record = DISCOUNT.replace("pct: 10\n", 'pct: 10\ncode: "a_b"\npad: " 10 "\nphrase: two  words\n')
    # A label that wraps across lines is not a link to this scanner (a known gap).
    doc = (f"[`10`]({LINK}#pct) [a\\_b]({LINK}#code) [10]({LINK}#pad) [two \t words]({LINK}#phrase)\n"
           f"[*10*]({LINK}#pct) [__10__]({LINK}#pct)\n"
           f"[`a\\_b`]({LINK}#code)\n")
    make_repo(tmp_path, {"discount.md": record}, {"doc.md": doc}, CONFIG)
    _, diags = check(tmp_path, capsys)
    # Escapes inside a code span are literal.
    assert e013(diags) == ["label 'a\\_b' ≠ code 'a_b' — update the label"], diags


def test_stale_null_and_non_text_fields_fail(tmp_path, capsys):
    doc = (f"[9]({LINK}#pct) [x]({LINK}#note) [x]({LINK}#limits) [heading]({LINK}#Rates)\n"
           f"[x]({LINK}?v=1#pcct)\n"
           f"```\n[1]({LINK}#pct)\n```\n<!-- [2]({LINK}#pct) --> `[3]({LINK}#pct)`\n")
    make_repo(tmp_path, {"discount.md": DISCOUNT}, {"doc.md": doc}, CONFIG)
    status, diags = check(tmp_path, capsys)
    assert status == 1
    # A heading fragment is an ordinary anchor; links with a query, fences,
    # comments, and code are not field refs.
    assert e013(diags) == [
        "label '9' ≠ pct '10' — update the label",
        "glossary/discount.md has no value for field 'note'",
        "field 'limits' in glossary/discount.md is not text or a list of text; link a scalar field",
    ], diags


def test_headings_win_over_same_named_fields(tmp_path, capsys):
    record = DISCOUNT.replace("## Rates", "## Pct\n\n## Description").replace(
        "pct: 10\n", "pct: 10\ndescription: Money off.\n")
    doc = f"---\npct: 5\n---\n# pct\n\n[4](#pct) [9]({LINK}#pct) [what]({LINK}#description)\n"
    make_repo(tmp_path, {"discount.md": record}, {"doc.md": doc}, CONFIG)
    status, diags = check(tmp_path, capsys)
    assert status == 0, diags


def test_setext_html_and_duplicate_anchors_are_headings(tmp_path, capsys):
    record = ("---\nterm: z\n# owner pending\npct: 1\n---\nZ.\n\nSetext Heading\n--------------\n\n"
              '<a id="Custom"></a> <span name=named></span>\n\n## Dup\n## Dup\n')
    doc = ("[x](glossary/z.md#setext-heading) [x](glossary/z.md#custom) [x](glossary/z.md#named) "
           "[x](glossary/z.md#dup-1) [x](glossary/z.md#owner-pending)\n")
    make_repo(tmp_path, {"z.md": record}, {"doc.md": doc}, CONFIG)
    _, diags = check(tmp_path, capsys)
    # A YAML comment in frontmatter is not a heading.
    assert e013(diags) == ["no field or heading 'owner-pending' in glossary/z.md"], diags


def test_misspelled_field_fragments_fail(tmp_path, capsys):
    doc = (f"---\npct: 5\n---\n## Real heading\n\n[5](#pcct) [10]({LINK}#pcct) [5](#x) [10]({LINK}#PCT) "
           f"[ok](#Real-Heading) [ok]({LINK}#rates-1) [ok](plain.md#nothing)\n")
    make_repo(tmp_path, {"discount.md": DISCOUNT + "\n## Rates\n"},
              {"doc.md": doc, "plain.md": "# Plain\n"}, CONFIG)
    status, diags = check(tmp_path, capsys)
    assert status == 1
    # Files without frontmatter keep unchecked fragments.
    assert e013(diags) == ["no field or heading 'pcct' in doc.md",
                           "no field or heading 'pcct' in glossary/discount.md",
                           "no field or heading 'x' in doc.md",
                           # Field names are case-sensitive; headings are not.
                           "no field or heading 'PCT' in glossary/discount.md"], diags


def test_severity_and_historical_docs(tmp_path, capsys):
    make_repo(tmp_path, {"discount.md": DISCOUNT},
              {"doc.md": f"[1]({LINK}#pct)\n",
               "CHANGELOG.md": f"[2]({LINK}#pct) [2]({LINK}#pcct)\n"},
              CONFIG + 'historical: ["CHANGELOG.md"]\nreferences: {value: {severity: warn}}\n')
    status, diags = check(tmp_path, capsys)
    assert status == 0
    assert [(d["file"], d["severity"]) for d in diags if d["code"] == "E013"] == [
        ("doc.md", "warning")]


def test_lenient_records_read_leniently(tmp_path, capsys):
    record = "---\nterm: rate\ntitle: a: b\npct: 3\n---\n"
    make_repo(tmp_path, {"rate.md": record},
              {"doc.md": "[3](glossary/rate.md#pct) [4](glossary/rate.md#pct)\n"},
              CONFIG + "frontmatter: lenient\n")
    _, diags = check(tmp_path, capsys)
    assert e013(diags) == ["label '4' ≠ pct '3' — update the label"], diags


def test_external_records_read_their_repositorys_overlays(tmp_path, capsys):
    skills = '  - {glob: "skills/*/SKILL.md", term_field: name, ns: skill}\n'
    files = {
        "ubiq.yaml": (f"glossary:\n{skills}docs: [\"doc.md\"]\n"
                      "edges:\n  install: [\"skills/*/SKILL.md\"]\n  external: [vendor/up]\n"),
        "doc.md": "[7](vendor/up/skills/t/SKILL.md#pct) [8](vendor/up/skills/t/SKILL.md#pct)\n",
        "vendor/up/ubiq.yaml": (f"glossary:\n{skills}docs: [\"skills/**/*.md\"]\n"
                                "overlays: [\".ubiq/*.md\"]\n"
                                "edges:\n  install: [\"skills/*/SKILL.md\"]\n"),
        "vendor/up/skills/t/SKILL.md": "---\nname: t\ndescription: T.\n---\n# T\n",
        "vendor/up/.ubiq/t.md": "---\nsource: skills/t/SKILL.md\npct: 7\n---\n",
    }
    for name, body in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(body)
    _, diags = check(tmp_path, capsys)
    assert e013(diags) == ["label '8' ≠ pct '7' — update the label"], diags


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
    assert frontmatter_fields(record)["pct"] == "10"
    [ref] = [r for r in built.refs if r.kind == "value" and r.file.name == "doc.md"]
    assert value_of(built.glossary, ref) == "15"


def test_fields_are_copies(tmp_path):
    make_repo(tmp_path, {"discount.md": DISCOUNT}, {}, CONFIG)
    frontmatter_fields(tmp_path / LINK)["tags"].append("c")
    assert frontmatter_fields(tmp_path / LINK)["tags"] == ["a", "b"]


def test_invalid_urls_are_not_value_refs(tmp_path, capsys):
    make_repo(tmp_path, {"discount.md": DISCOUNT},
              {"doc.md": "see [x](http://[oops/a#frag) and [y](https://[::1/x)\n"}, CONFIG)
    status, diags = check(tmp_path, capsys)
    assert status == 0, diags


@pytest.mark.parametrize(("heading", "fragment"), [
    ("## _Notes_", "notes"),
    ("## __Strong__", "strong"),
    ("## Foo &amp; bar", "foo--bar"),
    ("## <code>x</code> y", "x-y"),
    ("First line\nsecond line\n---", "first-line-second-line"),
    ("> ## Quoted Head", "quoted-head"),
    ("- ## Listed Head", "listed-head"),
    ("## See [docs][r]\n\n[r]: https://example.com", "see-docs"),
    ("## See [docs]", "see-docs"),
    ("Setext Eq\n===", "setext-eq"),
])
def test_heading_slugs_follow_github(tmp_path, capsys, heading, fragment):
    record = f"---\nterm: tee\npct: 10\n---\n\n{heading}\n"
    make_repo(tmp_path, {"t.md": record}, {"doc.md": f"[x](glossary/t.md#{fragment})\n"}, CONFIG)
    _, diags = check(tmp_path, capsys)
    assert not e013(diags), diags


def test_a_quote_before_a_rule_is_not_a_heading(tmp_path, capsys):
    record = "---\nterm: tee\npct: 10\n---\n\n> quote\n---\n\n## Quote\n"
    make_repo(tmp_path, {"t.md": record},
              {"doc.md": "[x](glossary/t.md#quote) [x](glossary/t.md#quote-1) "
                         "[x](glossary/t.md#-quote)\n"}, CONFIG)
    _, diags = check(tmp_path, capsys)
    assert e013(diags) == ["no field or heading 'quote-1' in glossary/t.md",
                           "no field or heading '-quote' in glossary/t.md"], diags


def test_anchors_in_comments_and_code_do_not_hide_fields(tmp_path, capsys):
    record = ('---\nterm: tee\npct: 10\n---\n\n`<a id="pct">`\n\n<!-- <a name="pct"> -->\n\n'
              '<a id="real"></a>\n')
    make_repo(tmp_path, {"t.md": record},
              {"doc.md": "[11](glossary/t.md#pct) [x](glossary/t.md#real)\n"}, CONFIG)
    _, diags = check(tmp_path, capsys)
    assert e013(diags) == ["label '11' ≠ pct '10' — update the label"], diags


def test_changed_records_and_overlays_are_read_again(tmp_path, capsys):
    overlay = "---\nsource: glossary/discount.md\nowner: ops\n---\n"
    make_repo(tmp_path, {"discount.md": DISCOUNT},
              {"doc.md": f"[10]({LINK}#pct) [ops]({LINK}#owner)\n", ".ubiq/o.md": overlay},
              CONFIG + 'overlays: [".ubiq/o.md"]\n')
    assert not e013(check(tmp_path, capsys)[1])
    (tmp_path / LINK).write_text(DISCOUNT.replace("pct: 10", "pct: 2000"))
    assert e013(check(tmp_path, capsys)[1]) == [
        "label '10' ≠ pct '2000' — update the label",
        "label '10' ≠ pct '2000' — update the label"]  # the record's own link
    (tmp_path / ".ubiq/o.md").write_text(overlay.replace("ops", "sales"))
    assert e013(check(tmp_path, capsys)[1]) == [
        "label '10' ≠ pct '2000' — update the label",
        "label 'ops' ≠ owner 'sales' — update the label",
        "label '10' ≠ pct '2000' — update the label"]
