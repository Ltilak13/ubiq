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


def class_contract(module, name):
    return (
        f"  {name}:\n"
        f"    id: symbol:{module}.{name}\n"
        f"    term: {name}\n"
        "    form: bound\n"
        "    feature: owner\n"
        "    scenarios: []\n"
        "    params: {type: object, properties: {}}\n"
        "    result: {}\n"
        "    errors: false\n"
    )


@pytest.fixture
def class_repository(repository):
    source = repository / "src/demo/api.py"
    source.write_text(source.read_text() + "\nclass C:\n"
                      "    def public(self):\n        pass\n"
                      "    def _internal(self):\n        pass\n")
    record = source.with_suffix(".md")
    record.write_text(record.read_text().removesuffix("---\n")
                      + class_contract("demo.api", "C")
                      + class_contract("demo.api", "C.public") + "---\n")
    return repository


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


def test_dotted_import_checks_names_on_parent_package(repository, capsys):
    package = repository / "src/demo"
    (package / "__init__.py").write_text("def _internal(): pass\n")
    (package / "__init__.md").write_text("---\nsymbols: {}\n---\n")
    (repository / "consumer.py").write_text(
        'import demo.api\ndemo.api.command(".")\ndemo._internal()\n'
    )
    status, findings = run_check(repository, capsys)
    assert status == 1
    [finding] = findings
    assert "Unregistered symbol demo._internal" in finding["message"]
    assert finding["line"] == 3


def test_wildcard_and_intrinsic_module_metadata_are_not_named_symbols(repository, capsys):
    (repository / "consumer.py").write_text(
        'from demo.api import *\nimport demo.api as api\ncommand(".")\napi.__name__\n'
    )
    assert run_check(repository, capsys) == (0, [])


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


def test_signature_drift_keeps_a_canonical_symbol_registered(repository, capsys):
    source = repository / "src/demo/api.py"
    source.write_text(source.read_text().replace("root: str", "directory: str"))
    (repository / "consumer.py").write_text("from demo.api import command\n")
    status, findings = run_check(repository, capsys)
    assert status == 1
    [finding] = [found for found in findings if found["code"] == "E010"]
    assert "src/demo/api.md:3" in finding["message"]
    assert load_symbols(load_config(repository)).records == ()


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


@pytest.mark.parametrize("consumer", [
    "from demo.api import C\nC._internal()\n",
    "from demo.api import C as Alias\nAlias._internal()\n",
    "from .api import C as Alias\nAlias._internal()\n",
    "from demo import api as other\nother.C._internal()\n",
    "import demo.api as api\napi.C._internal()\n",
    "import demo.api\ndemo.api.C._internal()\n",
])
def test_static_class_member_access_requires_its_own_record(class_repository, capsys, consumer):
    (class_repository / "src/demo/consumer.py").write_text(consumer)
    status, findings = run_check(class_repository, capsys)
    assert status == 1
    [finding] = [found for found in findings if found["code"] == "E010"]
    assert finding["file"] == "src/demo/consumer.py"
    assert finding["line"] == 2
    assert "Unregistered symbol demo.api.C._internal" in finding["message"]


def test_class_members_resolve_in_the_imported_modules_table(class_repository, capsys):
    package = class_repository / "src/demo"
    source = package / "api.py"
    (package / "other.py").write_text(source.read_text())
    (package / "other.md").write_text(source.with_suffix(".md").read_text().removesuffix("---\n")
                                     .replace("demo.api.", "demo.other.")
                                     + class_contract("demo.other", "C._internal") + "---\n")
    (class_repository / "consumer.py").write_text(
        "from demo.api import C as ApiClass\n"
        "import demo.other as other\n"
        "ApiClass.public()\n"
        "other.C._internal()\n"
        "ApiClass._internal()\n"
    )
    status, findings = run_check(class_repository, capsys)
    assert status == 1
    [finding] = [found for found in findings if found["code"] == "E010"]
    assert finding["line"] == 5
    assert "Unregistered symbol demo.api.C._internal" in finding["message"]


def test_dynamic_instance_and_attribute_lookups_are_outside_the_static_check(class_repository, capsys):
    (class_repository / "consumer.py").write_text(
        "from demo.api import C\n"
        "C()._internal()\n"
        "getattr(C, '_internal')\n"
        "C.__name__\n"
    )
    status, findings = run_check(class_repository, capsys)
    assert status == 0, findings


