"""`ubiq coverage`: typed-metadata coverage of explicitly selected files.

The ordinary-software fixture lives in tests/fixtures/coverage/ordinary/. See
"Coverage" in docs/spec.md.
"""

import hashlib
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
    cut = text.index("coverage:") if "coverage:" in text else len(text)
    (root / "ubiq.yaml").write_text(text[:cut] + coverage)


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
        "coverage: 2 of 4 eligible files typed (50.00%); 5 selected, 1 excluded, 0 nonconforming,"
        " evidence not assessed for 1")


def model_edit(root: Path, old: str, new: str) -> None:
    text = (root / "model.yaml").read_text()
    assert old in text
    (root / "model.yaml").write_text(text.replace(old, new, 1))


def assessed(capsys, root: Path) -> tuple[int, dict, dict]:
    code, report = run(capsys, root)
    return code, report, by_file(report)["src/app.py"]


def test_assessments_distinguish_invalid_data_from_absent_metadata(tmp_path, capsys):
    root = ordinary(tmp_path)
    model_edit(root, "kind: module", "kind: 7")
    code, report, app = assessed(capsys, root)
    assert code == 0
    assert (app["classification"], app["conformance"]) == ("typed", "invalid")
    # Integrity cannot run on nonconforming data: not assessed, never "ok".
    assert (app["evidence"], app["relationships"]) == ("not_assessed", "not_assessed")
    assert by_file(report)["src/util.py"]["classification"] == "untyped"


def test_unresolved_relationship_is_reported(tmp_path, capsys):
    root = ordinary(tmp_path)
    digest = hashlib.sha256((root / "src" / "app.py").read_bytes()).hexdigest()
    model_edit(root, "relationships: []", "relationships:\n  - id: pays\n    from: app\n    to: ghost\n"
               "    kind: calls\n    evidence:\n      path: src/app.py\n"
               f"      sha256: {digest}\n      anchor: def main\n")
    _, report, app = assessed(capsys, root)
    assert (app["conformance"], app["relationships"], app["evidence"]) == ("valid", "unresolved", "ok")
    assert [(f["category"], f["kind"], f["records"]) for f in app["findings"]] == [
        ("relationship", "unresolved", ["app"])]
    assert report["assessments"]["relationships"]["unresolved"] == 1


@pytest.mark.parametrize("change, status", [
    (lambda root: (root / "src" / "app.py").write_text('"""Payment service entry point."""\n'), "stale"),
    (lambda root: model_edit(root, "      - path: src/app.py\n        sha256",
                             "      - path: services/api.yaml\n        sha256"), "missing"),
    (lambda root: (root / "src" / "app.py").write_bytes(b"\xff def main"), "invalid"),
])
def test_evidence_failures_are_categorized(tmp_path, capsys, change, status):
    root = ordinary(tmp_path)
    model = (root / "model.yaml").read_text()
    # Keep the domain's snapshot on its own file so only the module's evidence fails.
    model_edit(root, model[model.index("domains:"):model.index("modules:")],
               "domains:\n  - id: payments\n    evidence:\n      - path: services/api.yaml\n"
               "        sha256: " + hashlib.sha256(
                   (root / "services" / "api.yaml").read_bytes()).hexdigest()
               + "\n        anchor: payments\n")
    change(root)
    _, report, app = assessed(capsys, root)
    assert app["conformance"] == "valid" and app["evidence"] == status
    assert all(f["category"] == "evidence" for f in app["findings"])
    assert report["assessments"]["evidence"][status] == 1


def test_plain_schema_binding_does_not_assess_evidence(tmp_path, capsys):
    _, report = run(capsys, ordinary(tmp_path))
    api = by_file(report)["services/api.yaml"]
    assert (api["evidence"], api["relationships"]) == ("not_assessed", "not_assessed")
    assert report["assessments"]["evidence"]["not_assessed"] == 1


# Baselines: each side uses its own configuration; the baseline is the merge base.

def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
         "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
        cwd=root, check=True, capture_output=True, text=True).stdout


def committed(tmp_path: Path) -> Path:
    """The ordinary fixture committed on `main`, checked out on a feature branch."""
    root = ordinary(tmp_path)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    git(root, "checkout", "-qb", "feature")
    return root


def since(capsys, root: Path, *extra: str) -> tuple[int, dict]:
    code, report = run(capsys, root, "--since", "main", *extra)
    if "baseline" in report:
        assert report["baseline"]["commit"] == git(root, "rev-parse", "main").strip()
    return code, report


