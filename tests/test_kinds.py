"""Reference-kind policies, `references:` config, and the spec guarantees."""

import json
import re
from itertools import combinations
from pathlib import Path

from test_ubiq import make_repo

from ubiq.cli import build, main
from ubiq.config import load_config
from ubiq.graph import KINDS as EDGE_KINDS
from ubiq.kinds import GUARANTEES, POLICIES, Context
from ubiq.scan import scan_file

SPEC = Path(__file__).resolve().parents[1] / "docs" / "spec.md"
REC = "---\nterm: session\nid: UB-1\n---\n\nA period of play.\n"
BASE = ('glossary: ["glossary/*.md"]\ndocs: ["doc.md"]\nref_fields: [uses]\n'
        'id_patterns: ["\\\\bUB-\\\\d+\\\\b"]\ndelimiters: ["/"]\n')


def check_json(root, capsys):
    status = main(["check", "--root", str(root), "--json"])
    return status, json.loads(capsys.readouterr().out)


def test_every_guarantee_is_quoted_from_the_spec():
    spec = " ".join(SPEC.read_text(encoding="utf-8").split())
    for guarantee in GUARANTEES:
        assert guarantee.spec in spec, guarantee.spec


def test_no_configuration_scans_fences_frontmatter_or_definitions(tmp_path):
    """Every scannable region, for every kind, still leaves guarded lines alone."""
    everything = "[[session]] /session `/session` UB-1 session [s](glossary/s.md)"
    doc = (f"---\nuses: [session]\nnote: \"{everything}\"\n---\n"   # lines 1-4
           f"[def]: glossary/s.md \"{everything}\"\n"               # line 5
           f"~~~\n{everything} <!-- [[session]] -->\n~~~\n"          # lines 6-8
           f"Prose {everything} [def] <!-- {everything} --> https://x.io/UB-1/session\n")
    make_repo(tmp_path, {"s.md": REC}, {"doc.md": doc}, BASE)
    glossary = build(tmp_path).glossary
    guarded = set(range(1, 9))
    tried = 0
    for name, policy in POLICIES.items():
        members = [flag for flag in Context if flag and flag in policy.scannable]
        for size in range(len(members) + 1):
            for regions in combinations(members, size):
                scans = json.dumps([flag.name.lower() for flag in regions])
                (tmp_path / "ubiq.yaml").write_text(
                    BASE + f"references: {{{name}: {{scans: {scans}}}}}\n")
                refs = scan_file(tmp_path / "doc.md", glossary, load_config(tmp_path))
                leaked = [(r.policy.name, r.line) for r in refs
                          if r.line in guarded and r.policy.name != "field"]
                assert not leaked, (name, scans, leaked)
                assert any(r.policy.name == name for r in refs) or name in (
                    "field", "catalog"), (name, scans)
                tried += 1
    assert tried > 20


def test_mention_severity_cannot_fail_the_build(tmp_path, capsys):
    make_repo(tmp_path, {"s.md": REC}, {"doc.md": "session\n"},
              BASE + "references: {mention: {severity: error}}\n")
    status, result = check_json(tmp_path, capsys)
    assert status == 1
    message = result["diagnostics"][0]["message"]
    assert result["diagnostics"][0]["code"] == "E008"
    assert "references.mention.severity" in message and "can never fail the build" in message


def setting(path, value):
    """A dotted setting and its value as one line of flow-style YAML."""
    *keys, last = path.split(".")
    text = f"{last}: {value}"
    for key in reversed(keys):
        text = f"{key}: {{{text}}}"
    return text + "\n"


INCLUDES = 'glossary: ["glossary/*.md", {glob: "parts/*.md", ns: part}]\ndocs: ["doc.md"]\n'


def test_every_severity_setting_keeps_every_guarantee(tmp_path, capsys):
    """Each allowed value keeps both checked guarantees, or is E008 naming the one it breaks."""
    make_repo(tmp_path, {"s.md": REC},
              {"doc.md": "A session.\n\nFollow [gone](parts/gone.md).\n"}, INCLUDES)
    levels = ("error", "warn", "off")
    settings = {**{f"references.{name}.severity": levels for name in POLICIES},
                "unlinked_mentions": ("warn", "off"),
                **{f"edges.{kind}.severity": levels for kind in EDGE_KINDS}}
    rejected = set()
    for path, values in settings.items():
        for value in values:
            (tmp_path / "ubiq.yaml").write_text(INCLUDES + setting(path, value))
            status, result = check_json(tmp_path, capsys)
            diags = result["diagnostics"]
            assert status == 1, (path, value, diags)
            if diags[0]["code"] == "E008":
                assert f"{path}: {value} contradicts the spec guarantee" in diags[0]["message"]
                rejected.add((path, value))
                continue
            # The link to a missing part (line 3) fails; the plain mention (line 1) never does.
            errors = [(d["code"], d["line"]) for d in diags if d["severity"] == "error"]
            assert errors == [("E002", 3)], (path, value, diags)
    assert rejected == {("references.mention.severity", "error"),
                        ("references.markdown.severity", "warn"),
                        ("references.markdown.severity", "off")}


def test_kind_severity_downgrades_or_silences_failures(tmp_path, capsys):
    doc = "[[session]] then UB-9, /ghost, and <!-- [[ghost]] -->.\n"
    make_repo(tmp_path, {"s.md": REC}, {"doc.md": doc}, BASE)
    status, result = check_json(tmp_path, capsys)
    assert status == 1
    assert sorted(d["code"] for d in result["diagnostics"]) == ["E002", "E002", "E004"]

    (tmp_path / "ubiq.yaml").write_text(BASE + (
        "references:\n  id: {severity: warn}\n  delimiter: {severity: off}\n"
        "  wiki: {scans: []}\n"))
    status, result = check_json(tmp_path, capsys)
    assert status == 0, result
    assert [(d["code"], d["severity"]) for d in result["diagnostics"]] == [("E004", "warning")]
    assert main(["check", "--root", str(tmp_path)]) == 0
    assert "E004 (warning) unresolved id 'UB-9'" in capsys.readouterr().out
    # Silenced refs are still indexed for search.
    assert main(["refs", "session", "--root", str(tmp_path), "--kind", "delimiter"]) == 0


