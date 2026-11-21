"""Regressions: YAML scalar typing, delimiter false positives, resolve cost."""

from pathlib import Path

from ubiq.check import run_checks
from ubiq.cli import build, main
from test_ubiq import make_repo


def test_record_scalars_stay_text(tmp_path, capsys):
    """YAML 1.1 would read `No` as False, `007` as 7, and `1.10` as 1.1."""
    recs = {
        "no.md": "---\nterm: No\naliases: [off]\n---\n\nA refusal.\n",
        "agent.md": "---\nterm: agent\nid: 007\n---\n\nSecret.\n",
        "release.md": "---\nterm: release\nid: 1.10\n---\n\nVersion.\n",
    }
    doc = ("---\nuses: [007, 1.10]\n---\n\n"
           "See [the refusal](glossary/no.md), [[off]], and [[agent]].\n")
    cfg = 'glossary: ["glossary/**/*.md"]\ndocs: ["doc.md"]\nref_fields: [uses]\n'
    make_repo(tmp_path, recs, {"doc.md": doc}, config=cfg)
    assert main(["check", "--root", str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(["terms", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "core:no" in out and "[007]" in out and "[1.10]" in out


def test_catalog_yaml_scalars_stay_text(tmp_path):
    recs = {"agent.md": "---\nterm: agent\nid: 007\n---\n\nSecret.\n"}
    cfg = ('glossary: ["glossary/**/*.md"]\ndocs: []\ncatalogs:\n'
           '  - file: inventory.yaml\n    term: literal\n    cover: ["glossary/**/*.md"]\n')
    make_repo(tmp_path, recs, {}, config=cfg)
    (tmp_path / "inventory.yaml").write_text("skills: [007]\n")
    assert main(["check", "--root", str(tmp_path)]) == 0


def test_delimiter_skips_link_destinations_and_html_attributes(tmp_path, capsys):
    recs = {"tdd.md": "---\nterm: tdd\n---\n\nThe loop.\n"}
    doc = ("Run /tdd first, or [run /tdd](./other.md).\n\n"
           "See the [setup guide](/setup.md), ![logo](/logo.png), and\n"
           '<a href="/install">install</a> or <img\n  src="/hero">.\n')
    cfg = 'glossary: ["glossary/**/*.md"]\ndocs: ["doc.md"]\ndelimiters: ["/"]\n'
    make_repo(tmp_path, recs, {"doc.md": doc, "other.md": "Other.\n"}, config=cfg)
    assert main(["check", "--root", str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(["refs", "tdd", "--kind", "explicit", "--root", str(tmp_path)]) == 0
    assert capsys.readouterr().out.count("explicit '/tdd'") == 2

    (tmp_path / "doc.md").write_text("Run /ghost, then read [setup](/setup.md).\n")
    assert main(["check", "--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "/ghost" in out and "/setup" not in out


def test_checks_resolve_paths_once_not_per_term(tmp_path):
    """Markdown links used to call Path.resolve() for every term, per reference."""
    recs = {f"t{i}.md": f"---\nterm: t{i}\n---\n\nTerm {i}.\n" for i in range(40)}
    links = "\n".join(f"[t{i % 40}](glossary/t{i % 40}.md)" for i in range(200))
    make_repo(tmp_path, recs, {"doc.md": links + "\n"},
              config='glossary: ["glossary/**/*.md"]\ndocs: ["doc.md"]\n')
    glossary, refs, cfg, _ = build(tmp_path)
    assert len([r for r in refs if r.kind == "markdown"]) == 200

    calls = 0
    original = Path.resolve

    def counting(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original(self, *args, **kwargs)

    Path.resolve = counting
    try:
        diags = run_checks(glossary, refs, cfg["external_id_patterns"])
    finally:
        Path.resolve = original
    assert not [d for d in diags if d.is_error]
    assert calls < 20, calls  # was 16,000+ (200 refs x 40 terms x 2 passes)