def test_baseline_rename_is_neither_added_nor_removed(tmp_path, capsys):
    root = committed(tmp_path)
    git(root, "mv", "src/util.py", "src/money.py")
    code, report = since(capsys, root)
    d = report["delta"]
    assert code == 0
    assert (d["added"], d["removed"], d["eligible"]["change"]) == ([], [], 0)


def test_baseline_deletion_shrinks_the_denominator_visibly(tmp_path, capsys):
    root = committed(tmp_path)
    (root / "src" / "util.py").unlink()
    _, report = since(capsys, root)
    d = report["delta"]
    assert d["removed"] == [{"file": "src/util.py", "classification": "untyped"}]
    assert d["eligible"] == {"baseline": 4, "head": 3, "change": -1}
    assert (d["typed"]["change"], d["newly_typed"]) == (0, [])  # not newly documented
    assert d["typed_percent"] == {"baseline": 50.0, "head": 66.66}
    main(["coverage", "--root", str(root), "--since", "main"])
    text = capsys.readouterr().out
    assert "eligible files 4 -> 3 (-1): 0 added, 1 removed" in text
    assert "the denominator shrank by 1" in text


def test_baseline_exclusion_changes(tmp_path, capsys):
    root = committed(tmp_path)
    configure(root, "coverage:\n  files: ['src/**/*.py', 'services/*.yaml', 'glossary/*.md']\n"
                    "  exclude:\n"
                    "    - {glob: 'src/vendor/**', reason: 'Upstream copy.'}\n"
                    "    - {glob: 'src/util.py', reason: 'Generated.'}\n")
    _, report = since(capsys, root)
    d = report["delta"]
    assert d["newly_excluded"] == ["src/util.py"] and d["removed"] == [
        {"file": "src/util.py", "classification": "excluded"}]
    assert d["exclusions"] == {
        "added": [{"glob": "src/util.py", "reason": "Generated."}], "removed": [],
        "changed": [{"glob": "src/vendor/**",
                     "from": "Vendored upstream copy; its metadata belongs upstream.",
                     "to": "Upstream copy."}]}


def test_baseline_untracked_and_untyped_changes(tmp_path, capsys):
    root = committed(tmp_path)
    (root / "src" / "new.py").write_text("x = 1\n")  # untracked
    text = (root / "ubiq.yaml").read_text()
    (root / "ubiq.yaml").write_text(text.replace('    files: ["services/*.yaml"]\n', '    files: ["nothing/*.yaml"]\n'))
    _, report = since(capsys, root)
    d = report["delta"]
    assert d["added"] == [{"file": "src/new.py", "classification": "untyped"}]
    assert d["newly_untyped"] == ["services/api.yaml"]
    assert d["findings"]["counts"]["new"] == 1  # the binding now matches nothing (E009)


def test_baseline_finding_changes_reuse_compare_identity(tmp_path, capsys):
    root = committed(tmp_path)
    with (root / "src" / "app.py").open("a") as f:
        f.write("\n# edited\n")
    _, report = since(capsys, root)
    findings = report["delta"]["findings"]
    assert findings["counts"] == {"new": 2, "resolved": 0, "unchanged": 0}
    assert {f["message"] for f in findings["new"]} == {"evidence drift: src/app.py"}


def test_unconfigured_baseline_has_no_delta(tmp_path, capsys):
    root = ordinary(tmp_path)
    configured = (root / "ubiq.yaml").read_text()
    configure(root, "")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    (root / "ubiq.yaml").write_text(configured)
    code, report = since(capsys, root)
    assert code == 0
    assert report["baseline"]["status"] == "unconfigured" and report["delta"] is None


@pytest.mark.parametrize("rev", ["nope", "--output=x"])
def test_invalid_baseline_is_unavailable(tmp_path, capsys, rev):
    root = committed(tmp_path)
    code, report = run(capsys, root, f"--since={rev}")
    assert code == 2 and report["status"] == "unavailable"
    assert report["reason"].startswith("baseline unavailable")


