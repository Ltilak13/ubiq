"""Support matrix as records: runtime helper, marker, drift checks, and the table."""

import datetime
import sys
from pathlib import Path

import pytest

from ubiq import cli
from ubiq.config import InvalidConfig, load_config
from ubiq.support import RuntimeUnmet, declared, require, satisfies, skip_reason, unmet
from ubiq.support_check import BEGIN, END, check_support, extras, requires_python

REPO = Path(__file__).resolve().parents[1]
TODAY = datetime.date(2026, 11, 27)


# --- runtime helper ---------------------------------------------------------

@pytest.mark.parametrize("version, spec, ok", [
    ((3, 10, 14), ">=3.11", False),
    ((3, 11, 0), ">=3.11", True),
    ((3, 12, 1), ">=3.11,<3.13", True),
    ((3, 13, 0), ">=3.11,<3.13", False),
    ((3, 11, 4), "==3.11", True),
    ((3, 12, 0), "==3.11", False),
    ((3, 11, 4), "!=3.11", False),
    ((3, 11, 4), ">3.11", True),
    ((3, 11, 0), ">3.11", False),
    ((3, 11, 4), "<=3.11", False),
])
def test_satisfies_specifier_clauses(version, spec, ok):
    assert satisfies(version, spec) is ok


@pytest.mark.parametrize("spec", ["3.11", "~=3.11", ">=three", "", ">=3.11,"])
def test_unsupported_specifier_is_rejected_with_an_example(spec):
    with pytest.raises(ValueError, match=r"use clauses like '>=3.11'"):
        satisfies((3, 12, 0), spec)


def test_unmet_python_names_the_need_the_extra_and_the_running_version():
    message = unmet(python=">=3.11", extra="jsonpath", feature="JSONPath selection",
                    version=(3, 10, 14))
    assert message is not None
    assert "JSONPath selection needs Python >=3.11 (install ubiq[jsonpath])" in message
    assert "this is Python 3.10.14" in message


def test_met_requirements_return_nothing():
    assert unmet(python=">=3.11", version=(3, 12, 0)) is None
    assert unmet() is None
    assert unmet(module="json") is None


def test_missing_module_names_the_extra_to_install():
    message = unmet(extra="jsonpath", module="ubiq_no_such_module_xyz", feature="JSONPath")
    assert message is not None
    assert "pip install 'ubiq[jsonpath]'" in message
    assert "'ubiq_no_such_module_xyz'" in message
    assert "pip install ubiq_no_such_module_xyz" in unmet(module="ubiq_no_such_module_xyz")


def test_require_raises_an_import_error_with_the_message():
    with pytest.raises(ImportError, match="needs Python >=99.0") as raised:
        require(python=">=99.0", extra="jsonpath")
    assert isinstance(raised.value, RuntimeUnmet)
    require(python=">=3.10")


def test_declared_reads_a_feature_records_runtime_mapping():
    assert declared({"python": ">=3.11"}, "jsonpath", "JSONPath") is None or sys.version_info < (3, 11)
    assert declared(None) is None
    assert declared({"python": ">=99"}, "jsonpath") is not None


def test_skip_reason_takes_keywords_only():
    assert skip_reason(python=">=99") is not None
    assert skip_reason(python=">=3.10") is None
    with pytest.raises(TypeError, match="keyword"):
        skip_reason(">=3.11")


@pytest.mark.runtime(python=">=3.11")
def test_marker_runs_where_the_runtime_is_met():
    import tomllib  # exists from 3.11, so a skip on 3.10 proves the marker works
    assert tomllib.loads('a = 1') == {"a": 1}


@pytest.mark.runtime(python=">=99.0", extra="never")
def test_marker_skips_where_it_is_not():
    raise AssertionError("must be skipped")


# --- drift checks -----------------------------------------------------------

PYPROJECT = '''[project]
name = "demo"
requires-python = ">=3.10"

[project.optional-dependencies]
dev = [
    "pytest",
]
jsonpath = ["jsonpath-ng"]
'''

WORKFLOW = '''name: ci
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest]
        python-version: ["3.10", "3.11", "3.12"]
        include:
          - os: macos-latest
            python-version: "3.12"
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
  package:
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
'''

STATUSES = {"3.9": "unsupported", "3.10": "deprecated", "3.11": "supported",
            "3.12": "supported", "3.13": "unsupported"}


def record(root, version, status, eol="2030-10-31", name=None):
    path = root / ".ubiq/support" / f"python-{version}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'---\nname: {name or "python-" + version}\nruntime: python\n'
                    f'version: "{version}"\nstatus: {status}\neol: "{eol}"\n'
                    f'reason: Because | reasons.\n---\nBody.\n')
    return path


