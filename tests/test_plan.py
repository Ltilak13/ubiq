"""Feature records, their adoption order (`ubiq plan`), and the checks that keep them honest."""

import json
import re
import shutil
from pathlib import Path

import pytest

from ubiq.cli import main
from ubiq.plan import (
    BUNDLED,
    Feature,
    PlanError,
    load_features,
    next_steps,
    order,
    used_features,
)

ROOT = Path(__file__).resolve().parents[1]


def feature(name, *requires, config=()):
    return Feature(name, f"{name} summary", tuple(requires), config=tuple(config))


def names(features):
    return [f.name for f in features]


def write_feature(directory, name, requires=(), config=(), codes=()):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.md").write_text(
        f"---\nname: {name}\nrequires: [{', '.join(requires)}]\ncodes: [{', '.join(codes)}]\n"
        f"config: [{', '.join(config)}]\ndocs: docs/spec.md\nsummary: {name} summary\n---\n\n"
        f"{name} body.\n")


def test_order_follows_requirements_with_alphabetical_ties():
    features = [feature("zeta"), feature("edges", "zeta", "alpha"), feature("alpha"),
                feature("beta", "alpha"), feature("aaa", "edges")]
    assert names(order(features)) == ["alpha", "beta", "zeta", "edges", "aaa"]
    assert names(order(reversed(features))) == names(order(features))


def test_missing_requirement_fails():
    with pytest.raises(PlanError, match="field-links requires glossary, which is not a feature"):
        order([feature("field-links", "glossary")])


def test_mutual_requirement_fails():
    with pytest.raises(PlanError, match="requires cycle: a -> b -> a"):
        order([feature("a", "b"), feature("b", "a"), feature("c")])
    with pytest.raises(PlanError, match="requires cycle: a -> b -> c -> a"):
        order([feature("a", "b"), feature("b", "c"), feature("c", "a")])


def test_duplicate_feature_fails():
    with pytest.raises(PlanError, match="defined twice"):
        order([feature("a"), feature("a")])


def test_next_steps_skip_used_and_unmet_features():
    ordered = order([feature("glossary"), feature("refs", "glossary"),
                     feature("edges", "refs"), feature("schemas", "glossary")])
    assert names(next_steps(ordered, {"glossary"})) == ["refs", "schemas"]
    assert names(next_steps(ordered, {"glossary", "refs"})) == ["edges", "schemas"]
    assert names(next_steps(ordered, {"glossary", "refs", "edges", "schemas"})) == []


def test_used_features_come_from_config_and_requirements(tmp_path):
    features = order([feature("glossary", config=["glossary"]), feature("refs", "glossary"),
                      feature("edges", "refs", config=["edges"]),
                      feature("external", "edges", config=["edges.external"])])
    (tmp_path / "ubiq.yaml").write_text("edges:\n  install: ['a']\n")
    assert used_features(features, tmp_path) == {"glossary", "refs", "edges"}
    (tmp_path / "ubiq.yaml").write_text("edges:\n  external: [{path: x}]\n")
    assert used_features(features, tmp_path) == {"glossary", "refs", "edges", "external"}
    assert used_features(features, tmp_path / "missing") == set()
    assert used_features(features, tmp_path / "missing", declared=["refs", "typo"]) \
        == {"glossary", "refs"}


def run(capsys, *argv):
    status = main(["plan", *argv])
    return status, capsys.readouterr().out


def test_plan_lists_every_feature_in_order(tmp_path, capsys):
    features = tmp_path / "features"
    write_feature(features, "schemas", ["glossary"])
    write_feature(features, "glossary")
    write_feature(features, "catalogs", ["glossary"])
    status, out = run(capsys, "--features", str(features))
    assert status == 0
    lines = out.splitlines()
    assert [line.split()[:2] for line in lines] == [
        ["1.", "glossary"], ["2.", "catalogs"], ["3.", "schemas"]]
    status, out = run(capsys, "--features", str(features), "--json")
    assert [f["name"] for f in json.loads(out)["features"]] == ["glossary", "catalogs", "schemas"]


