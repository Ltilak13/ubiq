"""CLI contracts for validated discovery, reference output, and explanations."""


import json


from pathlib import Path


from ubiq.cli import build, main


from test_ubiq import REC_SESSION, make_repo


def check_json(root, capsys):
    status = main(["check", "--root", str(root), "--json"])
    return status, json.loads(capsys.readouterr().out)


def test_config_errors_are_diagnostics(tmp_path, capsys):
    configs = [
        "[glossary, docs]", "false", "0", "glossary: [", "docs: README.md",
        "glossary: [42]", "glossary: [{}]", "glossary: [{glob: '*.md', ns: []}]",
        "term_field: []", "frontmatter: tolerant", "id_patterns: ['[']",
        "external_id_patterns: ['(']", "catalogs: [{}]", "catalogs: [false]",
        "catalogs: [{file: x.json, cover: 5}]", "catalogs: [{file: x.json, term: typo}]",
        "delimiters: [5]", "delimiters: [{prefix: '/', except: false}]",
        "delimiters: [{prefix: '/', only_known: 'yes'}]",
        "delimiters: ['{term}{term}']", "historical: 3", "ref_fields: [null]",
    ]
    for config in configs:
        (tmp_path / "ubiq.yaml").write_text(config)
        status, result = check_json(tmp_path, capsys)
        assert status == 1, config
        assert result["errors"] == 1, config
        assert result["diagnostics"][0]["code"] == "E008", config
        assert result["diagnostics"][0]["file"] == "ubiq.yaml"


def test_all_read_commands_handle_invalid_config(tmp_path, capsys):
    (tmp_path / "ubiq.yaml").write_text("[]")
    for command in (["terms"], ["refs", "session"], ["explain"]):
        assert main([*command, "--root", str(tmp_path)]) == 1
        output = capsys.readouterr()
        assert "E008" in output.out and "Traceback" not in output.err
    for command in (["refs", "session"], ["explain"]):
        assert main([*command, "--root", str(tmp_path), "--json"]) == 1
        assert json.loads(capsys.readouterr().out)["errors"] == 1


def test_null_config_values_keep_defaults(tmp_path, capsys):
    (tmp_path / "ubiq.yaml").write_text("glossary: null\ndocs: null\n")
    status, result = check_json(tmp_path, capsys)
    assert status == 0 and result["terms"] == 0


def test_equivalent_globs_and_symlinks_register_once(tmp_path, capsys):
    make_repo(tmp_path, {"session.md": REC_SESSION}, {"README.md": "[[session]]"},
              'glossary: ["glossary/*.md", "glossary/**/*.md", "linked.md"]\ndocs: [README.md]\n')
    (tmp_path / "linked.md").symlink_to(tmp_path / "glossary/session.md")
    status, result = check_json(tmp_path, capsys)
    assert status == 0 and result["terms"] == 1
    assert result["warnings"] == 0


def test_conflicting_globs_report_both_rules(tmp_path, capsys):
    for setting in ("ns: other", "term_field: name"):
        config = ('glossary:\n  - glob: "glossary/*.md"\n'
                  f'  - glob: "glossary/**/*.md"\n    {setting}\ndocs: [README.md]\n')
        make_repo(tmp_path, {"session.md": REC_SESSION}, {"README.md": "[[session]]"}, config)
        status, result = check_json(tmp_path, capsys)
        assert status == 1
        diag = result["diagnostics"][0]
        assert diag["code"] == "E008"
        assert "glossary[0]" in diag["message"] and "glossary[1]" in diag["message"]


def test_invalid_overlay_inputs_fail(tmp_path, capsys):
    make_repo(tmp_path, {"session.md": REC_SESSION}, {"README.md": "[[session]]"},
              'glossary: ["glossary/*.md"]\ndocs: [README.md]\n')
    overlays = tmp_path / ".ubiq/overlays"
    overlays.mkdir(parents=True)
    for body in ("source: [", "source: []", "aliases: [play]", "source: missing.md",
                 "source: glossary/session.md\naliases: 7"):
        (overlays / "bad.md").write_text(f"---\n{body}\n---\n")
        status, result = check_json(tmp_path, capsys)
        assert status == 1, body
        assert any(d["code"] == "E005" for d in result["diagnostics"])
        assert main(["terms", "--root", str(tmp_path)]) == 1
        capsys.readouterr()


