"""Malformed declarations must report E005, never disappear silently.

Each case exits 0 on v0.7.4: the declaration is dropped or coerced without a
diagnostic.
"""

import pytest
from test_ubiq import make_repo

from ubiq.cli import main

TDD = "---\nterm: tdd\n---\n\nThe loop.\n"


def _check(tmp_path, capsys, records, docs, config):
    make_repo(tmp_path, records, docs, config=config)
    code = main(["check", "--root", str(tmp_path)])
    return code, capsys.readouterr().out


@pytest.mark.xfail(strict=True, reason="M2: unparsable doc frontmatter drops its ref fields")
def test_unparsable_doc_frontmatter_with_ref_fields_is_e005(tmp_path, capsys):
    doc = "---\nuses: [ghost\ntitle: a: b\n---\n\nBody.\n"
    cfg = 'glossary: ["glossary/**/*.md"]\ndocs: ["doc.md"]\nref_fields: [uses]\n'
    code, out = _check(tmp_path, capsys, {"tdd.md": TDD}, {"doc.md": doc}, cfg)
    assert code == 1
    assert "doc.md: E005" in out and "invalid YAML frontmatter" in out


@pytest.mark.xfail(strict=True, reason="M2: non-string ref field values are skipped")
@pytest.mark.parametrize("value", ["[{name: ghost}]", "[[ghost]]", "{name: ghost}"])
def test_non_string_ref_field_values_are_e005(tmp_path, capsys, value):
    doc = f"---\nuses: {value}\n---\n\nBody.\n"
    cfg = 'glossary: ["glossary/**/*.md"]\ndocs: ["doc.md"]\nref_fields: [uses]\n'
    code, out = _check(tmp_path, capsys, {"tdd.md": TDD}, {"doc.md": doc}, cfg)
    assert code == 1
    assert "doc.md:2: E005" in out and "uses: expected a string or list of strings" in out


@pytest.mark.xfail(strict=True, reason="M2: non-scalar catalog entries are skipped")
@pytest.mark.parametrize("entry", ['{"name": "ghost"}', "null", "true", '["ghost"]'])
def test_non_scalar_catalog_entries_are_e005(tmp_path, capsys, entry):
    cfg = ('glossary: ["glossary/**/*.md"]\ndocs: []\ncatalogs:\n'
           '  - file: inv.json\n    items: skills\n')
    make_repo(tmp_path, {"tdd.md": TDD}, {}, config=cfg)
    (tmp_path / "inv.json").write_text(f'{{"skills": ["tdd", {entry}]}}')
    assert main(["check", "--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "inv.json: E005" in out and "skills[1]: expected a string" in out


@pytest.mark.xfail(strict=True, reason="M2: blank or non-string terms drop the record")
@pytest.mark.parametrize("value", ['""', "[]", "{}"])
def test_blank_or_non_string_term_is_e005(tmp_path, capsys, value):
    rec = f"---\nterm: {value}\n---\n\nBody.\n"
    cfg = 'glossary: ["glossary/**/*.md"]\ndocs: []\n'
    code, out = _check(tmp_path, capsys, {"bad.md": rec}, {}, cfg)
    assert code == 1
    assert "bad.md: E005" in out and "term: expected a nonempty string" in out


@pytest.mark.xfail(strict=True, reason="M2: non-scalar id and ns are coerced with str()")
@pytest.mark.parametrize("field,value", [("id", "[UB-1, UB-2]"), ("id", '""'),
                                         ("ns", "[x]"), ("ns", "{a: b}"), ("ns", '" "')])
def test_malformed_id_and_ns_are_e005(tmp_path, capsys, field, value):
    rec = f"---\nterm: c\n{field}: {value}\n---\n\nBody.\n"
    cfg = 'glossary: ["glossary/**/*.md"]\ndocs: []\n'
    code, out = _check(tmp_path, capsys, {"c.md": rec}, {}, cfg)
    assert code == 1
    assert "c.md: E005" in out and f"{field}: expected a nonempty string" in out


@pytest.mark.parametrize("value", ["", "~"])
def test_empty_term_key_still_means_no_term(tmp_path, capsys, value):
    """A null field reads as absent: files without a term stay non-records."""
    rec = f"---\nterm: {value}\n---\n\nNot a record.\n"
    cfg = 'glossary: ["glossary/**/*.md"]\ndocs: []\n'
    code, _ = _check(tmp_path, capsys, {"none.md": rec}, {}, cfg)
    assert code == 0
