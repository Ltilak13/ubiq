"""Native opt-in schema validation through the public check command."""

import json

from ubiq.cli import main


def run(root, capsys):
    code = main(["check", "--root", str(root), "--json"])
    return code, json.loads(capsys.readouterr().out)


def setup(root, schema, data, *, suffix="yaml", fragment="", mode="document"):
    (root / "schema.json").write_text(json.dumps(schema))
    (root / f"record.{suffix}").write_text(data)
    (root / "ubiq.yaml").write_text(
        "glossary: []\ndocs: []\nschemas:\n"
        f"  - schema: schema.json{fragment}\n    files: [record.{suffix}]\n    format: {mode}\n")


def test_native_schema_validates_domain_contract_and_reports_pointer(tmp_path, capsys):
    schema = {"type": "object", "properties": {"skills": {"type": "array", "items": {
        "type": "object", "properties": {"domain": {"type": "string"}, "allowed": {"type": "boolean"}},
        "required": ["domain"], "allOf": [{"if": {"properties": {"domain": {"const": "delivery"}}},
        "then": {"required": ["allowed"], "properties": {"allowed": {"const": False}}}}]}}}}
    setup(tmp_path, schema, "skills:\n  - domain: delivery\n    allowed: false\n")
    code, result = run(tmp_path, capsys)
    assert code == 0, result
    (tmp_path / "record.yaml").write_text("skills:\n  - domain: delivery\n    allowed: true\n")
    code, result = run(tmp_path, capsys)
    assert code == 1
    assert result["diagnostics"][0]["code"] == "E009"
    assert "/skills/0/allowed" in result["diagnostics"][0]["message"]
    assert result["diagnostics"][0]["file"] == "record.yaml"


def test_frontmatter_uses_typed_values_and_preserves_vocabulary(tmp_path, capsys):
    schema = {"type": "object", "properties": {"enabled": {"type": "boolean"},
              "count": {"type": "integer"}, "word": {"const": "on"}},
              "required": ["enabled", "count", "word"], "additionalProperties": False}
    setup(tmp_path, schema, "---\nenabled: true\ncount: 2\nword: on\n---\nText", suffix="md", mode="frontmatter")
    code, result = run(tmp_path, capsys)
    assert code == 0, result
    from ubiq.records import parse_frontmatter
    meta, _ = parse_frontmatter(tmp_path / "record.md")
    assert meta["enabled"] == "true" and meta["count"] == "2"
    for text in ("no frontmatter", "---\nenabled: true", "---\n[]\n---", "---\nenabled: 'true'\ncount: 2\nword: on\n---"):
        (tmp_path / "record.md").write_text(text)
        code, result = run(tmp_path, capsys)
        assert code == 1 and result["diagnostics"][0]["code"] == "E009", text


def test_fragment_keeps_root_definitions_and_composition(tmp_path, capsys):
    schema = {"type": "array", "$defs": {
        "common": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
        "record": {"allOf": [{"$ref": "#/$defs/common"}, {"properties": {"kind": {"const": "rule"}},
                    "required": ["kind"]}], "unevaluatedProperties": False}}}
    setup(tmp_path, schema, '{"id":"x", "kind":"rule"}', suffix="json", fragment="#/$defs/record")
    code, result = run(tmp_path, capsys)
    assert code == 0, result
    (tmp_path / "record.json").write_text('{"id":"x", "kind":"rule", "extra":1}')
    code, result = run(tmp_path, capsys)
    assert code == 1 and result["diagnostics"][0]["code"] == "E009", result


def test_malformed_instances_fail_closed(tmp_path, capsys):
    for suffix, bodies in {
        "json": ['{"id":1,"id":2}', '{"x":NaN}', '{"x":Infinity}', '{'],
        "yaml": ['id: 1\nid: 2', '1: one', 'x: !!float .nan', 'x: !!binary Zm9v',
                 'x: &cycle [*cycle]', 'x: [', 'x: !!set {a: null}'],
    }.items():
        for body in bodies:
            setup(tmp_path, {"type": "object"}, body, suffix=suffix)
            code, result = run(tmp_path, capsys)
            assert code == 1 and result["diagnostics"][0]["code"] == "E009", (body, result)


def test_bad_schemas_and_refs_fail_closed_without_network(tmp_path, capsys):
    schemas = [
        {"type": "not-a-type"}, {"$schema": "http://json-schema.org/draft-07/schema#"},
        {"$ref": "https://example.invalid/schema.json"}, {"$ref": "other.json"},
        {"$dynamicRef": "https://example.invalid/schema"},
    ]
    for schema in schemas:
        setup(tmp_path, schema, '{}')
        code, result = run(tmp_path, capsys)
        assert code == 1 and result["diagnostics"][0]["code"] == "E008", result
    setup(tmp_path, {"type": "object"}, '{}', fragment="#/$defs/missing")
    code, result = run(tmp_path, capsys)
    assert code == 1 and result["diagnostics"][0]["code"] == "E008", result
    (tmp_path / "schema.json").write_text('{')
    code, result = run(tmp_path, capsys)
    assert code == 1 and result["diagnostics"][0]["code"] == "E008", result
    (tmp_path / "schema.json").unlink()
    code, result = run(tmp_path, capsys)
    assert code == 1 and result["diagnostics"][0]["code"] == "E008", result