def test_duplicate_overlay_sources_report_both_paths(tmp_path, capsys):
    make_repo(tmp_path, {"session.md": REC_SESSION}, {"README.md": "[[session]]"},
              'glossary: ["glossary/*.md"]\ndocs: [README.md]\n')
    overlays = tmp_path / ".ubiq/overlays"
    overlays.mkdir(parents=True)
    for name in ("first", "second"):
        (overlays / f"{name}.md").write_text(
            f"---\nsource: glossary/session.md\naliases: [{name}]\n---\n")
    status, result = check_json(tmp_path, capsys)
    assert status == 1
    diag = next(d for d in result["diagnostics"] if d["code"] == "E005")
    assert "first.md" in diag["message"] and "second.md" in diag["message"]


def test_overlay_can_define_a_selected_source_without_term(tmp_path, capsys):
    make_repo(tmp_path, {"session.md": "A definition without metadata."},
              {"README.md": "[[session]]"},
              'glossary: ["glossary/*.md"]\ndocs: [README.md]\n')
    overlays = tmp_path / ".ubiq/overlays"
    overlays.mkdir(parents=True)
    (overlays / "session.md").write_text(
        "---\nsource: glossary/session.md\nterm: session\n---\n")
    status, result = check_json(tmp_path, capsys)
    assert status == 0 and result["terms"] == 1
    assert len(build(tmp_path)) == 4