def test_plan_next_for_a_repo_using_some_features(tmp_path, capsys):
    features = tmp_path / "features"
    write_feature(features, "glossary", config=["glossary"])
    write_feature(features, "refs", ["glossary"], config=["ref_fields"])
    write_feature(features, "edges", ["refs"], config=["edges"])
    write_feature(features, "schemas", ["glossary"], config=["schemas"])
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ubiq.yaml").write_text("glossary: ['g/*.md']\nref_fields: [uses]\n")
    status, out = run(capsys, "--features", str(features), "--root", str(repo), "--next", "--json")
    result = json.loads(out)
    assert status == 0
    assert [(f["position"], f["name"]) for f in result["features"]] == [(3, "edges"), (4, "schemas")]
    assert result["used"] == ["glossary", "refs"]
    status, out = run(capsys, "--features", str(features), "--root", str(repo), "--next",
                      "--used", "schemas", "--used", "edges")
    assert out == "every feature is in use\n"
    status, out = run(capsys, "--features", str(features), "--used", "typo", "--next")
    assert status == 1 and "typo" in out


def test_plan_reports_missing_requirement_and_cycle(tmp_path, capsys):
    features = tmp_path / "features"
    write_feature(features, "field-links", ["glossary"])
    status, out = run(capsys, "--features", str(features))
    assert status == 1 and "requires glossary, which is not a feature" in out
    write_feature(features, "glossary", ["field-links"])
    status, out = run(capsys, "--features", str(features))
    assert status == 1 and "requires cycle: field-links -> glossary -> field-links" in out


# --- the records ubiq ships -------------------------------------------------

def test_shipped_features_form_a_valid_order():
    ordered = order(load_features(BUNDLED))
    assert ordered[0].name == "glossary"
    assert len(ordered) >= 10


def test_shipped_feature_codes_match_the_spec():
    spec = (ROOT / "docs" / "spec.md").read_text()
    documented = set(re.findall(r"^- `([EW]\d{3})`", spec, re.MULTILINE))
    owned = [code for f in load_features(BUNDLED) for code in f.codes]
    assert len(owned) == len(set(owned)), "a code is owned by two features"
    assert set(owned) == documented


def test_shipped_feature_docs_exist():
    for f in load_features(BUNDLED):
        assert (ROOT / f.docs.split("#")[0]).is_file(), f"{f.name}: {f.docs}"


# --- ubiq check validates the records --------------------------------------

CONFIG = """glossary:
  - {glob: "features/*.md", term_field: name, ns: feature}
docs: ["features/*.md"]
ref_fields: [requires]
schemas:
  - schema: ".ubiq/schemas/feature.json"
    files: ["features/*.md"]
    format: frontmatter
"""


def feature_repo(tmp_path):
    (tmp_path / ".ubiq" / "schemas").mkdir(parents=True)
    shutil.copy(ROOT / ".ubiq" / "schemas" / "feature.json", tmp_path / ".ubiq" / "schemas")
    (tmp_path / "ubiq.yaml").write_text(CONFIG)
    write_feature(tmp_path / "features", "glossary", codes=["E001"])
    return tmp_path


def check_codes(root, capsys):
    status = main(["check", "--root", str(root), "--json"])
    return status, {d["code"] for d in json.loads(capsys.readouterr().out)["diagnostics"]}


def test_check_accepts_valid_feature_records(tmp_path, capsys):
    root = feature_repo(tmp_path)
    write_feature(root / "features", "field-links", ["glossary"], codes=["E013"])
    status, codes = check_codes(root, capsys)
    assert status == 0, codes


def test_check_fails_when_a_required_feature_is_missing(tmp_path, capsys):
    root = feature_repo(tmp_path)
    write_feature(root / "features", "field-links", ["frontmatter-schemas"])
    status, codes = check_codes(root, capsys)
    assert status == 1 and "E006" in codes


def test_check_fails_on_a_record_the_schema_rejects(tmp_path, capsys):
    root = feature_repo(tmp_path)
    (root / "features" / "bad.md").write_text(
        "---\nname: bad\nrequires: glossary\ncodes: [X1]\nsummary: no docs\n---\n\nbad.\n")
    status, codes = check_codes(root, capsys)
    assert status == 1 and "E009" in codes