def test_missing_targets_and_invalid_bindings_fail_closed(tmp_path, capsys):
    setup(tmp_path, {"type": "object"}, '{}')
    (tmp_path / "record.yaml").unlink()
    code, result = run(tmp_path, capsys)
    assert code == 1 and result["diagnostics"][0]["code"] == "E009", result
    for binding in ("{}", "false", "{schema: schema.json, files: []}",
                    "{schema: schema.json, files: record.yaml}",
                    "{schema: schema.json, files: [x], format: typo}",
                    "{schema: schema.json, files: [x], typo: true}",
                    "{schema: 'https://example.invalid/schema', files: [x]}"):
        (tmp_path / "ubiq.yaml").write_text(f"schemas: [{binding}]\n")
        code, result = run(tmp_path, capsys)
        assert code == 1 and result["diagnostics"][0]["code"] == "E008", (binding, result)


def test_yaml_schema_and_json_boolean_schemas(tmp_path, capsys):
    setup(tmp_path, True, '{}')
    code, result = run(tmp_path, capsys)
    assert code == 0, result
    (tmp_path / "schema.json").write_text('false')
    code, result = run(tmp_path, capsys)
    assert code == 1 and result["diagnostics"][0]["code"] == "E009", result
    (tmp_path / "schema.yaml").write_text("type: object\nrequired: [enabled]\nproperties:\n  enabled:\n    const: true\n")
    (tmp_path / "ubiq.yaml").write_text("schemas: [{schema: schema.yaml, files: [record.yaml]}]\n")
    (tmp_path / "record.yaml").write_text('enabled: true')
    code, result = run(tmp_path, capsys)
    assert code == 0, result


def test_literal_examples_are_not_treated_as_schemas(tmp_path, capsys):
    schema = {"type": "object", "properties": {"$ref": {"type": "string"}},
              "examples": [{"$ref": "https://example.invalid/value"}],
              "const": {"$ref": "https://example.invalid/value"}}
    setup(tmp_path, schema, '{"$ref":"https://example.invalid/value"}')
    code, result = run(tmp_path, capsys)
    assert code == 0, result


def test_invalid_optional_refs_and_cyclic_refs_fail_closed(tmp_path, capsys):
    setup(tmp_path, {"properties": {"optional": {"$ref": "#/$defs/missing"}}}, '{}')
    code, result = run(tmp_path, capsys)
    assert code == 1 and result["diagnostics"][0]["code"] == "E008", result
    setup(tmp_path, {"$ref": "#"}, '{}')
    code, result = run(tmp_path, capsys)
    assert code == 1 and result["diagnostics"][0]["code"] == "E009", result


def test_native_graph_integrity_and_null_configuration(tmp_path, capsys):
    setup(tmp_path, {"type": "object", "x-ubiq": None}, '{}')
    code, result = run(tmp_path, capsys)
    assert code == 1 and result["diagnostics"][0]["code"] == "E008", result
    from test_integrity import example
    data, integrity, _ = example(tmp_path)
    data['relationships'][0]['to'] = 'missing'
    setup(tmp_path, {"type": "object", "x-ubiq": integrity}, json.dumps(data))
    code, result = run(tmp_path, capsys)
    assert code == 1 and any(d['code'] == 'E010' for d in result['diagnostics']), result


def test_referenced_annotation_cannot_hide_invalid_schema(tmp_path, capsys):
    for fragment in ('', '#/examples/0'):
        schema = {'examples': [{'$ref': 'https://example.invalid/schema'}]}
        if not fragment:
            schema['properties'] = {'optional': {'$ref': '#/examples/0'}}
        setup(tmp_path, schema, '{}', fragment=fragment)
        code, result = run(tmp_path, capsys)
        assert code == 1 and result['diagnostics'][0]['code'] == 'E008', (fragment, result)


def test_fragment_does_not_apply_inventory_root_integrity(tmp_path, capsys):
    from test_integrity import example
    _, integrity, _ = example(tmp_path)
    schema = {'type': 'object', 'x-ubiq': integrity,
              '$defs': {'skill': {'type': 'object', 'required': ['name'],
                                  'properties': {'name': {'type': 'string'}}}}}
    setup(tmp_path, schema, '---\nname: example\n---\n', suffix='md',
          fragment='#/$defs/skill', mode='frontmatter')
    code, result = run(tmp_path, capsys)
    assert code == 0, result


def test_finite_recursive_schema_remains_supported(tmp_path, capsys):
    schema = {'type': 'object', 'properties': {
        'name': {'type': 'string'},
        'children': {'type': 'array', 'items': {'$ref': '#'}}},
        'required': ['name']}
    setup(tmp_path, schema, '{"name":"root","children":[{"name":"leaf"}]}')
    code, result = run(tmp_path, capsys)
    assert code == 0, result
