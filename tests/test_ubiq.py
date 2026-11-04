import json
from pathlib import Path

from ubiq.check import run_checks
from ubiq.cli import main
from ubiq.records import load_glossary, parse_record
from ubiq.scan import scan_docs

ROOT = Path(__file__).resolve().parents[1]


def make_repo(tmp_path: Path, records: dict[str, str], docs: dict[str, str],
              config: str | None = None) -> Path:
    (tmp_path / "glossary").mkdir(exist_ok=True)
    for name, body in records.items():
        (tmp_path / "glossary" / name).write_text(body)
    for name, body in docs.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    (tmp_path / "ubiq.yaml").write_text(config or
        'glossary: ["glossary/**/*.md"]\ndocs: ["**/*.md"]\n')
    return tmp_path


def diags_for(tmp_path, records, docs, id_patterns=(), ref_fields=(), external=()):
    root = make_repo(tmp_path, records, docs)
    glossary = load_glossary(list((root / "glossary").glob("*.md")))
    doc_files = [p for p in root.rglob("*.md")]
    refs = scan_docs(doc_files, glossary, list(id_patterns),
                     ref_fields=list(ref_fields))
    return run_checks(glossary, refs, list(external))


REC_SESSION = "---\nterm: session\n---\n\nA period of play.\n"


def codes(diags):
    return [d.code for d in diags]


def test_parse_record(tmp_path):
    p = tmp_path / "r.md"
    p.write_text("---\nterm: At-Bat\nns: Game\naliases: [ab]\nid: T1\n---\n\nOne attempt.\n")
    t = parse_record(p)
    assert t.term == "at bat" and t.ns == "game" and t.aliases == ["ab"] and t.id == "T1"
    assert t.definition == "One attempt."


def test_clean_repo_passes(tmp_path):
    d = diags_for(tmp_path, {"s.md": REC_SESSION}, {"doc.md": "Start a [[session]] now.\n"})
    assert codes(d) == []


def test_e001_duplicate(tmp_path):
    d = diags_for(tmp_path,
                  {"a.md": REC_SESSION, "b.md": "---\nterm: session\n---\n\nDupe.\n"},
                  {"doc.md": "A [[session]].\n"})
    assert "E001" in codes(d)


def test_e001_alias_collision(tmp_path):
    d = diags_for(tmp_path,
                  {"a.md": REC_SESSION,
                   "b.md": "---\nterm: meeting\naliases: [session]\n---\n\nAlias clash.\n"},
                  {"doc.md": "A [[meeting]] and a [[core:session]].\n"})
    assert "E001" in codes(d)


def test_e002_unresolved(tmp_path):
    d = diags_for(tmp_path, {"s.md": REC_SESSION}, {"doc.md": "See [[inning]].\n"})
    assert "E002" in codes(d)


def test_e003_ambiguous_and_qualified_ok(tmp_path):
    recs = {"a.md": "---\nterm: pitch\nns: game\n---\n\nA throw.\n",
            "b.md": "---\nterm: pitch\nns: sales\n---\n\nA spiel.\n"}
    d = diags_for(tmp_path, recs, {"doc.md": "Make a [[pitch]].\n"})
    assert "E003" in codes(d)
    d = diags_for(tmp_path, recs, {"doc.md": "Make a [[sales:pitch]] about a [[game:pitch]].\n"})
    assert not any(c.startswith("E") for c in codes(d))


def test_e004_unresolved_id(tmp_path):
    d = diags_for(tmp_path,
                  {"s.md": "---\nterm: session\nid: T1\n---\n\nPlay.\n"},
                  {"doc.md": "T1 is real but T9 is not.\n"},
                  id_patterns=[r"\bT\d+\b"])
    assert codes(d).count("E004") == 1


def test_e005_invalid_record(tmp_path):
    d = diags_for(tmp_path,
                  {"s.md": REC_SESSION,
                   "bad.md": "---\nterm: x\nnote: (meta: broken yaml)\n---\n\nOops.\n"},
                  {"doc.md": "A [[session]].\n"})
    assert "E005" in codes(d)


def test_explicit_ref_resolves_by_id(tmp_path):
    d = diags_for(tmp_path,
                  {"s.md": "---\nterm: initiation deficit\nid: T1\n---\n\nStarting costs.\n"},
                  {"doc.md": "See [[T1]] for why.\n"})
    assert codes(d) == []  # resolves by id, and the id ref satisfies the orphan check


def test_w001_orphan(tmp_path):
    d = diags_for(tmp_path,
                  {"s.md": REC_SESSION, "o.md": "---\nterm: dugout\n---\n\nUnused.\n"},
                  {"doc.md": "A [[session]].\n"})
    assert "W001" in codes(d)
    assert all(not x.is_error for x in d)


