"""`ubiq coverage`: typed-metadata coverage of explicitly selected files.

The ordinary-software fixture lives in tests/fixtures/coverage/ordinary/. See
"Coverage" in docs/spec.md.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from ubiq.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "coverage"


def run(capsys, root: Path, *extra: str) -> tuple[int, dict]:
    code = main(["coverage", "--root", str(root), "--json", *extra])
    return code, json.loads(capsys.readouterr().out)


def ordinary(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "ordinary", root)
    return root


def configure(root: Path, coverage: str) -> None:
    """Replace the fixture's coverage section."""
    text = (root / "ubiq.yaml").read_text()
    (root / "ubiq.yaml").write_text(text[:text.index("coverage:")] + coverage)


def by_file(report: dict) -> dict[str, dict]:
    return {f["file"]: f for f in report["files"]}


def test_ordinary_fixture_counts_and_provenance(tmp_path, capsys):
    code, report = run(capsys, ordinary(tmp_path))
    assert code == 0
    assert report == json.loads((FIXTURES / "ordinary-report.json").read_text())


def test_registration_is_not_typed_coverage(tmp_path, capsys):
    _, report = run(capsys, ordinary(tmp_path))
    # glossary/payment.md is a registered vocabulary record with no schema or source record.
    assert by_file(report)["glossary/payment.md"]["classification"] == "untyped"


def test_unconfigured_is_unavailable_with_guidance(tmp_path, capsys):
    (tmp_path / "ubiq.yaml").write_text("docs: []\n")
    code, report = run(capsys, tmp_path)
    assert code == 2
    assert report["status"] == "unavailable" and "coverage:" in report["guidance"]
    assert main(["check", "--root", str(tmp_path)]) == 0  # other commands are unchanged


@pytest.mark.parametrize("section, message", [
    ("coverage: []\n", "coverage: expected a mapping"),
    ("coverage: {}\n", "coverage.files"),
    ("coverage: {files: []}\n", "at least one pattern"),
    ("coverage: {files: ['/abs/**']}\n", "repository-relative"),
    ("coverage: {files: ['../up/**']}\n", "repository-relative"),
    ("coverage: {files: ['src/**'], exclude: [{glob: 'src/vendor/**'}]}\n",
     "coverage.exclude[0].reason"),
    ("coverage: {files: ['src/**'], exclude: [{glob: 'a', reason: ' '}]}\n", "nonempty"),
    ("coverage: {files: ['src/**'], exclude: ['src/vendor/**']}\n", "glob and reason"),
    ("coverage: {files: ['src/**'], exclude: [{glob: a, reason: x}, {glob: a, reason: y}]}\n",
     "once"),
    ("coverage: {files: ['src/**'], min_typed_percent: 101}\n", "0 through 100"),
    ("coverage: {files: ['src/**'], min_typed_percent: true}\n", "0 through 100"),
    ("coverage: {files: ['src/**'], min_typed_percent: .nan}\n", "0 through 100"),
    ("coverage: {files: ['src/**'], no_regression: 'yes'}\n", "true or false"),
    ("coverage: {files: ['src/**'], floor: 3}\n", "unknown setting floor"),
])
def test_malformed_configuration_is_unavailable(tmp_path, capsys, section, message):
    root = ordinary(tmp_path)
    configure(root, section)
    code, report = run(capsys, root)
    assert code == 2 and report["status"] == "unavailable"
    assert message in report["reason"]


def test_overlapping_globs_count_each_file_once(tmp_path, capsys):
    root = ordinary(tmp_path)
    configure(root, "coverage:\n  files: ['src/**/*.py', 'src/*.py', 'src/app.py']\n")
    _, report = run(capsys, root)
    assert report["counts"]["selected"] == 3
    assert [f["file"] for f in report["files"]] == ["src/app.py", "src/util.py", "src/vendor/retry.py"]


