"""`acyclic` from `x-ubiq-ref`: a cycle fails `ubiq check` (E013)."""
import json

from ubiq import xref
from ubiq.cli import main

# -- E013: acyclic ---------------------------------------------------------------------

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
    "properties": {"name": {"type": "string"}, "issue": {"type": "integer"},
                   "requires": {"type": "array", "items": {"type": "string"},
                                "x-ubiq-ref": {"ns": "feature", "edge": "requires", "acyclic": True}}}}


def features(root, **requires):
    (root / "schema.json").write_text(json.dumps(SCHEMA))
    (root / "f").mkdir()
    for name, needs in requires.items():
        (root / f"f/{name}.md").write_text(
            f"---\nname: {name}\nrequires: [{', '.join(needs)}]\n---\n\nThe {name} feature.\n")
    (root / "ubiq.yaml").write_text(
        'glossary:\n  - {glob: "f/*.md", term_field: name, ns: feature}\ndocs: ["f/*.md"]\n'
        'schemas:\n  - schema: schema.json\n    files: ["f/*.md"]\n    format: frontmatter\n')


def check(root, capsys):
    status = main(["check", "--root", str(root), "--json"])
    report = json.loads(capsys.readouterr().out)
    return status, [d for d in report["diagnostics"] if d["code"] == "E013"], report


def test_a_requires_cycle_fails_check_and_names_it(tmp_path, capsys):
    features(tmp_path, a=["b"], b=["c"], c=["a"], d=["a"])
    status, found, _ = check(tmp_path, capsys)
    assert status == 1
    [error] = found
    assert error["message"] == "requires cycle: a -> b -> c -> a"
    assert error["file"].endswith("f/a.md") and error["line"] == 3


def test_a_self_requirement_is_a_cycle(tmp_path, capsys):
    features(tmp_path, a=["a"])
    assert [d["message"] for d in check(tmp_path, capsys)[1]] == ["requires cycle: a -> a"]


def test_a_dag_passes_and_pr_entries_are_not_records(tmp_path, capsys):
    features(tmp_path, a=["b", "'pr: 7'"], b=[], c=["a", "b"])
    status, found, report = check(tmp_path, capsys)
    assert found == [] and status == 0, report


def test_find_cycles_reports_each_loop_once():
    edges = {"a": ["b"], "b": ["a", "c"], "c": ["c"], "d": ["a"]}
    assert xref.find_cycles(edges) == [["a", "b", "a"], ["c", "c"]]
    assert xref.find_cycles({"a": ["b"], "b": []}) == []


def test_pr_entry():
    assert xref.pr_entry("pr: 12") == 12 and xref.pr_entry("pr:12") == 12
    assert xref.pr_entry("alpha") is None and xref.pr_entry("pr: x") is None