def repo(tmp_path, statuses=STATUSES, *, pyproject=PYPROJECT, workflow=WORKFLOW,
         extra_config="", table=True):
    for version, status in statuses.items():
        record(tmp_path, version, status)
    (tmp_path / "pyproject.toml").write_text(pyproject)
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/ci.yml").write_text(workflow)
    (tmp_path / "guide.md").write_text(f"# Guide\n\n{BEGIN}\n{END}\n")
    (tmp_path / "ubiq.yaml").write_text(
        "glossary: []\ndocs: []\nsupport:\n  records: '.ubiq/support/*.md'\n"
        f"{'  table: guide.md' if table else ''}\n{extra_config}")
    if table:
        assert cli.main(["support", "--root", str(tmp_path), "--write"]) == 0
    return tmp_path


def drift(root):
    return [d for d in check_support(load_config(root), TODAY)]


def messages(root):
    return [f"{d.code} {d.message}" for d in drift(root)]


def test_consistent_records_and_views_report_nothing(tmp_path):
    assert drift(repo(tmp_path)) == []


def test_this_repository_has_no_support_drift():
    diags = check_support(load_config(REPO), TODAY)
    assert diags == []
    statuses = {p.stem: p.read_text() for p in (REPO / ".ubiq/support").glob("*.md")}
    assert sorted(statuses) == [f"python-3.{n}" for n in range(10, 15)]
    assert "status: deprecated" in statuses["python-3.10"]
    assert 'eol: "2026-10-31"' in statuses["python-3.10"]


def test_requires_python_must_equal_the_lowest_supported_version(tmp_path):
    root = repo(tmp_path)
    (root / "pyproject.toml").write_text(PYPROJECT.replace(">=3.10", ">=3.11"))
    assert any('does not start at the lowest supported version' in m and '">=3.10"' in m
               for m in messages(root))
    (root / "pyproject.toml").write_text(PYPROJECT.replace(">=3.10", ">=3.9"))
    assert any("does not start at" in m for m in messages(root))


def test_requires_python_upper_bound_excluding_a_supported_version(tmp_path):
    root = repo(tmp_path)
    (root / "pyproject.toml").write_text(PYPROJECT.replace(">=3.10", ">=3.10,<3.12"))
    assert any("excludes supported Python 3.12" in m for m in messages(root))


