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


def test_dogfood_ubiq_repo_is_clean():
    assert main(["check", "--root", str(ROOT)]) == 0