def test_unlinked_mentions_is_mention_severity(tmp_path, capsys):
    for setting in ("unlinked_mentions: warn\n", "references: {mention: {severity: warn}}\n"):
        make_repo(tmp_path, {"s.md": REC}, {"doc.md": "A session.\n"}, BASE + setting)
        status, result = check_json(tmp_path, capsys)
        assert status == 0 and [d["code"] for d in result["diagnostics"]] == ["W002"]


def test_references_config_names_the_bad_setting(tmp_path, capsys):
    cases = {
        "references: {wikki: {severity: warn}}": "references.wikki: unknown kind",
        "references: {id: {level: warn}}": "references.id: unknown setting level",
        "references: {id: {severity: loud}}": "references.id.severity: expected error, warn, or off",
        "references: {id: {scans: [urls]}}": "references.id.scans: unknown region urls",
        "references: {markdown: {scans: [inline_code]}}":
            "references.markdown.scans: markdown cannot scan inline_code",
        "references: [id]": "references: expected a mapping",
        "edges: {include: {severity: loud}}": "edges.include.severity: expected error, warn, or off",
        "edges: {route: {severty: warn}}":
            "edges.route: unknown setting severty; did you mean severity?",
        "glosary: [x]": "unknown setting glosary; did you mean glossary?",
        "glossary: [{glob: 'g/*.md', term_feild: name}]":
            "glossary[0]: unknown setting term_feild; did you mean term_field?",
        "delimiters: [{pattern: '/', excpet: [x]}]":
            "delimiters[0]: unknown setting excpet; did you mean except?",
        "catalogs: [{file: c.json, cover: [], itmes: skills}]":
            "catalogs[0]: unknown setting itmes; did you mean items?",
    }
    for setting, expected in cases.items():
        make_repo(tmp_path, {"s.md": REC}, {"doc.md": "x\n"}, BASE + setting + "\n")
        status, result = check_json(tmp_path, capsys)
        assert status == 1 and result["diagnostics"][0]["code"] == "E008", setting
        assert expected in result["diagnostics"][0]["message"], result["diagnostics"][0]


def test_refs_kind_selects_a_policy_and_json_names_it(tmp_path, capsys):
    make_repo(tmp_path, {"s.md": REC}, {"doc.md": "[[session]] and /session\n"}, BASE)
    args = ["refs", "session", "--root", str(tmp_path), "--json"]
    for kinds, expected in ((["explicit"], ["delimiter", "wiki"]), (["wiki"], ["wiki"]),
                            (["delimiter"], ["delimiter"])):
        assert main([*args, *(f"--kind={k}" for k in kinds)]) == 0
        refs = json.loads(capsys.readouterr().out)["references"]
        assert sorted(r["policy"] for r in refs) == expected
        assert {r["kind"] for r in refs} == {"explicit"}


def test_mentions_match_names_that_start_or_end_in_punctuation(tmp_path, capsys):
    recs = {"c.md": "---\nterm: C++\n---\n\nA language.\n",
            "n.md": "---\nterm: .NET\n---\n\nA platform.\n"}
    make_repo(tmp_path, recs, {"doc.md": "We write C++ on .NET, not ASP.NET or C++x.\n"},
              'glossary: ["glossary/*.md"]\ndocs: ["doc.md"]\n')
    for term, count in (("c++", 1), (".net", 1)):
        assert main(["refs", term, "--root", str(tmp_path), "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["count"] == count, term


def test_colons_are_part_of_a_name_unless_the_prefix_is_a_namespace(tmp_path, capsys):
    recs = {"r.md": "---\nterm: 'ratio:2'\n---\n\nTwo to one.\n",
            "g.md": "---\nterm: session\nns: game\n---\n\nPlay.\n"}
    doc = "[[ratio:2]], [[game:session]], and [[nope:session]].\n"
    make_repo(tmp_path, recs, {"doc.md": doc}, 'glossary: ["glossary/*.md"]\ndocs: ["doc.md"]\n')
    status, result = check_json(tmp_path, capsys)
    assert status == 1
    assert [d["message"] for d in result["diagnostics"] if d["code"] == "E002"] == [
        "unresolved reference [[nope:session]] — no defining record. Did you mean [[session]]?"]


def test_ambiguity_reports_e003_only_when_qualifying_helps(tmp_path, capsys):
    dupe = {"a.md": REC.replace("id: UB-1\n", ""), "b.md": REC.replace("id: UB-1\n", "")}
    make_repo(tmp_path, dupe, {"doc.md": "[[session]]\n"},
              'glossary: ["glossary/*.md"]\ndocs: ["doc.md"]\n')
    _, result = check_json(tmp_path, capsys)
    assert [d["code"] for d in result["diagnostics"] if d["severity"] == "error"] == ["E001"]

    (tmp_path / "glossary/b.md").write_text("---\nterm: session\nns: game\n---\n\nPlay.\n")
    _, result = check_json(tmp_path, capsys)
    e003 = [d["message"] for d in result["diagnostics"] if d["code"] == "E003"]
    assert len(e003) == 1 and re.search(r"\[\[core:session\]\], \[\[game:session\]\]", e003[0])