def test_baseline_with_invalid_configuration_is_unavailable(tmp_path, capsys):
    root = ordinary(tmp_path)
    good = (root / "ubiq.yaml").read_text()
    configure(root, "coverage: {files: []}\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    (root / "ubiq.yaml").write_text(good)
    code, report = since(capsys, root)
    assert code == 2 and "baseline configuration cannot load" in report["reason"]


def test_incomplete_baseline_is_incomplete(tmp_path, capsys):
    root = ordinary(tmp_path)
    good = (root / "schemas" / "model.json").read_text()
    (root / "schemas" / "model.json").write_text("{not json")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    (root / "schemas" / "model.json").write_text(good)
    code, report = since(capsys, root)
    assert code == 2 and report["status"] == "incomplete"
    assert report["incomplete"] == [] and report["baseline"]["incomplete"]


def test_markdown_summary(tmp_path, capsys):
    root = committed(tmp_path)
    (root / "src" / "util.py").unlink()
    assert main(["coverage", "--root", str(root), "--since", "main", "--markdown"]) == 0
    out = capsys.readouterr().out.replace(git(root, "rev-parse", "main").strip()[:12], "<commit>")
    assert out == (FIXTURES / "deletion.md").read_text()


# Policies: floors and no regression. Exit 0 pass, 1 policy failure, 2 unavailable.

SCOPE = "coverage:\n  files: ['src/**/*.py', 'services/*.yaml', 'glossary/*.md']\n" \
        "  exclude: [{glob: 'src/vendor/**', reason: upstream}]\n"


def policy(report: dict, name: str) -> dict:
    return next(p for p in report["policies"] if p["policy"] == name)


@pytest.mark.parametrize("floor, code", [
    (50, 0), (50.0, 0), (49.99, 0), (50.01, 1), (0, 0), (100, 1),
])
def test_floor_boundaries(tmp_path, capsys, floor, code):
    root = ordinary(tmp_path)  # 2 of 4 typed
    configure(root, SCOPE + f"  min_typed_percent: {floor}\n")
    got, report = run(capsys, root)
    assert got == code
    assert policy(report, "min_typed_percent")["result"] == ("pass" if code == 0 else "fail")


def test_floor_compares_unrounded_ratios(tmp_path, capsys):
    root = ordinary(tmp_path)
    configure(root, "coverage:\n  files: ['src/*.py', 'services/*.yaml']\n"
                    "  min_typed_percent: 66.67\n")  # 2 of 3 is 66.666...
    code, report = run(capsys, root)
    assert report["typed_percent"] == 66.66 and code == 1
    configure(root, "coverage:\n  files: ['src/*.py', 'services/*.yaml']\n"
                    "  min_typed_percent: 66.66\n")
    assert run(capsys, root)[0] == 0
    # 66.666 is below 2/3 but above the displayed 66.66: only the exact ratio passes it.
    configure(root, "coverage:\n  files: ['src/*.py', 'services/*.yaml']\n"
                    "  min_typed_percent: 66.666\n")
    assert run(capsys, root)[0] == 0


def test_zero_denominator_cannot_pass_a_floor(tmp_path, capsys):
    root = ordinary(tmp_path)
    configure(root, "coverage:\n  files: ['src/vendor/**']\n"
                    "  exclude: [{glob: 'src/vendor/**', reason: upstream}]\n  min_typed_percent: 0\n")
    code, report = run(capsys, root)
    assert code == 1 and policy(report, "min_typed_percent")["result"] == "fail"


def test_incomplete_measurement_never_passes(tmp_path, capsys):
    root = ordinary(tmp_path)
    configure(root, SCOPE + "  min_typed_percent: 0\n")
    (root / "schemas" / "model.json").write_text("{not json")
    code, report = run(capsys, root)
    assert code == 2 and policy(report, "min_typed_percent")["result"] == "unavailable"


def test_no_regression_requires_a_baseline(tmp_path, capsys):
    root = ordinary(tmp_path)
    configure(root, SCOPE + "  no_regression: true\n")
    code, report = run(capsys, root)
    assert code == 2
    assert "--since" in policy(report, "no_regression")["reason"]
    main(["coverage", "--root", str(root)])
    assert "ubiq coverage --since REV" in capsys.readouterr().out


def regression_repo(tmp_path: Path) -> Path:
    root = committed(tmp_path)
    configure(root, SCOPE + "  no_regression: true\n")
    git(root, "commit", "-qam", "policy")
    git(root, "branch", "-f", "main")
    return root


def test_no_regression_passes_when_ratio_holds(tmp_path, capsys):
    root = regression_repo(tmp_path)
    code, report = since(capsys, root)
    assert code == 0 and policy(report, "no_regression")["reason"] == "2/4 -> 2/4 typed"


def test_no_regression_fails_when_ratio_falls(tmp_path, capsys):
    root = regression_repo(tmp_path)
    (root / "src" / "new.py").write_text("z = 3\n")
    code, report = since(capsys, root)
    assert code == 1
    assert policy(report, "no_regression") == {
        "policy": "no_regression", "result": "fail", "reason": "typed ratio fell from 2/4 to 2/5"}


def test_no_regression_uses_head_policy_not_baseline_policy(tmp_path, capsys):
    root = committed(tmp_path)  # the baseline has no policy
    configure(root, SCOPE + "  no_regression: true\n")
    (root / "src" / "new.py").write_text("z = 3\n")
    assert since(capsys, root)[0] == 1


def test_no_regression_against_empty_baseline_fails(tmp_path, capsys):
    root = ordinary(tmp_path)
    configure(root, "coverage:\n  files: ['nothing/**']\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    configure(root, SCOPE + "  no_regression: true\n")
    code, report = since(capsys, root)
    assert code == 1 and "baseline" in policy(report, "no_regression")["reason"]


def test_no_regression_on_first_adoption_is_skipped_visibly(tmp_path, capsys):
    root = ordinary(tmp_path)
    configure(root, "")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    configure(root, SCOPE + "  no_regression: true\n")
    code, report = since(capsys, root)
    assert code == 0 and policy(report, "no_regression")["result"] == "skipped"


def test_no_regression_with_incomplete_baseline_is_unavailable(tmp_path, capsys):
    root = ordinary(tmp_path)
    good = (root / "schemas" / "model.json").read_text()
    configure(root, SCOPE + "  no_regression: true\n")
    (root / "schemas" / "model.json").write_text("{not json")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    (root / "schemas" / "model.json").write_text(good)
    code, report = since(capsys, root)
    assert code == 2 and policy(report, "no_regression")["result"] == "unavailable"


def test_missing_baseline_rev_exits_2(tmp_path, capsys):
    root = regression_repo(tmp_path)
    assert run(capsys, root, "--since", "missing")[0] == 2


def test_suggestions_come_from_discovery_outside_scope(tmp_path, capsys):
    root = ordinary(tmp_path)
    (root / "skills" / "deploy").mkdir(parents=True)
    (root / "skills" / "deploy" / "SKILL.md").write_text("---\nname: deploy\n---\n")
    (root / "skills" / "upstream").mkdir()
    (root / "skills" / "upstream" / "SKILL.md").write_text("---\nname: upstream\n---\n")
    configure(root, "coverage:\n  files: ['src/**/*.py', 'services/*.yaml', 'glossary/*.md']\n"
                    "  exclude: [{glob: 'skills/upstream/**', reason: 'Pinned copy.'}]\n")
    _, report = run(capsys, root)
    # Never in the denominator; excluded paths are not suggested.
    assert report["suggestions"] == ["skills/deploy/SKILL.md"]
    assert report["counts"]["selected"] == 5


def test_excluded_links_do_not_admit_their_targets(tmp_path, capsys):
    root = ordinary(tmp_path)
    (root / "lib").mkdir()
    (root / "lib" / "e.py").write_text("e = 1\n")
    os.symlink("../../lib/e.py", root / "src" / "vendor" / "ext.py")
    os.symlink("app.py", root / "src" / "alias.py")
    _, report = run(capsys, root)
    assert by_file(report)["lib/e.py"]["classification"] == "excluded"
    assert report["counts"]["eligible"] == 4  # the in-repo alias of app.py counts once


def test_submodule_files_can_be_excluded(tmp_path, capsys):
    sub = tmp_path / "sub-src"
    sub.mkdir()
    (sub / "z.py").write_text("z = 1\n")
    git(sub, "init", "-q")
    git(sub, "add", "-A")
    git(sub, "commit", "-qm", "sub")
    root = committed(tmp_path)
    git(root, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "src/sub")
    assert run(capsys, root)[0] == 2  # git cannot probe files inside a submodule
    configure(root, "coverage:\n  files: ['src/**/*.py', 'services/*.yaml', 'glossary/*.md']\n"
                    "  exclude:\n    - {glob: 'src/vendor/**', reason: upstream}\n"
                    "    - {glob: 'src/sub/**', reason: 'Submodule; typed in its own repository.'}\n")
    code, report = run(capsys, root)
    assert code == 0 and by_file(report)["src/sub/z.py"]["classification"] == "excluded"


def test_incomplete_head_makes_no_regression_unavailable_even_on_first_adoption(tmp_path, capsys):
    root = ordinary(tmp_path)
    configure(root, "")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    configure(root, SCOPE + "  no_regression: true\n")
    (root / "schemas" / "model.json").write_text("{not json")
    code, report = since(capsys, root)
    assert code == 2 and policy(report, "no_regression")["result"] == "unavailable"