def test_mention_counts_for_orphan_but_never_errors(tmp_path):
    d = diags_for(tmp_path, {"s.md": REC_SESSION},
                  {"doc.md": "We had a good session yesterday.\n"})
    assert codes(d) == []  # mention satisfies orphan check, no explicit ref needed


def test_code_blocks_ignored(tmp_path):
    doc = "A [[session]].\n\n```\n[[not-a-term]] T99\n```\nAnd `[[also-not]]` inline.\n"
    d = diags_for(tmp_path, {"s.md": REC_SESSION}, {"doc.md": doc},
                  id_patterns=[r"\bT\d+\b"])
    assert codes(d) == []


def test_field_refs_resolve_and_credit_orphans(tmp_path):
    recs = {"t1.md": "---\nterm: initiation deficit\nid: T1\n---\n\nStarting.\n"}
    doc = "---\nid: widget-x\nsolves: [T1]\nserves: [R2]\n---\n\nBody.\n"
    # T1 resolves by id (and clears T1's orphan warning); R2 is E006 without allowlist
    d = diags_for(tmp_path, recs, {"w.md": doc}, ref_fields=["solves", "serves"])
    assert codes(d) == ["E006"] and "R2" in d[0].message
    d = diags_for(tmp_path, recs, {"w.md": doc}, ref_fields=["solves", "serves"],
                  external=[r"R\d"])
    assert codes(d) == []


def test_field_ref_placeholders_skipped(tmp_path):
    recs = {"t1.md": "---\nterm: thing\nid: T1\n---\n\nX.\n"}
    doc = "---\nsolves: [T1, na, —]\nbranch: none\n---\n\nBody.\n"
    d = diags_for(tmp_path, recs, {"w.md": doc}, ref_fields=["solves", "branch"])
    assert codes(d) == []


