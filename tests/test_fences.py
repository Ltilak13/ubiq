import json

import pytest
from test_ubiq import make_repo

from ubiq.cli import main

BASE = """
docs: ["*.feature.md"]
unlinked_mentions: warn
"""
FENCES = r"""
fences:
  gherkin:
    value_refs: ["the record's (\\w+)", '<(\w+)>']
    terms: true
"""


def check(root, capsys):
    status = main(["check", "--root", str(root), "--json"])
    return status, json.loads(capsys.readouterr().out)["diagnostics"]


def test_configured_fences_check_field_names_and_count_term_uses(tmp_path, capsys):
    make_repo(tmp_path, {"discount.md": "---\nterm: discount\naliases: [rebate]\n---\n"},
              {"checkout.feature.md": """---
pct: 10
compound: {type: fixed}
unused:
---
  ~~~~ gherkin extra-info
 Given a rebate
 Then use the record's pct with <compound> and <unused>
 ~~~
 Then use <PCT>
 ~~~~~
 ```python
 Then use <ignored>
 ```
 ```Gherkin
 Then use <ignored>
 ```
 ```gherkin
 Then use the record's pxt and [[unknown]]
"""}, BASE + FENCES)

    status, diags = check(tmp_path, capsys)
    assert status == 1
    assert [(d["code"], d["line"]) for d in diags] == [("E013", 10), ("E013", 19)]
    assert "'PCT'" in diags[0]["message"]
    assert "'pxt'" in diags[1]["message"]

    (tmp_path / "ubiq.yaml").write_text(BASE)
    status, diags = check(tmp_path, capsys)
    assert status == 0
    assert [d["code"] for d in diags] == ["W001"]


def test_fence_options_apply_independently(tmp_path, capsys):
    make_repo(tmp_path, {"discount.md": "---\nterm: discount\n---\n"},
              {"checkout.feature.md": """~~~gherkin
Given a discount using <pct>
~~~
~~~scenario
Given a discount using <pxt>
~~~
"""}, BASE + r"""
fences:
  gherkin:
    value_refs: ['<(\w+)>']
  scenario:
    terms: true
references:
  value:
    severity: warn
""")
    status, diags = check(tmp_path, capsys)
    assert status == 0
    assert [(d["code"], d["line"], d["severity"]) for d in diags] == [
        ("E013", 2, "warning")]
    assert "'pct'" in diags[0]["message"]


def test_docs_glob_selects_registered_feature_record(tmp_path, capsys):
    make_repo(tmp_path, {"checkout.feature.md": """---
term: checkout
---
~~~gherkin
Then use <missing>
~~~
"""}, {}, 'docs: ["glossary/**/*.feature.md"]\n' + FENCES)
    status, diags = check(tmp_path, capsys)
    assert status == 1
    assert [(d["file"], d["line"]) for d in diags if d["code"] == "E013"] == [
        ("glossary/checkout.feature.md", 5)]


def test_commented_fences_do_not_report_fields_or_count_terms(tmp_path, capsys):
    make_repo(tmp_path, {"discount.md": "---\nterm: discount\n---\n"},
              {"checkout.feature.md": """<!--
~~~gherkin
Given a discount using <commented>
-->
~~~
~~~gherkin
# literal <!-- inside the fence
Then use <actual>
~~~
~~~gherkin
Then use <later>
~~~
"""}, BASE + FENCES)
    status, diags = check(tmp_path, capsys)
    assert status == 1
    assert [(d["code"], d.get("line", 0)) for d in diags if d["code"] == "E013"] == [
        ("E013", 8), ("E013", 11)]
    assert [d["code"] for d in diags].count("W001") == 1


@pytest.mark.parametrize(("setting", "message"), [
    ("[]", "fences: expected a mapping"),
    ("{gherkin: {terms: 'true'}}", "fences.gherkin.terms: expected a boolean"),
    ("{gherkin: {value_ref: []}}", "fences.gherkin: unknown setting value_ref"),
    ("{gherkin: {value_refs: ['[']}}", "fences.gherkin.value_refs[0]:"),
    ("{gherkin: {value_refs: ['foo']}}", "expected exactly one capturing group"),
    ("{gherkin: {value_refs: ['(a)(b)']}}", "expected exactly one capturing group"),
])
def test_invalid_fence_config_reports_e008(tmp_path, capsys, setting, message):
    make_repo(tmp_path, {}, {}, BASE + f"fences: {setting}\n")
    status, diags = check(tmp_path, capsys)
    assert status == 1
    assert [d["code"] for d in diags] == ["E008"]
    assert message in diags[0]["message"]
