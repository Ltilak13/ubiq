"""W002: unlinked mentions, once per term per section."""

import json

from ubiq.cli import main
from test_ubiq import REC_SESSION, make_repo

CFG = 'glossary: ["glossary/**/*.md"]\ndocs: ["**/*.md"]\nunlinked_mentions: warn\n'


def w002(tmp_path, capsys):
    status = main(["check", "--root", str(tmp_path), "--json"])
    out = json.loads(capsys.readouterr().out)
    found = [(d["file"], d["line"]) for d in out["diagnostics"] if d["code"] == "W002"]
    assert all(d["severity"] == "warning" for d in out["diagnostics"] if d["code"] == "W002")
    return status, found


def test_first_unlinked_mention_per_section(tmp_path, capsys):
    doc = ("A session starts. Another session follows.\n"  # 1: flagged once
           "\n"
           "## Session notes\n"                            # 3: heading, not flagged
           "\n"
           "Each [session](glossary/s.md) ends; the session is saved.\n"  # 5: linked
           "\n"
           "## Later\n"
           "\n"
           "Close the session.\n"                          # 9: new section, flagged
           "\n"
           "```\nsession in a fence\n```\n"
           "`session` in code.\n")
    make_repo(tmp_path, {"s.md": REC_SESSION}, {"doc.md": doc}, config=CFG)
    status, found = w002(tmp_path, capsys)
    assert status == 0
    assert found == [("doc.md", 1), ("doc.md", 9)]


def test_wiki_links_delimiters_and_ids_count_as_links(tmp_path, capsys):
    recs = {"s.md": "---\nterm: session\nid: S-1\n---\n\nPlay.\n",
            "t.md": "---\nterm: tdd\n---\n\nThe loop.\n"}
    doc = ("A [[session]] and a session.\n\n## Two\n\nRun /tdd: tdd first.\n\n"
           "## Three\n\nS-1 says the session ends.\n")
    cfg = CFG + 'delimiters: ["/"]\nid_patterns: ["\\\\bS-\\\\d+\\\\b"]\n'
    make_repo(tmp_path, recs, {"doc.md": doc}, config=cfg)
    assert w002(tmp_path, capsys) == (0, [])


def test_off_by_default_and_yaml_boolean_off(tmp_path, capsys):
    make_repo(tmp_path, {"s.md": REC_SESSION}, {"doc.md": "A session.\n"},
              config='glossary: ["glossary/**/*.md"]\ndocs: ["**/*.md"]\n')
    assert w002(tmp_path, capsys) == (0, [])
    for value in ("off", "false"):  # bare `off` loads as False in YAML 1.1
        (tmp_path / "ubiq.yaml").write_text(
            f'glossary: ["glossary/**/*.md"]\ndocs: ["**/*.md"]\nunlinked_mentions: {value}\n')
        assert w002(tmp_path, capsys) == (0, [])
    (tmp_path / "ubiq.yaml").write_text(
        'glossary: ["glossary/**/*.md"]\ndocs: ["**/*.md"]\nunlinked_mentions: loud\n')
    status = main(["check", "--root", str(tmp_path), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert status == 1 and out["diagnostics"][0]["code"] == "E008"


def test_skips_excepted_terms_own_record_sidecars_and_history(tmp_path, capsys):
    recs = {"s.md": "---\nterm: session\n---\n\nA session is play.\n",
            "pr.md": "---\nterm: pr\nns: skill\n---\n\nOpen a pull request.\n"}
    docs = {"doc.md": "Open a PR for the session.\n",
            "CHANGELOG.md": "Renamed session.\n"}
    cfg = CFG + 'historical: [CHANGELOG.md]\n'
    make_repo(tmp_path, recs, docs, config=cfg)
    overlays = tmp_path / ".ubiq/overlays"
    overlays.mkdir(parents=True)
    (overlays / "s.md").write_text("---\nsource: glossary/s.md\n---\n\nSession sidecar.\n")
    status, found = w002(tmp_path, capsys)
    assert status == 0 and sorted(found) == [("doc.md", 1), ("doc.md", 1)]

    for excepted in ("[pr]", "['skill:pr']"):
        (tmp_path / "ubiq.yaml").write_text(cfg + f"unlinked_except: {excepted}\n")
        assert w002(tmp_path, capsys) == (0, [("doc.md", 1)])


def test_urls_are_not_mentions_and_external_labels_count_as_links(tmp_path, capsys):
    doc = ("# A\n\nSee https://example.dev/skills-session now.\n"     # bare URL
           "\n# B\n\nSee [the page](https://example.dev/session).\n"  # destination
           "\n# C\n\nSee <https://example.dev/session>.\n"            # autolink
           '\n# D\n\nSee <a href="/session">here</a>.\n'              # HTML tag
           "\n# E\n\nThe [session](https://example.dev/s) page; the session ends.\n"
           "\n# F\n\nA plain session.\n")                             # 23: flagged
    make_repo(tmp_path, {"s.md": REC_SESSION}, {"doc.md": doc}, config=CFG)
    assert w002(tmp_path, capsys) == (0, [("doc.md", 23)])


def test_external_link_label_still_counts_as_use(tmp_path, capsys):
    make_repo(tmp_path, {"s.md": REC_SESSION},
              {"doc.md": "The [session](https://example.dev/s) page.\n"}, config=CFG)
    main(["check", "--root", str(tmp_path), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert [d for d in out["diagnostics"] if d["code"] == "W001"] == []


def test_slug_names_need_their_separator_but_spaced_names_do_not(tmp_path, capsys):
    recs = {"g.md": "---\nterm: grill-me\n---\n\nInterview.\n",
            "t.md": "---\nterm: issue tracker\n---\n\nWhere issues live.\n"}
    doc = ("# A\n\nDon't grill me, just show it.\n"   # ordinary phrase: not a mention
           "\n# B\n\nRun grill_me or grill-me.\n"     # 7: slug forms match
           "\n# C\n\nThe issue-tracker is set.\n")    # 11: spaced name, any separator
    make_repo(tmp_path, recs, {"doc.md": doc}, config=CFG)
    assert w002(tmp_path, capsys) == (0, [("doc.md", 7), ("doc.md", 11)])
