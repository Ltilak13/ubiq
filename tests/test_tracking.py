"""Tracking fields: the shared fragment, `x-ubiq-ref`, and edge names."""

import json
from pathlib import Path

import pytest

from ubiq import xref
from ubiq.cli import main

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / ".ubiq/schemas"

# -- x-ubiq-ref parsing -------------------------------------------------------------


def test_annotation_shape_and_defaults():
    assert xref.parse({"ns": "feature", "edge": "requires"}) == xref.XRef("feature", "requires")
    assert xref.parse({"ns": "a", "edge": "part_of", "acyclic": True, "single": True}).single


@pytest.mark.parametrize("value", [
    "feature", {"ns": "feature"}, {"edge": "requires"}, {"ns": "", "edge": "requires"},
    {"ns": "feature", "edge": "Requires"}, {"ns": "feature", "edge": "invoke"},
    {"ns": "feature", "edge": "requires", "single": "yes"},
    {"ns": "feature", "edge": "requires", "since": 1}])
def test_bad_annotation_is_rejected(value):
    with pytest.raises((ValueError, TypeError)):
        xref.parse(value)


def test_annotations_follow_refs_patterns_and_items():
    schema = {"properties": {"criteria": {"patternProperties": {"^AC": {"properties": {
        "requires": {"$ref": "#/$defs/names", "x-ubiq-ref": {"ns": "feature", "edge": "requires"}}}}}},
        "steps": {"type": "array", "items": {"properties": {"after": {
            "x-ubiq-ref": {"ns": "step", "edge": "after"}}}}}},
        "$defs": {"names": {"type": "array"}}}
    found = {a.steps: a.ref.edge for a in xref.collect(schema)}
    assert found == {(("key", "criteria"), ("pattern", "^AC"), ("key", "requires")): "requires",
                     (("key", "steps"), ("items", ""), ("key", "after")): "after"}
    data = {"criteria": {"AC1": {"requires": ["a", "b"]}, "other": {"requires": ["x"]}}}
    [steps] = [a.steps for a in xref.collect(schema) if a.ref.edge == "requires"]
    assert list(xref.values(data, steps)) == [(("criteria", "AC1", "requires"), "a"),
                                              (("criteria", "AC1", "requires"), "b")]


def test_line_of_finds_the_nested_key():
    text = "name: g\ncriteria:\n  AC1:\n    requires: [a]\n  AC2:\n    requires: [b]\n"
    assert xref.line_of(text, ("criteria", "AC2", "requires")) == 7


# -- the shared fragment --------------------------------------------------------------


@pytest.mark.parametrize("name", ["goal", "feature", "plan"])
def test_schemas_reference_the_tracking_fields_instead_of_copying_them(name):
    text = (SCHEMAS / f"{name}.json").read_text()
    assert "tracking.json#/properties/" in text
    assert '"tracking"' not in text


def test_bundled_schema_inlines_tracking_json_as_one_same_document_definition():
    from ubiq.schemas import load_schema
    schema = load_schema(ROOT, SCHEMAS / "feature.json")
    fragment = json.loads((SCHEMAS / "tracking.json").read_text())
    assert schema["$defs"]["ubiq-file:.ubiq/schemas/tracking.json"] == fragment
    assert schema["properties"]["pr"] == {
        "$ref": "#/$defs/ubiq-file:.ubiq~1schemas~1tracking.json/properties/pr"}


def test_a_ref_outside_the_repository_is_an_unloadable_schema(tmp_path):
    from ubiq.schemas import load_schema
    (tmp_path / "s.json").write_text('{"$ref": "../outside.json"}')
    with pytest.raises(ValueError, match="no schema file inside"):
        load_schema(tmp_path, tmp_path / "s.json")


# -- ubiq check and ubiq graph ----------------------------------------------------------

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema", "title": "Work", "type": "object",
    "required": ["name"],
    "properties": {
        "name": {"type": "string"},
        "criteria": {"type": "object", "patternProperties": {"^AC[0-9]+$": {
            "type": "object", "properties": {"requires": {
                "type": "array", "items": {"type": "string"},
                "x-ubiq-ref": {"ns": "feature", "edge": "requires", "acyclic": True}}}}}},
        "part_of": {"type": "string", "x-ubiq-ref": {"ns": "feature", "edge": "part_of"}}}}


def repo(root, goal_text, features=("alpha", "beta"), config=""):
    (root / "schema.json").write_text(json.dumps(SCHEMA))
    (root / "g").mkdir()
    (root / "f").mkdir()
    (root / "g/work.md").write_text(goal_text)
    for name in features:
        (root / f"f/{name}.md").write_text(f"---\nname: {name}\n---\n\nThe {name} feature.\n")
    (root / "ubiq.yaml").write_text(
        'glossary:\n  - {glob: "g/*.md", term_field: name, ns: goal}\n'
        '  - {glob: "f/*.md", term_field: name, ns: feature}\ndocs: ["g/*.md", "f/*.md"]\n'
        f'schemas:\n  - schema: schema.json\n    files: ["g/*.md"]\n    format: frontmatter\n{config}')