def test_refs_json_filters_and_default_text(tmp_path, capsys):
    make_repo(tmp_path, {"session.md": REC_SESSION},
              {"README.md": "[[session]] then session. [play](glossary/session.md)\n",
               "CHANGELOG.md": "[[session]]\n"},
              'glossary: ["glossary/*.md"]\ndocs: [README.md]\nhistorical: [CHANGELOG.md]\n')
    args = ["refs", "session", "--root", str(tmp_path)]
    assert main(args) == 0
    text = capsys.readouterr().out
    assert "defined: core:session" in text and "4 references" in text
    assert main([*args, "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["count"] == 4 and result["query"] == "session"
    assert result["definitions"][0]["file"] == "glossary/session.md"
    assert result["references"][0]["historical"] is True
    link = next(ref for ref in result["references"] if ref["kind"] == "markdown")
    assert link["destination"] == "glossary/session.md" and link["line"] == 1
    assert main([*args, "--json", "--kind", "explicit", "--kind", "markdown"]) == 0
    filtered = json.loads(capsys.readouterr().out)
    assert filtered["count"] == 3
    assert {ref["kind"] for ref in filtered["references"]} == {"explicit", "markdown"}
    assert main([*args, "--json", "--kind", "id"]) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 0


def test_refs_unknown_term_is_json_failure(tmp_path, capsys):
    assert main(["refs", "missing", "--root", str(tmp_path), "--json"]) == 1
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["definitions"] == [] and result["references"] == []
    assert result["count"] == 0 and "missing" in result["error"]
    assert output.err == ""


def test_refs_json_external_record_keeps_absolute_path(tmp_path, capsys):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text(REC_SESSION)
    (root / "glossary.md").symlink_to(outside)
    (root / "README.md").write_text("[[session]]")
    (root / "ubiq.yaml").write_text('glossary: [glossary.md]\ndocs: [README.md]\n')
    assert main(["refs", "session", "--root", str(root), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["definitions"][0]["file"] == str(outside)


def test_explain_tracks_discovery_without_crawling(tmp_path, capsys):
    config = ('glossary: ["glossary/*.md"]\ndocs: [README.md, "empty/*.md"]\n'
              'historical: [CHANGELOG.md]\nignore: [ignored.md]\n')
    make_repo(tmp_path, {"session.md": REC_SESSION}, {
        "README.md": "[next](next.md) [ignore](ignored.md) [history](CHANGELOG.md)",
        "next.md": "[back](README.md) [[session]]", "ignored.md": "[[ghost]]",
        "unseen.md": "[[ghost]]", "CHANGELOG.md": "[[old]]",
    }, config)
    args = ["explain", "--root", str(tmp_path), "--json"]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    files = {item["file"]: item for item in result["files"]}
    assert "unseen.md" not in files
    assert files["ignored.md"]["included"] is False
    assert files["ignored.md"]["reasons"][0]["ignored_by"] == "ignored.md"
    assert {r["kind"] for r in files["README.md"]["reasons"]} == {"docs", "link"}
    assert files["next.md"]["reasons"] == [{"kind": "link", "from": "README.md"}]
    assert files["CHANGELOG.md"]["historical"] is True
    assert {r["kind"] for r in files["CHANGELOG.md"]["reasons"]} == {"historical", "link"}
    assert {"kind": "docs", "pattern": "empty/*.md"} in result["unmatched"]
    assert main(args) == 0
    assert result == json.loads(capsys.readouterr().out)
    assert main(["explain", "--root", str(tmp_path)]) == 0
    assert "unmatched docs: empty/*.md" in capsys.readouterr().out


def test_invalid_utf8_overlay_is_reported_once(tmp_path, capsys):
    make_repo(tmp_path, {"session.md": REC_SESSION}, {"README.md": "[[session]]"},
              'glossary: ["glossary/*.md"]\ndocs: [README.md]\n')
    overlays = tmp_path / ".ubiq/overlays"
    overlays.mkdir(parents=True)
    (overlays / "bad.md").write_bytes(b"\xff")
    status, result = check_json(tmp_path, capsys)
    assert status == 1 and result["errors"] == 1
    assert result["diagnostics"][0]["code"] == "E005"
    assert result["diagnostics"][0]["file"] == ".ubiq/overlays/bad.md"


def test_overlay_missing_term_fails_with_and_without_glob(tmp_path, capsys):
    source = tmp_path / "source.md"
    source.write_text("No term here.")
    overlays = tmp_path / ".ubiq/overlays"
    overlays.mkdir(parents=True)
    (overlays / "source.md").write_text("---\nsource: source.md\n---\n")
    for globs in ("[]", "[source.md]"):
        (tmp_path / "ubiq.yaml").write_text(f"glossary: {globs}\ndocs: []\n")
        status, result = check_json(tmp_path, capsys)
        assert status == 1
        assert result["errors"] == 1
        assert result["diagnostics"][0]["code"] == "E005"
        assert "no defining term" in result["diagnostics"][0]["message"]


def test_invalid_overlay_source_path_is_diagnostic(tmp_path, capsys):
    (tmp_path / "ubiq.yaml").write_text("glossary: []\ndocs: []\n")
    overlays = tmp_path / ".ubiq/overlays"
    overlays.mkdir(parents=True)
    (overlays / "bad.md").write_text('---\nsource: "bad\\0path.md"\n---\n')
    status, result = check_json(tmp_path, capsys)
    assert status == 1 and result["errors"] == 1
    assert result["diagnostics"][0]["code"] == "E005"
    assert result["diagnostics"][0]["file"] == ".ubiq/overlays/bad.md"


def test_overflowing_config_patterns_are_diagnostics(tmp_path, capsys):
    for field in ("id_patterns", "external_id_patterns"):
        (tmp_path / "ubiq.yaml").write_text(f'{field}: ["a{{99999999999999999999999999999}}"]\n')
        status, result = check_json(tmp_path, capsys)
        assert status == 1 and result["errors"] == 1
        assert result["diagnostics"][0]["code"] == "E008"
        assert field in result["diagnostics"][0]["message"]
