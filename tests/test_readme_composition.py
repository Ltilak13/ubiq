"""README declarations and explicit managed sections."""

from test_field_values import check
from test_ubiq import make_repo

START = "<!-- ubiq:readme:start -->\n"
END = "<!-- ubiq:readme:end -->\n"


def membership(diags):
    return [d for d in diags if d["code"] == "E015"]


def test_two_readmes_with_nested_parent(tmp_path, capsys):
    record = tmp_path / "skills" / "nested" / "closeout" / "SKILL.md"
    record.parent.mkdir(parents=True)
    record.write_text("---\nname: closeout\nreadme: [root, parent]\n"
                      "summary: Runs the audit.\ndescription: Audits tasks.\n---\n")
    (record.parent / "README.md").write_text("# Same folder\n")
    (tmp_path / "skills" / "README.md").write_text("# Farther ancestor\n")
    parent = tmp_path / "skills" / "nested" / "README.md"
    parent.write_text(START + "- [Audits tasks.](closeout/SKILL.md#description)\n" + END)
    (tmp_path / "ubiq.yaml").write_text(
        'docs: ["README.md"]\nglossary: [{glob: "skills/**/SKILL.md", term_field: name}]\n')
    (tmp_path / "README.md").write_text(
        START + "- [Runs the audit.](skills/nested/closeout/SKILL.md#summary)\n" + END)
    status, diags = check(tmp_path, capsys)
    assert status == 0, diags

    # The parent README is a scan input even when it is unreachable from docs.
    parent.write_text("# Unlisted\n")
    status, diags = check(tmp_path, capsys)
    assert status == 1
    [diag] = membership(diags)
    assert (diag["file"], diag["line"]) == ("skills/nested/closeout/SKILL.md", 3)
    assert "skills/nested/README.md" in diag["message"]


def test_configured_field_explicit_path_and_invalid_target(tmp_path, capsys):
    config = 'readme_field: indexes\ndocs: ["README.md"]\n'
    record = '---\nterm: example\n"indexes": [guide.md, unknown.md]\nsummary: Example\n---\n'
    make_repo(tmp_path, {"example.md": record}, {
        "README.md": "# Intro\n",
        "guide.md": START + "[Example](glossary/example.md#summary)\n" + END,
    }, config)
    status, diags = check(tmp_path, capsys)
    assert status == 1
    [diag] = membership(diags)
    assert (diag["file"], diag["line"]) == ("glossary/example.md", 3)
    assert "unknown.md" in diag["message"]


def test_only_managed_links_are_memberships(tmp_path, capsys):
    record = "---\nterm: feature\nsummary: A feature.\n---\n"
    readme = ("[Stale](glossary/feature.md#summary)\n" +
              "```md\n" + START + "[A feature.](glossary/feature.md#summary)\n" + END + "```\n" +
              START + "[A feature.](glossary/feature.md#summary)\n" + END)
    make_repo(tmp_path, {"feature.md": record}, {"README.md": readme}, "")
    status, diags = check(tmp_path, capsys)
    assert status == 1
    [diag] = membership(diags)
    assert (diag["file"], diag["line"]) == ("README.md", 8)
    assert any(d["code"] == "E013" and d["line"] == 1 for d in diags)

    (tmp_path / "glossary" / "feature.md").write_text(record.replace(
        "summary:", "readme: root\nsummary:"))
    (tmp_path / "README.md").write_text(
        "[A feature.](glossary/feature.md#summary)\n" + START +
        "<!-- [A feature.](glossary/feature.md#summary) -->\n" + END)
    status, diags = check(tmp_path, capsys)
    assert status == 1
    [diag] = membership(diags)
    assert (diag["file"], diag["line"]) == ("glossary/feature.md", 3)
    assert not any(d["code"] == "E013" for d in diags)


def test_overlay_membership_uses_source_location_and_overlay_line(tmp_path, capsys):
    make_repo(tmp_path, {"feature.md": "---\nterm: feature\nreadme: missing.md\n---\n"},
              {"README.md": "# Feature list\n"}, "")
    sidecar = tmp_path / ".ubiq" / "overlays" / "feature.md"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text("---\nsource: glossary/feature.md\nsummary: A feature.\nreadme: parent\n---\n")
    status, diags = check(tmp_path, capsys)
    assert status == 1
    [diag] = membership(diags)
    assert (diag["file"], diag["line"]) == (".ubiq/overlays/feature.md", 4)
    assert "README.md has no field link" in diag["message"]

    (tmp_path / "README.md").write_text(START + "[A feature.](glossary/feature.md#summary)\n" + END)
    status, diags = check(tmp_path, capsys)
    assert status == 0, diags



def test_historical_readmes_are_exempt_from_membership(tmp_path, capsys):
    make_repo(tmp_path, {"feature.md": "---\nterm: feature\nreadme: root\n---\n"},
              {"README.md": "# Archived feature list\n"},
              'historical: ["README.md"]\n')
    status, diags = check(tmp_path, capsys)
    assert status == 0, diags
    assert membership(diags) == []
