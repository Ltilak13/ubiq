"""Step definitions for the goal scenarios in docs/goals/*.feature.

Each scenario builds a small repository in a temporary directory, runs the ubiq
CLI in it, and checks the JSON it prints. Each phrase is one literal pattern on
one function (decision 0002).
"""

import json
from pathlib import Path

import pytest

pytest.importorskip("pytest_bdd")  # the minimum-dependency and wheel jobs install pytest only

from pytest_bdd import given, parsers, scenarios, then, when

from ubiq.cli import main

GOALS = Path(__file__).resolve().parents[2] / "docs" / "goals"
scenarios(*sorted(str(p) for p in GOALS.glob("*.feature")))

CONFIG = """glossary:
  - {{glob: "skills/*/SKILL.md", term_field: name, ns: skill}}
{rule}
docs: ["skills/**/*.md"]
ref_fields: [uses]
edges:
  invoke: {{blocked_by: disable-model-invocation}}
  install: ["skills/*/SKILL.md"]
"""


@pytest.fixture
def repo(tmp_path):
    return {"root": tmp_path, "out": None, "status": None}


def write(repo, path, text):
    target = repo["root"] / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def record(name, body="", meta=""):
    return f"---\nname: {name}\n{meta}---\n\n{body or 'A record with no references.'}\n"


@given("a skill repository that registers parts with this glossary rule:")
def _(repo, docstring):
    rule = "\n".join("  " + line for line in docstring.splitlines())
    write(repo, "ubiq.yaml", CONFIG.format(rule=rule))


@given(parsers.parse('the part "{name}" in "{path}"'))
@given(parsers.parse('the skill "{name}" in "{path}"'))
def _(repo, name, path):
    write(repo, path, record(name))


@given(parsers.parse('the part "{name}" in "{path}" says:'))
@given(parsers.parse('the skill "{name}" in "{path}" says:'))
def _(repo, name, path, docstring):
    write(repo, path, record(name, docstring))


@given(parsers.parse('the skill "{name}" in "{path}" uses "{other}"'))
def _(repo, name, path, other):
    write(repo, path, record(name, meta=f"uses: [{other}]\n"))


@given(parsers.parse('the skill "{name}" in "{path}" is user-invoked only'))
def _(repo, name, path):
    write(repo, path, record(name, meta="disable-model-invocation: true\n"))


@given(parsers.parse('the skills "{a}" and "{b}" share 19 of 20 words'))
def _(repo, a, b):
    words = [f"word{i}" for i in range(20)]
    near = [*words[:10], "other", *words[11:]]
    write(repo, f"skills/{a}/SKILL.md", record(a, " ".join(words)))
    write(repo, f"skills/{b}/SKILL.md", record(b, " ".join(near)))


@when(parsers.parse('"{old}" moves to "{new}"'))
def _(repo, old, new):
    (repo["root"] / old).rename(repo["root"] / new)


@when(parsers.parse('I run "ubiq {command}"'))
def _(repo, command, capsys):
    repo["status"] = main([*command.split(), "--root", str(repo["root"]), "--json"])
    repo["out"] = json.loads(capsys.readouterr().out)


def _errors(repo):
    return [d for d in repo["out"]["diagnostics"] if d["severity"] == "error"]


@then("it passes")
def _(repo):
    assert repo["status"] == 0, _errors(repo)


@then(parsers.parse('it passes with the warning "{code}" in "{path}"'))
def _(repo, code, path):
    assert repo["status"] == 0, _errors(repo)
    assert path in [d["file"] for d in repo["out"]["diagnostics"] if d["code"] == code]


@then(parsers.parse('it fails with the error "{code}"'))
def _(repo, code):
    assert repo["status"] == 1
    assert {d["code"] for d in _errors(repo)} == {code}


@then("it fails with:")
def _(repo, datatable):
    assert repo["status"] == 1
    _, *rows = datatable
    want = sorted(tuple(row) for row in rows)
    assert sorted((d["code"], d["file"]) for d in _errors(repo)) == want


@then("the references come from:")
def _(repo, datatable):
    assert repo["status"] == 0
    _, *rows = datatable
    assert sorted(r["file"] for r in repo["out"]["references"]) == sorted(row[0] for row in rows)


@then("the edges are:")
def _(repo, datatable):
    assert repo["status"] == 0
    header, *rows = datatable
    found = [[str(edge[key]) for key in header] for edge in repo["out"]["edges"]]
    assert sorted(found) == sorted(rows)


@then("the edges go:")
def _(repo, datatable):
    assert repo["status"] == 0
    _, *rows = datatable
    assert [[e["source"], e["target"]] for e in repo["out"]["edges"]] == rows


@then(parsers.parse("overlap reports {count:d} cluster(s)"))
def _(repo, count):
    assert repo["out"]["count"] == count
