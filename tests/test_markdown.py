"""Markdown behavior exercised through repository checks and traversal."""

from ubiq.check import run_checks
from ubiq.cli import build
from ubiq.scan import file_link_targets


def repo(tmp_path, text, *, historical=False):
    (tmp_path / "glossary").mkdir(exist_ok=True)
    (tmp_path / "glossary/session.md").write_text(
        "---\nterm: session\nid: T1\n---\nA period of play.\n\n## Definition\n")
    (tmp_path / "README.md").write_text(text)
    (tmp_path / "ubiq.yaml").write_text(
        'glossary: ["glossary/**/*.md"]\ndocs: [README.md]\n'
        "id_patterns: ['\\bT[0-9]+\\b']\n"
        'delimiters: ["/"]\n'
        + ('historical: [README.md]\n' if historical else ''))
    return tmp_path


def references(root):
    built = build(root)
    return built.refs, built.diagnostics + run_checks(built.glossary, built.refs)


def test_fence_variants_keep_code_hidden_and_locations(tmp_path):
    blocks = [
        "````md\n[[ghost]]\n```\n[[ghost]]\n`````\n",
        "   ```\n[[ghost]]\n  ```\n",
        "~~~\n[[ghost]]\n```\n[[ghost]]\n~~~~\n",
        "```\n[[ghost]]\n``` trailing\n[[ghost]]\n```\n",
    ]
    for block in blocks:
        root = repo(tmp_path, block + "[[session]]\n")
        refs, diags = references(root)
        assert not diags
        assert [(r.raw, r.line) for r in refs if r.kind == "explicit"] == [
            ("[[session]]", block.count("\n") + 1)]


def test_unclosed_fence_hides_links_and_delimiters_to_eof(tmp_path):
    root = repo(tmp_path, "[[session]]\n```\n[[ghost]] /ghost [x](extra.md)\n")
    (root / "extra.md").write_text("[[ghost]]\n")
    refs, diags = references(root)
    assert not diags
    assert [r.raw for r in refs] == ["[[session]]"]
    assert file_link_targets(root / "README.md", root) == []


def test_reference_link_forms_count_once_at_usage(tmp_path):
    root = repo(tmp_path, "[session][play]\n[session][]\n[session]\n"
                "[play]: glossary/session.md 'Play'\n"
                "[session]: <glossary/session.md#definition>\n")
    refs, diags = references(root)
    assert not diags
    assert [(r.raw, r.line, r.kind) for r in refs] == [
        ("[session][play]", 1, "markdown"),
        ("[session][]", 2, "markdown"),
        ("[session]", 3, "markdown"),
    ]


def test_reference_labels_normalize_and_first_definition_wins(tmp_path):
    root = repo(tmp_path, "[game][PLAY  time]\n"
                " [Play\ttime]: glossary/session.md\n"
                "[play time]: glossary/missing.md\n")
    refs, diags = references(root)
    assert not diags
    assert len(refs) == 1 and refs[0].destination == root / "glossary/session.md"


def test_reference_exclusions_and_unused_definitions(tmp_path):
    root = repo(tmp_path, "[[session]]\n"
                "![picture][x]\n![x]\n![x][]\n"
                "`[x]`\n``a `[x]` b``\n"
                "\\[x]\n\\[label][x]\n[[x]]\n"
                "[x](https://example.com)\n"
                "```\n[x]\n```\n"
                "[x]: glossary/missing.md\n"
                "[unused]: extra.md\n")
    (root / "extra.md").write_text("[[ghost]]\n")
    refs, diags = references(root)
    assert not [r for r in refs if r.kind == "markdown"]
    assert [(d.code, d.line) for d in diags] == [("E002", 9)]
    assert file_link_targets(root / "README.md", root) == []


def test_definitions_are_metadata_not_references(tmp_path):
    root = repo(tmp_path, "[[session]]\n"
                '[unused]: glossary/session.md "[[ghost]] /ghost T9"\n')
    refs, diags = references(root)
    assert not diags
    assert [r.raw for r in refs] == ["[[session]]"]


def test_missing_reference_definition_remains_plain_prose(tmp_path):
    root = repo(tmp_path, "[[session]] [label][missing] [missing][] [missing]\n")
    refs, diags = references(root)
    assert not diags
    assert [r.raw for r in refs] == ["[[session]]"]


def test_named_links_follow_documents_but_not_unused_definitions(tmp_path):
    root = repo(tmp_path, "[[session]]\n[details][more]\n"
                "[more]: extra.md\n[unused]: unused.md\n")
    (root / "extra.md").write_text("[back][root]\n[[ghost]]\n[root]: README.md\n")
    (root / "unused.md").write_text("[[another-ghost]]\n")
    _, diags = references(root)
    assert [(d.code, d.file.name, d.line) for d in diags] == [("E002", "extra.md", 2)]
    assert file_link_targets(root / "README.md", root) == [root / "extra.md"]


def test_named_missing_glossary_destination_and_historical(tmp_path):
    text = "[[session]]\n[old][gone]\n[gone]: glossary/deleted.md\n"
    root = repo(tmp_path, text)
    _, diags = references(root)
    assert [(d.code, d.line) for d in diags] == [("E002", 2)]
    repo(tmp_path, text, historical=True)
    refs, diags = references(root)
    assert not diags
    assert all(r.historical for r in refs)


def test_named_links_support_encoded_paths_and_select_namespace(tmp_path):
    root = repo(tmp_path, "[playing][game]\n[game]: glossary/play%20%28one%29.md#x \"Title\"\n")
    (root / "glossary/play (one).md").write_text(
        "---\nterm: session\nns: game\n---\n# X\n")
    built = build(root)
    assert not built.diagnostics
    assert len(built.refs) == 1
    assert [t.qualified for t in built.refs[0].resolve(built.glossary)] == ["game:session"]


def test_named_links_keep_registered_external_symlinks(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    repo(root, "[play][s]\n[s]: glossary/session.md\n[outside]: ../outside.md\n")
    outside = tmp_path / "outside.md"
    outside.write_text((root / "glossary/session.md").read_text())
    (root / "glossary/session.md").unlink()
    (root / "glossary/session.md").symlink_to(outside)
    refs, diags = references(root)
    assert not diags
    assert refs[0].destination == outside
    assert file_link_targets(root / "README.md", root) == []


def test_markdown_usage_does_not_also_emit_delimiter_or_id(tmp_path):
    root = repo(tmp_path, "[/session T1][s]\n[s]: glossary/session.md\n")
    refs, diags = references(root)
    assert not diags
    assert len(refs) == 1 and refs[0].kind == "markdown"


def test_inline_code_keeps_delimiters_but_hides_named_links(tmp_path):
    root = repo(tmp_path, "``/session [play] `[[ghost]]` ``\n"
                "[play]: glossary/missing.md\n")
    refs, diags = references(root)
    assert not diags
    assert [(r.kind, r.raw) for r in refs] == [("explicit", "/session")]


def test_definition_inside_multiline_code_is_not_registered(tmp_path):
    root = repo(tmp_path, "[[session]]\n`example\n[x]: glossary/missing.md\n`\n[x]\n")
    refs, diags = references(root)
    assert not diags
    assert [r.raw for r in refs] == ["[[session]]"]


def test_escaped_image_marker_leaves_a_link(tmp_path):
    root = repo(tmp_path, "\\![play]\n[play]: glossary/session.md\n")
    refs, diags = references(root)
    assert not diags
    assert [(r.kind, r.raw) for r in refs] == [("markdown", "[play]")]
