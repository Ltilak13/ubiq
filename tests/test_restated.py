"""W008: a record body restates a configured frontmatter value."""

import json

from test_ubiq import make_repo

from ubiq.cli import main

CFG = 'glossary: ["glossary/**/*.md"]\ndocs: ["**/*.md"]\nrestated_values: [pct, label, flag, unit, name]\n'


def w008(tmp_path, capsys):
    status = main(["check", "--root", str(tmp_path), "--json"])
    out = json.loads(capsys.readouterr().out)
    return status, [(d["file"], d["line"], d["severity"]) for d in out["diagnostics"]
                    if d["code"] == "W008"]


def test_reports_each_restated_field_once_outside_code_and_links(tmp_path, capsys):
    record = ("---\nterm: discount\npct: 10\nlabel: Spring Sale\nflag: true\nunit: x\n"
              "name: discount\nother: 42\n---\n\n"
              "```\npct is 10 here\n```\n"          # 12: fenced, ignored
              "Inline `10` and [10](https://e.dev/10) are code and links.\n"  # 14
              "Prices drop 100 or 10.5 units on 2026-10-01 at 10:30 for 10,000 users "
              "(ISSUE-10, 1/10); 42 is unconfigured.\n"                      # 15: numbers
              "The discount is true at x.\n"        # 16: boolean, short value, term
              "It takes 10% off.\n"                  # 17: flagged
              "Again 10%. The spring\n"             # 18: wrapped label flagged, pct once
              "sale ends.\n")
    make_repo(tmp_path, {"d.md": record}, {}, config=CFG)
    status, found = w008(tmp_path, capsys)
    assert status == 0
    assert found == [("glossary/d.md", 17, "warning"), ("glossary/d.md", 18, "warning")]


def test_off_by_default(tmp_path, capsys):
    record = "---\nterm: discount\npct: 10\n---\n\nIt takes 10% off.\n"
    make_repo(tmp_path, {"d.md": record}, {})
    assert w008(tmp_path, capsys) == (0, [])


def test_rejects_invalid_setting(tmp_path, capsys):
    make_repo(tmp_path, {}, {}, config=CFG.replace("[pct, label, flag, unit, name]", "pct: 1"))
    status = main(["check", "--root", str(tmp_path), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert status == 1 and out["diagnostics"][0]["code"] == "E008"