def test_missing_or_malformed_requires_python(tmp_path):
    root = repo(tmp_path)
    (root / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    assert any("no [project] requires-python" in m for m in messages(root))
    (root / "pyproject.toml").write_text('[project]\nrequires-python = "~=3.10"\n')
    assert any("requires-python: unsupported Python requirement" in m for m in messages(root))


def test_requires_python_outside_the_project_table_is_ignored():
    assert requires_python('[tool.x]\nrequires-python = ">=3.1"\n[project]\n'
                           'requires-python = ">=3.10"  # floor\n') == ">=3.10"
    assert extras(PYPROJECT) == {"dev", "jsonpath"}


def test_every_live_version_must_be_in_the_matrix(tmp_path):
    root = repo(tmp_path)
    (root / ".github/workflows/ci.yml").write_text(WORKFLOW.replace('"3.10", ', ""))
    assert any("deprecated Python 3.10 is missing from the test matrix" in m
               for m in messages(root))


def test_unsupported_and_unknown_versions_must_not_be_in_the_matrix(tmp_path):
    root = repo(tmp_path)
    (root / ".github/workflows/ci.yml").write_text(
        WORKFLOW.replace('"3.12"]', '"3.12", "3.13", "3.14"]'))
    found = messages(root)
    assert any("unsupported Python 3.13 is in the test matrix" in m for m in found)
    assert any("Python 3.14 in the test matrix has no support record" in m for m in found)


def test_an_unquoted_matrix_version_gets_a_quoting_hint(tmp_path):
    root = repo(tmp_path)
    (root / ".github/workflows/ci.yml").write_text(WORKFLOW.replace('"3.10", ', "3.10, "))
    assert any("Python 3.1 in the test matrix has no support record (quote" in m
               for m in messages(root))


def test_an_include_entry_counts_toward_the_matrix(tmp_path):
    root = repo(tmp_path)
    (root / ".github/workflows/ci.yml").write_text(
        WORKFLOW.replace('"3.10", "3.11", "3.12"]', '"3.10", "3.12"]')
        .replace('python-version: "3.12"\n    steps', 'python-version: "3.11"\n    steps'))
    assert drift(root) == []


def test_other_jobs_may_not_pin_an_unsupported_version(tmp_path):
    root = repo(tmp_path)
    (root / ".github/workflows/ci.yml").write_text(
        WORKFLOW.replace('python-version: "3.10"\n', 'python-version: "3.9"\n'))
    assert any("job 'package' pins Python 3.9, which is unsupported" in m
               for m in messages(root))


def test_workflow_without_the_job_or_matrix(tmp_path):
    root = repo(tmp_path)
    (root / ".github/workflows/ci.yml").write_text("jobs:\n  build:\n    steps: []\n")
    assert any("job 'test' not found" in m for m in messages(root))
    (root / ".github/workflows/ci.yml").write_text("jobs:\n  test:\n    steps: []\n")
    assert any("has no strategy.matrix" in m for m in messages(root))


def test_an_unsupported_gap_between_supported_versions(tmp_path):
    root = repo(tmp_path, {**STATUSES, "3.11": "unsupported"})
    assert any("Python 3.11 is unsupported but sits between supported versions" in m
               for m in messages(root))


def test_record_name_and_duplicates(tmp_path):
    root = repo(tmp_path)
    record(root, "3.12", "supported", name="python-3.11")
    other = root / ".ubiq/support/python-3.12-copy.md"
    other.write_text((root / ".ubiq/support/python-3.12.md").read_text())
    found = messages(root)
    assert any("name 'python-3.11' should be 'python-3.12'" in m for m in found)
    assert any("python 3.12 has two support records" in m for m in found)


def test_no_matching_records_is_drift_not_a_pass(tmp_path):
    root = repo(tmp_path, {}, table=False)
    assert any("no support records match" in m for m in messages(root))


def test_expired_supported_record_warns(tmp_path):
    root = repo(tmp_path)
    record(root, "3.11", "supported", eol="2026-10-31")
    assert cli.main(["support", "--root", str(root), "--write"]) == 0
    found = drift(root)
    assert [(d.code, d.is_error) for d in found] == [("W010", False)]


# --- table ------------------------------------------------------------------

def test_table_is_generated_newest_first_and_escapes_pipes(tmp_path, capsys):
    root = repo(tmp_path)
    capsys.readouterr()
    assert cli.main(["support", "--root", str(root)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == BEGIN and out[-1] == END
    assert [row.split(" | ")[1] for row in out[3:-1]] == ["3.13", "3.12", "3.11", "3.10", "3.9"]
    assert "Because \\| reasons." in out[3]


def test_a_stale_table_is_drift_until_rewritten(tmp_path, capsys):
    root = repo(tmp_path)
    record(root, "3.11", "deprecated")
    assert any("support table is out of date" in m for m in messages(root))
    assert cli.main(["support", "--root", str(root), "--write"]) == 0
    assert "updated" in capsys.readouterr().out
    assert drift(root) == []
    assert cli.main(["support", "--root", str(root), "--write"]) == 0
    assert "unchanged" in capsys.readouterr().out


def test_missing_table_block_is_drift_and_write_fails(tmp_path, capsys):
    root = repo(tmp_path)
    (root / "guide.md").write_text("# Guide\n")
    assert any("has no support table block" in m for m in messages(root))
    assert cli.main(["support", "--root", str(root), "--write"]) == 1
    assert "error:" in capsys.readouterr().err


def test_support_command_without_configuration(tmp_path, capsys):
    (tmp_path / "ubiq.yaml").write_text("docs: []\n")
    assert cli.main(["support", "--root", str(tmp_path)]) == 2
    assert "no `support:` section" in capsys.readouterr().err


def test_ubiq_check_reports_drift_as_e013(tmp_path, capsys):
    root = repo(tmp_path)
    (root / "pyproject.toml").write_text(PYPROJECT.replace(">=3.10", ">=3.11"))
    assert cli.main(["check", "--root", str(root)]) == 1
    assert "E015" in capsys.readouterr().out


# --- feature declarations ---------------------------------------------------

def features(root, **frontmatter):
    path = root / "features" / "jsonpath.md"
    path.parent.mkdir(exist_ok=True)
    lines = "".join(f"{k}: {v}\n" for k, v in frontmatter.items())
    path.write_text(f"---\nname: jsonpath\n{lines}---\nBody.\n")


CONFIG = "  features: ['features/*.md']\n"


def test_feature_runtime_and_extra_must_be_declared(tmp_path):
    root = repo(tmp_path, extra_config=CONFIG)
    features(root, runtime="{python: '>=3.11'}", extra="jsonpath")
    assert drift(root) == []
    features(root, runtime="{python: '>=3.11'}", extra="jsonpth")
    assert any("extra 'jsonpth' is not declared in [project.optional-dependencies]" in m
               for m in messages(root))
    features(root, runtime="{python: 'newer'}")
    assert any("runtime: unsupported Python requirement 'newer'" in m for m in messages(root))
    features(root, runtime="3.11")
    assert any("runtime must be a mapping" in m for m in messages(root))


def test_feature_without_runtime_or_extra_is_fine(tmp_path):
    root = repo(tmp_path, extra_config=CONFIG)
    features(root)
    assert drift(root) == []


# --- configuration ----------------------------------------------------------

@pytest.mark.parametrize("block, message", [
    ("support: yes", "support: expected a mapping"),
    ("support: {}", "support.records"),
    ("support: {records: a, tabel: b}", "unknown setting tabel; did you mean table?"),
    ("support: {records: '../x'}", "support.records: expected a repository-relative"),
    ("support: {records: a, job: ''}", "support.job"),
])
def test_invalid_support_configuration(tmp_path, block, message):
    (tmp_path / "ubiq.yaml").write_text(block + "\n")
    with pytest.raises(InvalidConfig, match=message):
        load_config(tmp_path)
