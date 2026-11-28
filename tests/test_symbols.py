"""Symbol sidecars are contracts for covered Python modules and external consumers."""
import json
from pathlib import Path

import pytest

from ubiq.cli import main
from ubiq.config import load_config
from ubiq.symbols import load_symbols

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repository(tmp_path):
    schema = ROOT / ".ubiq/schemas/symbol.json"
    (tmp_path / schema.name).write_bytes(schema.read_bytes())
    (tmp_path / "ubiq.yaml").write_text(
        'glossary: [{glob: "features/*.md", term_field: name, ns: feature}]\n'
        'docs: ["*.md", "features/*.md"]\n'
        'symbols: {coverage: ["src/demo/*.py"]}\n'
        'schemas: [{schema: symbol.json, files: ["src/demo/*.md"], format: frontmatter}]\n'
    )
    (tmp_path / "features").mkdir()
    (tmp_path / "features/owner.md").write_text("---\nname: owner\n---\n\nOwner.\n")
    package = tmp_path / "src/demo"
    package.mkdir(parents=True)
    (package / "api.py").write_text(
        "def command(root: str, /, *, dry_run: bool = True) -> int:\n"
        "    return 0\n"
        "\n"
        "def _internal():\n"
        "    pass\n"
    )
    (package / "api.md").write_text(
        "---\n"
        "symbols:\n"
        "  command:\n"
        "    id: symbol:demo.api.command\n"
        "    term: command\n"
        "    form: bound\n"
        "    feature: owner\n"
        "    scenarios: [tests/test_api.py::test_command]\n"
        "    params:\n"
        "      type: object\n"
        "      properties:\n"
        '        root: {type: string, x-python-kind: positional-only, x-python-type: str}\n'
        '        dry_run: {type: boolean, x-python-kind: keyword-only, x-python-type: bool, x-python-default: "True"}\n'
        "      required: [root]\n"
        "    result: {type: integer, x-python-type: int}\n"
        "    errors: false\n"
        "---\n"
    )
    return tmp_path


def run_check(root, capsys):
    status = main(["check", "--root", str(root), "--json"])
    return status, json.loads(capsys.readouterr().out)["diagnostics"]


def test_valid_registry_has_a_stable_id_owner_and_scenario(repository, capsys):
    status, findings = run_check(repository, capsys)
    assert status == 0, findings
    registry = load_symbols(load_config(repository))
    [record] = registry.records
    assert record.id == "symbol:demo.api.command"
    assert record.feature == "owner"
    assert record.scenarios == ("tests/test_api.py::test_command",)
    assert record.record == repository / "src/demo/api.md"
    assert record.line == 3


@pytest.mark.parametrize("old,new", [
    ("root: str", "directory: str"),
    ("root: str, /", "root: str"),
    ("= True", "= False"),
    ("-> int", "-> str"),
])
def test_python_signature_drift_names_both_locations(repository, capsys, old, new):
    source = repository / "src/demo/api.py"
    source.write_text(source.read_text().replace(old, new))
    status, findings = run_check(repository, capsys)
    assert status == 1
    [finding] = [found for found in findings if found["code"] == "E010"]
    assert finding["file"] == "src/demo/api.py"
    assert finding["line"] == 1
    assert "src/demo/api.md:3" in finding["message"]


def test_public_symbol_without_record_and_record_without_definition(repository, capsys):
    source = repository / "src/demo/api.py"
    source.write_text(source.read_text().replace("def command(", "def renamed("))
    status, findings = run_check(repository, capsys)
    assert status == 1
    messages = {found["message"] for found in findings if found["code"] == "E010"}
    assert any("Public symbol renamed has no record" in message for message in messages)
    assert any("Symbol record command has no definition" in message for message in messages)


@pytest.mark.parametrize("consumer", [
    "from demo.api import _internal as internal\n",
    "from demo import api as other\nother._internal()\n",
    "import demo.api\ndemo.api._internal()\n",
    "def local():\n    import demo.api as api\n    api._internal()\n",
])
def test_static_cross_module_access_requires_registration(repository, capsys, consumer):
    source = repository / "consumer.py"
    source.write_text(consumer)
    status, findings = run_check(repository, capsys)
    assert status == 1
    [finding] = [found for found in findings if found["code"] == "E010"]
    assert finding["file"] == "consumer.py"
    assert "Unregistered symbol demo.api._internal" in finding["message"]


def test_local_binding_is_independent_of_module_alias(repository, capsys):
    source = repository / "consumer.py"
    source.write_text(
        "from demo import api\n"
        "def use_other(api):\n"
        "    return api._internal()\n"
    )
    status, findings = run_check(repository, capsys)
    assert status == 0, findings


def test_feature_ref_is_namespace_restricted(repository, capsys):
    owner = repository / "features/owner.md"
    owner.rename(repository / "owner.md")
    config = repository / "ubiq.yaml"
    config.write_text(config.read_text().replace("ns: feature}]",
                                                'ns: feature}, {glob: owner.md, term_field: name, ns: other}]'))
    status, findings = run_check(repository, capsys)
    assert status == 1
    [finding] = [found for found in findings if found["code"] == "E006"]
    assert finding["file"] == "src/demo/api.md"
    assert finding["line"] == 7


def test_invalid_inner_json_schema_is_an_error(repository, capsys):
    record = repository / "src/demo/api.md"
    record.write_text(record.read_text().replace("errors: false", "errors: {type: a_typo}"))
    status, findings = run_check(repository, capsys)
    assert status == 1
    assert any(found["code"] == "E009" and "errors" in found["message"] for found in findings)


def test_non_string_frontmatter_key_is_reported(repository, capsys):
    record = repository / "src/demo/api.md"
    record.write_text(record.read_text().replace("  command:", "  command: {}\n  7:"))
    status, findings = run_check(repository, capsys)
    assert status == 1
    assert any(found["code"] == "E009" and "keys must be strings" in found["message"] for found in findings)


def test_missing_source_reports_orphaned_sidecar(repository, capsys):
    (repository / "src/demo/api.py").unlink()
    status, findings = run_check(repository, capsys)
    assert status == 1
    assert any(found["code"] == "E010" and "Symbol sidecar has no module" in found["message"]
               for found in findings)


def test_shipped_contracts_resolve_and_their_test_references_exist():
    registry = load_symbols(load_config(ROOT))
    assert not registry.diagnostics
    assert {record.module.name for record in registry.records} == {"plan.py", "sync.py"}
    ids = [record.id for record in registry.records]
    assert ids == sorted(set(ids))
    for record in registry.records:
        for scenario in record.scenarios:
            filename, name = scenario.split("::")
            assert f"def {name}(" in (ROOT / filename).read_text()