def test_unmatched_patterns_are_reported(tmp_path, capsys):
    root = ordinary(tmp_path)
    configure(root, "coverage:\n  files: ['src/*.py', 'lib/**']\n"
                    "  exclude: [{glob: 'gen/**', reason: generated}]\n")
    code, report = run(capsys, root)
    assert code == 0
    assert [(d["code"], d["message"]) for d in report["diagnostics"]] == [
        ("W006", "coverage exclusion matched no selected file: gen/**"),
        ("W006", "coverage pattern matched no files: lib/**"),
    ]


def test_duplicate_source_mappings_count_once(tmp_path, capsys):
    root = ordinary(tmp_path)
    model = (root / "model.yaml").read_text()
    record = model[model.index("  - id: app"):model.index("relationships:")]
    (root / "model.yaml").write_text(model.replace(
        "relationships:", record.replace("id: app", "id: app-again") + "relationships:"))
    _, report = run(capsys, root)
    app = by_file(report)["src/app.py"]
    assert report["counts"]["typed"] == 2
    assert [v["id"] for v in app["via"]] == ["app", "app-again"]
    assert any(d["code"] == "E010" and "duplicate source" in d["message"]
               for d in report["diagnostics"])


def test_symlink_leaving_the_repository_is_not_counted(tmp_path, capsys):
    root = ordinary(tmp_path)
    (tmp_path / "elsewhere.py").write_text("x = 1\n")
    os.symlink(tmp_path / "elsewhere.py", root / "src" / "linked.py")
    _, report = run(capsys, root)
    assert report["scope"]["outside"] == [
        {"file": "src/linked.py", "target": str((tmp_path / "elsewhere.py").resolve())}]
    assert "src/linked.py" not in by_file(report)
    assert report["counts"]["selected"] == 5


def test_typed_but_invalid_is_nonconforming(tmp_path, capsys):
    root = ordinary(tmp_path)
    (root / "services" / "api.yaml").write_text("name: payments-api\nowner: payments\nport: http\n")
    code, report = run(capsys, root)
    api = by_file(report)["services/api.yaml"]
    assert code == 0
    assert (api["classification"], api["conformance"]) == ("typed", "invalid")
    assert report["counts"]["nonconforming"] == 1
    assert any(d["code"] == "E009" for d in report["diagnostics"])


def test_unavailable_schema_data_is_incomplete(tmp_path, capsys):
    root = ordinary(tmp_path)
    (root / "schemas" / "model.json").write_text("{not json")
    code, report = run(capsys, root)
    assert code == 2 and report["status"] == "incomplete" and not report["complete"]
    assert report["incomplete"][0]["reason"].startswith("schemas[1] (schemas/model.json) cannot load")


def test_unreadable_source_collection_is_incomplete(tmp_path, capsys):
    root = ordinary(tmp_path)
    model = (root / "model.yaml").read_text()
    (root / "model.yaml").write_text(model[:model.index("modules:")] + "modules: oops\n"
                                     + model[model.index("relationships:"):])
    code, report = run(capsys, root)
    assert code == 2
    assert report["incomplete"] == [
        {"file": "model.yaml", "reason": "x-ubiq collection modules is not a list"}]


def test_zero_eligible_files_have_no_percentage(tmp_path, capsys):
    root = ordinary(tmp_path)
    configure(root, "coverage:\n  files: ['src/vendor/**']\n"
                    "  exclude: [{glob: 'src/vendor/**', reason: upstream}]\n")
    code, report = run(capsys, root)
    assert code == 0
    assert report["counts"]["eligible"] == 0 and report["typed_percent"] is None


def test_git_ignored_files_are_not_selected(tmp_path, capsys):
    root = ordinary(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / ".gitignore").write_text("src/util.py\n")
    _, report = run(capsys, root)
    assert "src/util.py" not in by_file(report)


def test_output_is_deterministic(tmp_path, capsys):
    root = ordinary(tmp_path)
    first = run(capsys, root)
    assert run(capsys, root) == first
    assert main(["coverage", "--root", str(root)]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == (
        "coverage: 2 of 4 eligible files typed (50.00%); 5 selected, 1 excluded, 0 nonconforming")