def run(root, capsys, *argv):
    status = main([*argv, "--root", str(root), "--json"])
    return status, json.loads(capsys.readouterr().out)


def errors(report, code):
    return [d for d in report["diagnostics"] if d["code"] == code]


GOOD = "---\nname: work\ncriteria:\n  AC1:\n    requires: [alpha, beta]\n---\n\nWork.\n"


def test_annotated_values_resolve_and_make_named_edges(tmp_path, capsys):
    repo(tmp_path, GOOD)
    _status, report = run(tmp_path, capsys, "check")
    assert not errors(report, "E006"), report
    status, report = run(tmp_path, capsys, "graph", "--kind", "requires")
    assert status == 0
    assert [(e["kind"], e["source"], e["target"], e["line"]) for e in report["edges"]] == [
        ("requires", "goal:work", "feature:alpha", 5), ("requires", "goal:work", "feature:beta", 5)]
    _status, report = run(tmp_path, capsys, "graph", "--kind", "invoke")
    assert report["edges"] == []


def test_graph_selects_annotation_by_field_name_or_edge_kind(tmp_path, capsys):
    repo(tmp_path, GOOD)
    schema_path = tmp_path / "schema.json"
    schema = json.loads(schema_path.read_text())
    criteria = schema["properties"]["criteria"]["patternProperties"]["^AC[0-9]+$"]
    criteria["properties"]["requires"]["x-ubiq-ref"]["edge"] = "depends-on"
    schema_path.write_text(json.dumps(schema))
    status, by_field = run(tmp_path, capsys, "graph", "--kind", "requires")
    assert status == 0 and len(by_field["edges"]) == 2
    status, by_kind = run(tmp_path, capsys, "graph", "--kind", "depends-on")
    assert status == 0 and by_kind["edges"] == by_field["edges"]
    assert all(edge["kind"] == "depends-on" for edge in by_field["edges"])


def test_missing_target_is_e006_at_the_field(tmp_path, capsys):
    repo(tmp_path, GOOD.replace("beta", "gamma"))
    status, report = run(tmp_path, capsys, "check")
    assert status == 1
    [error] = errors(report, "E006")
    assert "requires: gamma" in error["message"] and "namespace 'feature'" in error["message"]
    assert error["file"].endswith("g/work.md") and error["line"] == 5


def test_target_in_another_namespace_does_not_resolve(tmp_path, capsys):
    repo(tmp_path, GOOD.replace("beta", "work"))
    _status, report = run(tmp_path, capsys, "check")
    assert len(errors(report, "E006")) == 1


def test_top_level_annotated_field(tmp_path, capsys):
    repo(tmp_path, "---\nname: work\npart_of: nope\n---\n\nWork.\n")
    _status, report = run(tmp_path, capsys, "check")
    [error] = errors(report, "E006")
    assert error["line"] == 3


def test_invalid_annotation_is_a_schema_error(tmp_path, capsys):
    repo(tmp_path, GOOD)
    SCHEMA_BAD = json.loads((tmp_path / "schema.json").read_text())
    SCHEMA_BAD["properties"]["part_of"]["x-ubiq-ref"] = {"ns": "feature"}
    (tmp_path / "schema.json").write_text(json.dumps(SCHEMA_BAD))
    status, report = run(tmp_path, capsys, "check")
    assert status == 1 and errors(report, "E008")


def test_a_ref_fields_field_keeps_its_own_meaning_and_edge_kind(tmp_path, capsys):
    repo(tmp_path, GOOD.replace("criteria:\n  AC1:\n    requires: [alpha, beta]",
                                "requires: [alpha]\ncriteria:\n  AC1:\n    requires: [beta]"),
         config="ref_fields: [requires]\n")
    schema = json.loads((tmp_path / "schema.json").read_text())
    schema["properties"]["requires"] = {"type": "array", "items": {"type": "string"},
                                        "x-ubiq-ref": {"ns": "feature", "edge": "requires"}}
    (tmp_path / "schema.json").write_text(json.dumps(schema))
    _status, report = run(tmp_path, capsys, "graph")
    kinds = sorted((e["kind"], e["target"]) for e in report["edges"])
    # The top-level field is an invoke edge as before, read once; the criterion's is an annotated edge.
    assert kinds == [("invoke", "feature:alpha"), ("requires", "feature:beta")]
    _status, report = run(tmp_path, capsys, "graph", "--kind", "requires")
    assert sorted(e["target"] for e in report["edges"]) == ["feature:alpha", "feature:beta"]


def test_unknown_kind_is_rejected(tmp_path, capsys):
    repo(tmp_path, GOOD)
    assert main(["graph", "--root", str(tmp_path), "--kind", "bogus"]) == 2
    assert "unknown edge kind bogus" in capsys.readouterr().err


def test_this_repository_declares_edges_on_its_goal_and_feature_schemas():
    names = set()
    for name in ("goal", "feature"):
        schema = json.loads((SCHEMAS / f"{name}.json").read_text())
        names |= {a.ref.edge for a in xref.collect(schema)}
    assert names == {"requires", "part_of", "supported_by", "assessed_in"}
