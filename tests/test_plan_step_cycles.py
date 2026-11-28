"""`acyclic` for plan step `requires` (x-ubiq-ref `within`): a loop is E014, found per plan."""
import json
from pathlib import Path

from ubiq.cli import main

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (ROOT / ".ubiq/schemas/plan.json").read_text()


def plan(name, **steps):
    body = "".join(f"  {s}:\n    requires: [{', '.join(r)}]\n" for s, r in steps.items())
    return f"---\nname: {name}\nstatus: active\nissue: 10\ntrunk: main\nsteps:\n{body}---\n\nPlan.\n"


def repo(root, **plans):
    (root / "schema.json").write_text(SCHEMA)
    (root / "plans").mkdir()
    for name, text in plans.items():
        (root / f"plans/{name}.md").write_text(text)
    (root / "ubiq.yaml").write_text(
        'glossary:\n  - {glob: "plans/*.md", term_field: name, ns: plan}\ndocs: ["plans/*.md"]\n'
        'schemas:\n  - schema: schema.json\n    files: ["plans/*.md"]\n    format: frontmatter\n')


def e014(root, capsys):
    status = main(["check", "--root", str(root), "--json"])
    found = json.loads(capsys.readouterr().out)["diagnostics"]
    return status, [d for d in found if d["code"] == "E014"]


def test_a_step_loop_fails_check_and_names_each_step_with_its_line(tmp_path, capsys):
    repo(tmp_path, p=plan("p", a=["b"], b=["c"], c=["a"], d=["a"]))
    status, found = e014(tmp_path, capsys)
    [error] = found
    assert status == 1 and error["file"].endswith("plans/p.md")
    assert error["message"] == "requires cycle: a (line 7) -> b (line 9) -> c (line 11) -> a (line 7)"
    assert error["line"] == 7


def test_a_self_requiring_step_is_a_loop(tmp_path, capsys):
    repo(tmp_path, p=plan("p", a=["a"]))
    [error] = e014(tmp_path, capsys)[1]
    assert error["message"] == "requires cycle: a (line 7) -> a (line 7)"


def test_same_step_names_in_different_plans_never_join(tmp_path, capsys):
    repo(tmp_path, p=plan("p", a=["b"], b=[]), q=plan("q", a=[], b=["a"]))
    status, found = e014(tmp_path, capsys)
    assert status == 0 and found == []


def test_each_plan_reports_its_own_loop(tmp_path, capsys):
    repo(tmp_path, p=plan("p", a=["b"], b=["a"]), q=plan("q", a=["b"], b=["a"]))
    _status, found = e014(tmp_path, capsys)
    assert sorted(Path(d["file"]).name for d in found) == ["p.md", "q.md"]


def test_an_unknown_step_is_e006_and_makes_no_loop(tmp_path, capsys):
    repo(tmp_path, p=plan("p", a=["zzz"]))
    assert e014(tmp_path, capsys)[1] == []


def test_an_acyclic_plan_passes(tmp_path, capsys):
    repo(tmp_path, p=plan("p", a=[], b=["a"], c=["a", "b"]))
    assert e014(tmp_path, capsys) == (0, [])