def test_dataclass_keyword_only_marker_is_not_a_constructor_parameter(class_repository, capsys):
    source = class_repository / "src/demo/api.py"
    source.write_text("from dataclasses import KW_ONLY, dataclass\n" + source.read_text().replace(
        "class C:\n", "@dataclass\nclass C:\n    _: KW_ONLY\n    flag: bool\n"))
    sidecar = source.with_suffix(".md")
    sidecar.write_text(sidecar.read_text().replace(class_contract("demo.api", "C"),
        class_contract("demo.api", "C").replace("properties: {}", "properties: {flag: "
            "{x-python-kind: keyword-only, x-python-type: bool}}, required: [flag]")))
    status, findings = run_check(class_repository, capsys)
    assert status == 0, findings


@pytest.mark.parametrize("consumer,line", [
    ("from demo import api\napi._internal()\napi = None\n", 2),
    ("from demo import api\napi = api._internal()\n", 2),
    ("def use():\n    from demo import api\n    api._internal()\n    api = None\n", 3),
    ("from demo import api\ndef use(api=api._internal): pass\n", 2),
    ("from demo import api\ndef use(api: api._internal): pass\n", 2),
    ("from demo import api\n@api._internal\ndef use(api): pass\n", 2),
])
def test_static_access_uses_the_binding_in_effect(repository, capsys, consumer, line):
    (repository / "consumer.py").write_text(consumer)
    status, findings = run_check(repository, capsys)
    assert status == 1
    [finding] = [found for found in findings if found["code"] == "E010"]
    assert finding["line"] == line
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


@pytest.mark.parametrize("contract", [
    "{type: a_typo}",
    "{$ref: 'https://example.test/schema'}",
    "{$ref: '#/$defs/missing'}",
    "{$schema: 'http://json-schema.org/draft-07/schema#'}",
])
def test_invalid_inner_json_schema_is_an_error(repository, capsys, contract):
    record = repository / "src/demo/api.md"
    record.write_text(record.read_text().replace("errors: false", f"errors: {contract}"))
    status, findings = run_check(repository, capsys)
    assert status == 1
    assert any(found["code"] == "E009" and "errors" in found["message"] for found in findings)


def test_inner_json_schema_may_use_a_local_reference(repository, capsys):
    record = repository / "src/demo/api.md"
    record.write_text(record.read_text().replace("errors: false", "errors: {$ref: '#/$defs/error', "
                                                "$defs: {error: {type: string}}}"))
    status, findings = run_check(repository, capsys)
    assert status == 0, findings


def test_non_string_frontmatter_key_is_reported(repository, capsys):
    record = repository / "src/demo/api.md"
    record.write_text(record.read_text().replace("  command:", "  command: {}\n  7:"))
    status, findings = run_check(repository, capsys)
    assert status == 1
    assert any(found["code"] == "E009" and "keys must be strings" in found["message"] for found in findings)


@pytest.mark.parametrize("pattern", ["*.py", "api.[p]y", "*"])
def test_missing_source_reports_orphaned_sidecar(repository, capsys, pattern):
    config = repository / "ubiq.yaml"
    config.write_text(config.read_text().replace("src/demo/*.py", f"src/demo/{pattern}"))
    (repository / "src/demo/api.py").unlink()
    status, findings = run_check(repository, capsys)
    assert status == 1
    assert any(found["code"] == "E010" and "Symbol sidecar has no module" in found["message"]
               for found in findings)


def test_unrelated_deep_source_does_not_crash_the_check(repository, capsys):
    (repository / "consumer.py").write_text("1" + " + 1" * 1200 + "\n")
    status, findings = run_check(repository, capsys)
    assert status == 0, findings


def test_covered_symlink_cannot_point_outside_the_repository(repository, tmp_path_factory, capsys):
    source = repository / "src/demo/api.py"
    outside = tmp_path_factory.mktemp("outside") / "api.py"
    source.rename(outside)
    try:
        source.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    status, findings = run_check(repository, capsys)
    assert status == 1
    [finding] = [found for found in findings if found["code"] == "E010"]
    assert finding["file"] == "src/demo/api.py"
    assert "resolves outside the repository" in finding["message"]


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
