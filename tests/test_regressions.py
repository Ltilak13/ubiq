"""Regressions: YAML scalar typing, delimiter false positives, resolve cost."""

import time
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


def test_delimiter_skips_bare_url_paths_and_queries(tmp_path, capsys):
    recs = {"tdd.md": "---\nterm: tdd\n---\n\nThe loop.\n"}
    doc = ("Run /tdd, then open https://example.com/?next=/nope or"
           " www.example.com/a/ghost and <https://x.dev/?to=/gone>.\n")
    cfg = 'glossary: ["glossary/**/*.md"]\ndocs: ["doc.md"]\ndelimiters: ["/"]\n'
    make_repo(tmp_path, recs, {"doc.md": doc}, config=cfg)
    assert main(["check", "--root", str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(["refs", "tdd", "--kind", "explicit", "--root", str(tmp_path)]) == 0
    assert capsys.readouterr().out.count("explicit '/tdd'") == 1


def test_address_scan_stays_linear_on_dotted_runs():
    from ubiq.scan import URL_RE
    start = time.perf_counter()
    assert not list(URL_RE.finditer("a." * 20000))
    assert time.perf_counter() - start < 1  # quadratic backtracking took ~4s
    # A version pin is not an email: `tdd@2.0` still mentions `tdd`.
    assert [m.group() for m in URL_RE.finditer("mail a.b+c@x.io, pin react@18.3.1")] == [
        "a.b+c@x.io"]


def test_version_pins_still_count_as_use(tmp_path, capsys):
    recs = {"tdd.md": "---\nterm: tdd\n---\n\nThe loop.\n"}
    make_repo(tmp_path, recs, {"doc.md": "Install tdd@2.0 or tdd@v1.x now.\n"})
    main(["check", "--root", str(tmp_path)])
    assert "W001" not in capsys.readouterr().out


def test_comments_hide_mentions_but_not_delimiters(tmp_path, capsys):
    recs = {"tdd.md": "---\nterm: tdd\n---\n\nThe loop.\n"}
    doc = ("<!-- tdd, then /ghost -->\n\nUse `<!--` and `https://x/?n=/gone` in code;"
           " tdd here.\n")
    cfg = ('glossary: ["glossary/**/*.md"]\ndocs: ["doc.md"]\ndelimiters: ["/"]\n'
           'unlinked_mentions: warn\n')
    make_repo(tmp_path, recs, {"doc.md": doc}, config=cfg)
    assert main(["check", "--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "unresolved reference /ghost" in out and "/gone" not in out
    assert [line for line in out.splitlines() if "W002" in line] == [
        line for line in out.splitlines() if "doc.md:3: W002" in line]