def test_cli_check_json_and_exit_codes(tmp_path, capsys):
    make_repo(tmp_path, {"s.md": REC_SESSION}, {"doc.md": "A [[session]].\n"})
    assert main(["check", "--root", str(tmp_path), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["errors"] == 0 and out["terms"] == 1

    (tmp_path / "bad.md").write_text("See [[ghost]].\n")
    assert main(["check", "--root", str(tmp_path)]) == 1


def test_cli_refs(tmp_path, capsys):
    make_repo(tmp_path, {"s.md": REC_SESSION},
              {"doc.md": "A [[session]] and later another session.\n"})
    assert main(["refs", "session", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "explicit" in out and "mention" in out


def test_init_scaffolds_and_passes_check(tmp_path, capsys):
    assert main(["init", "--root", str(tmp_path)]) == 0
    capsys.readouterr()
    (tmp_path / "README.md").write_text("Every term needs a [[glossary record]].\n")
    assert main(["check", "--root", str(tmp_path)]) == 0
    # refuses to clobber an existing config
    assert main(["init", "--root", str(tmp_path)]) == 1


def test_dogfood_ubiq_repo_is_clean():
    assert main(["check", "--root", str(ROOT)]) == 0


def test_delimiter_slash_resolves_including_inline_code(tmp_path, capsys):
    make_repo(tmp_path, {"s.md": REC_SESSION},
              {"doc.md": "Run `/session` then /session again.\n"},
              config='glossary: ["glossary/**/*.md"]\ndocs: ["**/*.md"]\ndelimiters: ["/"]\n')
    assert main(["check", "--root", str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(["refs", "session", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "explicit" in out


def test_delimiter_unresolved_is_e002(tmp_path):
    make_repo(tmp_path, {"s.md": REC_SESSION},
              {"doc.md": "Run /ghost now.\n"},
              config='glossary: ["glossary/**/*.md"]\ndocs: ["**/*.md"]\ndelimiters: ["/"]\n')
    assert main(["check", "--root", str(tmp_path)]) == 1


def test_delimiter_skips_html_relative_paths_and_urls(tmp_path):
    make_repo(tmp_path, {"s.md": REC_SESSION},
              {"doc.md": "</picture> [x](./MISSION-FORMAT.md) https://aihero.dev/x\n"
                         "`src/packages/<name>/index.ts`\n"
                         "Real ref: /session\n"},
              config='glossary: ["glossary/**/*.md"]\ndocs: ["**/*.md"]\ndelimiters: ["/"]\n')
    assert main(["check", "--root", str(tmp_path)]) == 0
    cfg = """
glossary: ["glossary/**/*.md"]
docs: ["**/*.md"]
delimiters:
  - pattern: "/"
    except: [clear]
"""
    make_repo(tmp_path, {"s.md": REC_SESSION},
              {"doc.md": "See [x](/skills/engineering/tdd) and /clear and /session.\n"
                         "Also mattpocock/skills is not a ref.\n"},
              config=cfg)
    assert main(["check", "--root", str(tmp_path)]) == 0


def test_glob_ns_without_editing_the_file(tmp_path, capsys):
    rec = "---\nname: tdd\n---\n\nThe loop.\n"
    cfg = """
glossary:
  - glob: "glossary/**/*.md"
    term_field: name
    ns: skill
docs: ["**/*.md"]
"""
    make_repo(tmp_path, {"t.md": rec}, {"doc.md": "Use [[tdd]] here.\n"}, config=cfg)
    assert main(["terms", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "skill:tdd" in out
    capsys.readouterr()
    assert main(["check", "--root", str(tmp_path)]) == 0


def test_overlay_on_key_yaml_boolean(tmp_path, capsys):
    """`on:` is True in YAML 1.1; the loader must still treat it as the source path."""
    rec = "---\nname: tdd\n---\n\nLoop.\n"
    overlay = "---\non: glossary/t.md\naliases: [tests]\n---\n\nSidecar.\n"
    cfg = """
glossary:
  - glob: "glossary/**/*.md"
    term_field: name
docs: ["**/*.md"]
overlays: [".ubiq/overlays/**/*.md"]
"""
    make_repo(tmp_path, {"t.md": rec}, {"doc.md": "See [[tdd]].\n"}, config=cfg)
    ov = tmp_path / ".ubiq" / "overlays"
    ov.mkdir(parents=True, exist_ok=True)
    (ov / "t.md").write_text(overlay)
    assert main(["terms", "--root", str(tmp_path)]) == 0
    assert "tests" in capsys.readouterr().out


def test_overlay_merges_uses_and_aliases(tmp_path, capsys):
    rec = "---\nname: implement\n---\n\nBuild it.\n"
    overlay = "---\nsource: glossary/i.md\nuses: [tdd]\naliases: [impl]\n---\n\nSidecar.\n"
    tdd = "---\nname: tdd\n---\n\nThe loop.\n"
    cfg = """
glossary:
  - glob: "glossary/**/*.md"
    term_field: name
    ns: skill
docs: ["**/*.md"]
overlays: [".ubiq/overlays/**/*.md"]
ref_fields: [uses]
"""
    make_repo(tmp_path, {"i.md": rec, "t.md": tdd}, {"doc.md": "See [[implement]].\n"},
              config=cfg)
    ov = tmp_path / ".ubiq" / "overlays"
    ov.mkdir(parents=True, exist_ok=True)
    (ov / "implement.md").write_text(overlay)
    assert main(["check", "--root", str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(["terms", "--root", str(tmp_path)]) == 0
    assert "impl" in capsys.readouterr().out
    capsys.readouterr()
    assert main(["refs", "tdd", "--root", str(tmp_path)]) == 0
    assert "field" in capsys.readouterr().out


def test_only_known_delimiter_skips_unknown(tmp_path):
    cfg = """
glossary: ["glossary/**/*.md"]
docs: ["**/*.md"]
delimiters:
  - pattern: "/"
    only_known: true
"""
    make_repo(tmp_path, {"s.md": REC_SESSION},
              {"doc.md": "Run /session and /ghost and /tmp.\n"}, config=cfg)
    assert main(["check", "--root", str(tmp_path)]) == 0


def test_only_known_false_still_errors_on_unknown(tmp_path):
    make_repo(tmp_path, {"s.md": REC_SESSION},
              {"doc.md": "Run /ghost now.\n"},
              config='glossary: ["glossary/**/*.md"]\ndocs: ["**/*.md"]\ndelimiters: ["/"]\n')
    assert main(["check", "--root", str(tmp_path)]) == 1


def test_historical_unresolved_does_not_fail(tmp_path, capsys):
    cfg = """
glossary: ["glossary/**/*.md"]
docs: ["README.md"]
historical: ["CHANGELOG.md"]
"""
    make_repo(tmp_path, {"s.md": REC_SESSION},
              {"README.md": "A [[session]].\n",
               "CHANGELOG.md": "Removed [[ghost]] and renamed /old-name.\n"},
              config=cfg)
    assert main(["check", "--root", str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(["refs", "session", "--root", str(tmp_path)]) == 0


def test_historical_does_not_hide_live_docs(tmp_path):
    cfg = """
glossary: ["glossary/**/*.md"]
docs: ["README.md"]
historical: ["CHANGELOG.md"]
"""
    make_repo(tmp_path, {"s.md": REC_SESSION},
              {"README.md": "See [[ghost]].\n",
               "CHANGELOG.md": "Removed [[ghost]].\n"},
              config=cfg)
    assert main(["check", "--root", str(tmp_path)]) == 1


def test_catalog_resolves_and_cover(tmp_path):
    rec = "---\nname: tdd\n---\n\nThe loop.\n"
    cfg = """
glossary:
  - glob: "glossary/**/*.md"
    term_field: name
docs: ["**/*.md"]
catalogs:
  - file: "plugin.json"
    items: skills
    term: basename
    cover: ["glossary/**/*.md"]
"""
    make_repo(tmp_path, {"tdd.md": rec}, {"doc.md": "See [[tdd]].\n"}, config=cfg)
    (tmp_path / "plugin.json").write_text(json.dumps({
        "skills": ["./skills/engineering/tdd"]
    }))
    assert main(["check", "--root", str(tmp_path)]) == 0


def test_catalog_unknown_entry_is_e006(tmp_path, capsys):
    rec = "---\nname: tdd\n---\n\nThe loop.\n"
    cfg = """
glossary:
  - glob: "glossary/**/*.md"
    term_field: name
docs: ["**/*.md"]
catalogs:
  - file: "plugin.json"
    items: skills
    term: basename
"""
    make_repo(tmp_path, {"tdd.md": rec}, {"doc.md": "See [[tdd]].\n"}, config=cfg)
    (tmp_path / "plugin.json").write_text(json.dumps({
        "skills": ["./skills/engineering/ghost"]
    }))
    assert main(["check", "--root", str(tmp_path), "--json"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert any(d["code"] == "E006" for d in out["diagnostics"])


def test_catalog_cover_gap_is_e007(tmp_path, capsys):
    rec = "---\nname: tdd\n---\n\nThe loop.\n"
    extra = "---\nname: grilling\n---\n\nGrill.\n"
    cfg = """
glossary:
  - glob: "glossary/**/*.md"
    term_field: name
docs: ["**/*.md"]
catalogs:
  - file: "plugin.json"
    items: skills
    term: basename
    cover: ["glossary/**/*.md"]
"""
    make_repo(tmp_path, {"tdd.md": rec, "g.md": extra},
              {"doc.md": "See [[tdd]] and [[grilling]].\n"}, config=cfg)
    (tmp_path / "plugin.json").write_text(json.dumps({
        "skills": ["./skills/engineering/tdd"]
    }))
    assert main(["check", "--root", str(tmp_path), "--json"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert any(d["code"] == "E007" for d in out["diagnostics"])


def test_terms_format_context(tmp_path, capsys):
    make_repo(tmp_path, {"s.md": REC_SESSION}, {"doc.md": "A [[session]].\n"})
    assert main(["terms", "--format", "context", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "## Language" in out and "**[[session]]**:" in out and "A period of play." in out


def test_wiki_link_filenames_are_not_unresolved_terms(tmp_path):
    make_repo(tmp_path, {"s.md": REC_SESSION},
              {"doc.md": "See [[GLOSSARY.md]] and [[./MISSION.md]] and [[dir/x.md]].\n"
                         "A [[session]].\n"})
    assert main(["check", "--root", str(tmp_path)]) == 0


def test_wiki_link_filename_that_is_a_term_still_resolves(tmp_path):
    rec = "---\nterm: SKILL.md\n---\n\nThe file.\n"
    make_repo(tmp_path, {"s.md": rec}, {"doc.md": "See [[SKILL.md]].\n"})
    assert main(["check", "--root", str(tmp_path)]) == 0


def test_path_wiki_link_follows_existing_file_into_scan(tmp_path):
    cfg = 'glossary: ["glossary/**/*.md"]\ndocs: ["README.md"]\n'
    make_repo(tmp_path, {"s.md": REC_SESSION},
              {"README.md": "See [[extra.md]].\nA [[session]].\n",
               "extra.md": "See [[ghost]].\n"},
              config=cfg)
    assert main(["check", "--root", str(tmp_path)]) == 1


def test_markdown_relative_link_is_followed(tmp_path):
    cfg = 'glossary: ["glossary/**/*.md"]\ndocs: ["README.md"]\n'
    make_repo(tmp_path, {"s.md": REC_SESSION},
              {"README.md": "See [x](./extra.md).\nA [[session]].\n",
               "extra.md": "See [[ghost]].\n"},
              config=cfg)
    assert main(["check", "--root", str(tmp_path)]) == 1


def test_dangling_path_wiki_link_is_not_an_error(tmp_path):
    cfg = 'glossary: ["glossary/**/*.md"]\ndocs: ["README.md"]\n'
    make_repo(tmp_path, {"s.md": REC_SESSION},
              {"README.md": "See [[MISSION.md]] and a [[session]].\n"},
              config=cfg)
    assert main(["check", "--root", str(tmp_path)]) == 0

