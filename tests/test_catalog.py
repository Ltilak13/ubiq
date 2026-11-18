import json
from pathlib import Path
from unittest.mock import patch

from ubiq.cli import build
from ubiq.check import run_checks


def catalog_repo(root, records, items, suffix="json"):
    glossary = root / "glossary"
    glossary.mkdir()
    for name, frontmatter in records.items():
        (glossary / name).write_text(f"---\n{frontmatter}\n---\nDefinition.\n")
    catalog = root / f"catalog.{suffix}"
    catalog.write_text(json.dumps({"skills": items}))
    (root / "ubiq.yaml").write_text(
        'glossary: ["glossary/*.md"]\ndocs: []\ncatalogs:\n'
        f'  - file: catalog.{suffix}\n    cover: ["glossary/*.md"]\n')
    return catalog


def errors(root):
    glossary, refs, cfg, extra = build(root)
    return [d for d in extra + run_checks(glossary, refs, cfg["external_id_patterns"])
            if d.is_error]


def test_catalog_ids_aliases_and_names_share_coverage_resolution(tmp_path):
    catalog_repo(tmp_path, {
        "id.md": "term: session\nid: T1",
        "alias.md": "term: attempt\naliases: [try]",
        "qualified.md": "term: pitch\nns: game",
        "other.md": "term: pitch\nns: sales",
    }, ["T1", "try", "game:pitch", "sales:pitch"])
    assert errors(tmp_path) == []


def test_catalog_ambiguous_name_covers_neither_record(tmp_path):
    catalog_repo(tmp_path, {
        "game.md": "term: pitch\nns: game",
        "sales.md": "term: pitch\nns: sales",
    }, ["pitch"])
    diags = errors(tmp_path)
    assert [d.code for d in diags].count("E003") == 1
    assert [d.code for d in diags].count("E007") == 2


def test_catalog_id_precedence_does_not_cover_same_named_record(tmp_path):
    catalog_repo(tmp_path, {
        "id.md": "term: session\nid: T1",
        "name.md": "term: T1",
    }, ["T1"])
    diags = errors(tmp_path)
    assert len(diags) == 1 and diags[0].code == "E007"
    assert "core:t1" in diags[0].message


def test_catalog_duplicate_id_covers_neither_record(tmp_path):
    catalog_repo(tmp_path, {
        "a.md": "term: session\nid: T1",
        "b.md": "term: inning\nid: T1",
    }, ["T1"])
    codes = [d.code for d in errors(tmp_path)]
    assert codes.count("E001") == 1
    assert codes.count("E003") == 1
    assert codes.count("E007") == 2


def test_catalog_is_read_once_per_build(tmp_path):
    catalog = catalog_repo(tmp_path, {"s.md": "term: session"}, ["session"])
    original = Path.read_text
    reads = []

    def read(path, *args, **kwargs):
        if path == catalog:
            reads.append(path)
        return original(path, *args, **kwargs)

    with patch.object(Path, "read_text", read):
        assert errors(tmp_path) == []
    assert reads == [catalog]


def test_catalog_yaml_uses_same_resolution(tmp_path):
    catalog = catalog_repo(tmp_path, {"s.md": "term: session\nid: T1"}, [], "yaml")
    catalog.write_text("skills:\n  - T1\n")
    assert errors(tmp_path) == []


def test_invalid_catalog_content_is_diagnostic(tmp_path):
    catalog = catalog_repo(tmp_path, {"s.md": "term: session"}, [])
    for content in (b"{", b"\xff", b'{"skills": {}}'):
        catalog.write_bytes(content)
        diags = errors(tmp_path)
        assert len(diags) == 1 and diags[0].code == "E005"


def test_unreadable_catalog_is_diagnostic(tmp_path):
    catalog = catalog_repo(tmp_path, {"s.md": "term: session"}, [])
    original = Path.read_text

    def read(path, *args, **kwargs):
        if path == catalog:
            raise PermissionError("catalog permission denied")
        return original(path, *args, **kwargs)

    with patch.object(Path, "read_text", read):
        diags = errors(tmp_path)
    assert len(diags) == 1 and diags[0].code == "E005"
    assert "catalog permission denied" in diags[0].message
