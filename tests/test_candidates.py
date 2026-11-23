"""ubiq candidates: backticked identifiers used across docs with no record."""

import json

from test_ubiq import make_repo

from ubiq.cli import main

CFG = ('glossary: ["glossary/**/*.md"]\ndocs: ["**/*.md"]\n'
       'historical: [CHANGELOG.md]\n')
RECORD = "---\nterm: grill-me\naliases: [grill-session]\n---\n\nInterview.\n"


def candidates(tmp_path, capsys, *extra):
    status = main(["candidates", "--root", str(tmp_path), "--json", *extra])
    return status, json.loads(capsys.readouterr().out)


def test_identifiers_in_two_docs_without_a_record(tmp_path, capsys):
    docs = {
        "a.md": "Label it `needs-triage`, then `ready-for-agent`.\n\nAgain `needs-triage`.\n",
        "b.md": ("Use `needs-triage` and `grill-me` and `grill-session`.\n"
                 "```\n`ready-for-agent` in a fence\n```\n"
                 "Not identifiers: `notes.md-x.md`, `--no-verify`, `Needs-Triage`, `one`.\n"),
        "c.md": "Only here: `ready-for-agent`.\n",
        "CHANGELOG.md": "Renamed `to-prd` and `needs-triage`.\n",
        "d.md": "Old `to-prd`.\n",
    }
    make_repo(tmp_path, {"g.md": RECORD}, docs, config=CFG)
    status, out = candidates(tmp_path, capsys)
    assert status == 0
    assert out == {"min_files": 2, "count": 2, "candidates": [
        {"name": "needs-triage", "files": 2, "occurrences": 3, "locations": [
            {"file": "a.md", "line": 1}, {"file": "a.md", "line": 3},
            {"file": "b.md", "line": 1}]},
        {"name": "ready-for-agent", "files": 2, "occurrences": 2, "locations": [
            {"file": "a.md", "line": 1}, {"file": "c.md", "line": 1}]},
    ]}


def test_min_files_and_text_output(tmp_path, capsys):
    make_repo(tmp_path, {}, {"a.md": "Run `to-prd` and `to-prd`.\n"}, config=CFG)
    status, out = candidates(tmp_path, capsys, "--min-files", "1")
    assert status == 0 and [c["name"] for c in out["candidates"]] == ["to-prd"]
    assert main(["candidates", "--root", str(tmp_path), "--min-files", "1"]) == 0
    assert capsys.readouterr().out == "to-prd — 1 file, 2 uses: a.md:1\n1 candidate\n"


def test_never_writes_files(tmp_path, capsys):
    root = make_repo(tmp_path, {}, {"a.md": "`x-y`\n", "b.md": "`x-y`\n"}, config=CFG)
    before = sorted((p, p.read_bytes()) for p in root.rglob("*") if p.is_file())
    candidates(tmp_path, capsys)
    assert sorted((p, p.read_bytes()) for p in root.rglob("*") if p.is_file()) == before


BOLD_DOCS = {
    "a.md": ("**Tracer bullet**: a thin slice. Label `ready-for-agent`.\n"
             "Keep the **seam** small. **Grill me** first, ***both*** too.\n"),
    "b.md": ("1. **tracer bullet:** again, **ready for agent** too.\n"
             "**Seam** and **not a name!** and \\*\\*escaped\\*\\* and \\**escaped**.\n"
             "`**in code**`, snake__case__ and __case__x, __adapter__.\n"
             "```\n**fenced**\n```\n"),
    # Each rejected shape repeats here, so it would reach two files if it leaked.
    "c.md": ("---\ntitle: \"**front**\"\n---\n**adapter** **fenced** **in code** **front**"
             " **not a name!** \\*\\*escaped\\*\\* \\**escaped** snake__case__ __case__x"
             " **grill-me** ***both***\n"),
}


def test_bold_is_opt_in(tmp_path, capsys):
    make_repo(tmp_path, {"g.md": RECORD}, BOLD_DOCS, config=CFG)
    _, out = candidates(tmp_path, capsys, "--min-files", "1")
    assert [c["name"] for c in out["candidates"]] == ["ready-for-agent"]


def test_bold_names_merge_by_normalized_name(tmp_path, capsys):
    make_repo(tmp_path, {"g.md": RECORD}, BOLD_DOCS,
              config=CFG + "candidate_shapes: [code, bold]\n")
    status, out = candidates(tmp_path, capsys)
    assert status == 0
    assert out["candidates"] == [
        {"name": "adapter", "files": 2, "occurrences": 2, "locations": [
            {"file": "b.md", "line": 3}, {"file": "c.md", "line": 4}]},
        {"name": "both", "files": 2, "occurrences": 2, "locations": [
            {"file": "a.md", "line": 2}, {"file": "c.md", "line": 4}]},
        {"name": "ready-for-agent", "files": 2, "occurrences": 2, "locations": [
            {"file": "a.md", "line": 1}, {"file": "b.md", "line": 1}]},
        {"name": "seam", "files": 2, "occurrences": 2, "locations": [
            {"file": "a.md", "line": 2}, {"file": "b.md", "line": 2}]},
        {"name": "Tracer bullet", "files": 2, "occurrences": 2, "locations": [
            {"file": "a.md", "line": 1}, {"file": "b.md", "line": 1}]},
    ]


def test_bold_alone_drops_code_spans(tmp_path, capsys):
    make_repo(tmp_path, {}, BOLD_DOCS, config=CFG + "candidate_shapes: bold\n")
    _, out = candidates(tmp_path, capsys)
    assert "ready-for-agent" not in [c["name"] for c in out["candidates"]]
    assert out["candidates"][-1]["locations"] == [{"file": "a.md", "line": 1},
                                                  {"file": "b.md", "line": 1}]


def test_invalid_candidate_shapes(tmp_path, capsys):
    for value, message in (("[code, bolds]", "unknown shape bolds; did you mean bold?"),
                           ("[]", "expected at least one shape")):
        make_repo(tmp_path, {}, {"a.md": "x\n"}, config=CFG + f"candidate_shapes: {value}\n")
        status, out = candidates(tmp_path, capsys)
        assert status == 1
        assert out["diagnostics"][0]["code"] == "E008"
        assert out["diagnostics"][0]["message"] == f"candidate_shapes: {message}"
