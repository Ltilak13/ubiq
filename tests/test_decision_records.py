"""Decision records: schema, supersession checks, generated index, and the comment mirror."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_sync import Fake, issue

from ubiq.cli import main
from ubiq.config import load_config
from ubiq.decisions import index_block, load_decisions
from ubiq.sync import (
    GitHub,
    cmd_sync,
    decision_desired,
    desired_from_config,
    drift,
    plan,
)

ROOT = Path(__file__).resolve().parents[1]
BOT = "github-actions[bot]"


def rec(name="alpha", question=5, status="accepted", supersedes="", **extra):
    return {"name": name, "question": question, "status": status, "decided": "2026-11-27", "by": "Lucas",
            "options": ["a", "b"], "outcome": ["Use a."], "supersedes": supersedes,
            "path": f"docs/decisions/0001-{name}.md", **extra}


def comment(cid, body, login=BOT):
    return {"id": cid, "body": body, "user": {"login": login}}


def with_comments(n, comments, state="open"):
    return {**issue(n, state), "ubiq_comments": comments}


# -- the repository's own records ----------------------------------------------------

def test_repository_decisions_validate_and_the_index_is_current(capsys):
    assert main(["check", "--root", str(ROOT), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["diagnostics"] == []
    cfg = load_config(ROOT)
    names = [d["name"] for d in load_decisions(cfg)]
    assert "rule-language" in names and "feature-interactions" in names
    assert index_block(load_decisions(cfg)) in (ROOT / "docs/decisions/README.md").read_text()


def test_repository_decisions_are_desired_items_with_comments():
    items = [d for d in desired_from_config(load_config(ROOT)) if d.kind == "decision"]
    assert items and all(d.comment.startswith(d.comment_marker) and d.listed for d in items)


# -- ubiq check over decisions -------------------------------------------------------

SCHEMA = (ROOT / ".ubiq/schemas/decision.json").read_text()


def text(name, question="5", status="accepted", extra=""):
    return (f"---\nname: {name}\nquestion: {question}\nstatus: {status}\ndecided: 2026-11-27\nby: me\n"
            f"options: [a, b]\noutcome:\n  - Use a.\n{extra}---\n\nWhy.\n")


def repo(root, files, readme=True):
    (root / "schema.json").write_text(SCHEMA)
    (root / "d").mkdir()
    for name, body in files.items():
        (root / "d" / name).write_text(body)
    cfg = ('glossary:\n  - {glob: "d/[0-9]*.md", term_field: name, ns: decision}\ndocs: ["d/*.md"]\n'
           'schemas:\n  - schema: schema.json\n    files: ["d/[0-9]*.md"]\n    format: frontmatter\n'
           'sync:\n  repo: o/r\n  records:\n    - {glob: "d/[0-9]*.md", kind: decision}\n')
    (root / "ubiq.yaml").write_text(cfg)
    if readme:
        (root / "d/README.md").write_text("# D\n\n<!-- ubiq-decisions:start -->\n<!-- ubiq-decisions:end -->\n")
        main(["decisions", "--root", str(root), "--write"])


def check(root, capsys):
    status = main(["check", "--root", str(root), "--json"])
    return status, json.loads(capsys.readouterr().out)["diagnostics"]


def test_supersedes_needs_a_superseded_target(tmp_path, capsys):
    repo(tmp_path, {"0001-alpha.md": text("alpha"), "0002-beta.md": text("beta", extra="supersedes: alpha\n")
                    })
    # alpha is accepted, not superseded, so the pair is inconsistent until alpha is marked.
    _status, found = check(tmp_path, capsys)
    assert [d["code"] for d in found] == ["E009"] and "not 'superseded'" in found[0]["message"]


def test_supersession_pair_passes(tmp_path, capsys):
    repo(tmp_path, {"0001-alpha.md": text("alpha", status="superseded"),
                    "0002-beta.md": text("beta", extra="supersedes: alpha\n")})
    status, found = check(tmp_path, capsys)
    assert status == 0 and found == []


@pytest.mark.parametrize("old, new", [("question: 5\n", ""), ("question: 5", "question: 0"),
                                      ("question: 5", "question: '#5'"), ("status: accepted", "status: done"),
                                      ("decided: 2026-11-27", "decided: soon")])
def test_schema_rejects_bad_decisions(tmp_path, capsys, old, new):
    repo(tmp_path, {"0001-alpha.md": text("alpha").replace(old, new)})
    status, found = check(tmp_path, capsys)
    assert status == 1 and any(d["code"] == "E009" for d in found)


def test_supersedes_must_name_a_decision(tmp_path, capsys):
    repo(tmp_path, {"0001-alpha.md": text("alpha", extra="supersedes: ghost\n")})
    status, found = check(tmp_path, capsys)
    assert status == 1 and any(d["code"] == "E006" for d in found)


def test_superseded_status_needs_a_replacement(tmp_path, capsys):
    repo(tmp_path, {"0001-alpha.md": text("alpha", status="superseded")})
    status, found = check(tmp_path, capsys)
    assert status == 1 and "no decision supersedes it" in found[0]["message"]


def test_stale_or_missing_index_fails_and_write_fixes_it(tmp_path, capsys):
    repo(tmp_path, {"0001-alpha.md": text("alpha")})
    (tmp_path / "d/0002-beta.md").write_text(text("beta", question="6"))
    status, found = check(tmp_path, capsys)
    assert status == 1 and "out of date" in found[0]["message"]
    assert main(["decisions", "--root", str(tmp_path), "--write"]) == 0
    status, found = check(tmp_path, capsys)
    assert status == 0 and "[[decision:beta]]" in (tmp_path / "d/README.md").read_text()
    (tmp_path / "d/README.md").write_text("# no block\n")
    status, found = check(tmp_path, capsys)
    assert status == 1 and "needs one generated decision list" in found[0]["message"]


def test_index_names_the_replacement():
    block = index_block([rec("old", status="superseded"), rec("new", supersedes="old")])
    assert "superseded by [[decision:new]]" in block


# -- the comment mirror --------------------------------------------------------------

def test_accepted_decision_gets_one_comment_and_closes_the_question():
    [item] = decision_desired([rec()])
    first, second = plan([item], [with_comments(5, [])])
    assert (first["action"], second["action"]) == ("close", "decision-comment")
    assert first["comment"] == "" and second["issue"] == 5
    assert second["body"].startswith("<!-- ubiq-decision: alpha -->")
    assert second["body"].endswith("<!-- /ubiq-decision: alpha -->")
    assert "- Use a." in second["body"] and "Options considered: a, b." in second["body"]


def test_a_current_comment_is_a_noop_and_a_closed_issue_is_never_reopened():
    [item] = decision_desired([rec()])
    snapshot = [with_comments(5, [comment(1, item.comment)], state="closed")]
    assert drift(plan([item], snapshot)) == []


def test_changed_record_updates_the_generated_comment_only():
    [item] = decision_desired([rec(outcome=["Use b."])])
    old = decision_desired([rec()])[0].comment
    person = comment(2, item.comment, login="someone")
    quoting_bot = comment(3, "see " + item.comment_marker)
    found = drift(plan([item], [with_comments(5, [person, quoting_bot, comment(1, old)], "closed")]))
    assert [(a["action"], a["comment_id"]) for a in found] == [("decision-comment-update", 1)]


def test_a_person_comment_with_the_marker_is_not_ours_and_a_new_one_is_made():
    [item] = decision_desired([rec()])
    found = drift(plan([item], [with_comments(5, [comment(2, item.comment, login="someone")], "closed")]))
    assert [a["action"] for a in found] == ["decision-comment"]


def test_duplicate_generated_comments_warn():
    [item] = decision_desired([rec()])
    snapshot = [with_comments(5, [comment(1, item.comment), comment(2, item.comment)], "closed")]
    assert [(a["action"], a["comment_id"]) for a in drift(plan([item], snapshot))] == [("warn", 2)]


def test_superseded_comment_names_the_replacement_and_proposed_mirrors_nothing():
    old, new, draft = decision_desired([rec("old", 5, "superseded"), rec("new", 6, supersedes="old"),
                                        rec("draft", 7, "proposed")])
    assert "superseded by `new` (answers #6, decided 2026-11-27)" in old.comment
    assert "(accepted)" in new.comment
    snapshot = [with_comments(7, [])]
    assert draft.comment == "" and plan([draft], snapshot)[0]["action"] == "noop"


def test_question_that_is_not_an_issue_warns():
    [item] = decision_desired([rec(question=99)])
    assert [a["action"] for a in plan([item], [with_comments(5, [])]) if a["action"] == "warn"] == ["warn"]


def test_apply_posts_then_patches_the_comment_endpoint():
    [item] = decision_desired([rec()])
    fake = Fake({("POST", "/5/comments"): {"id": 77}})
    create = plan([item], [with_comments(5, [], "closed")])[0]
    GitHub("o/r", "t", fake, 0).apply([create], [])
    assert create["comment_id"] == 77 and fake.calls[0][:2] == ("POST", "/5/comments")
    update = {"action": "decision-comment-update", "issue": 5, "comment_id": 77, "body": "x"}
    GitHub("o/r", "t", fake, 0).apply([update], [])
    assert fake.calls[1][:2] == ("PATCH", "/comments/77") and fake.calls[1][3] == {"body": "x"}


def test_closing_a_question_posts_no_extra_comment():
    fake = Fake()
    close = {"action": "close", "issue": 5, "comment": ""}
    GitHub("o/r", "t", fake, 0).apply([close], [])
    assert [c[:2] for c in fake.calls] == [("PATCH", "/5")]


def test_with_comments_reads_only_the_named_issues():
    fake = Fake({("GET", "/5/comments?per_page=100&page=1"): [comment(1, "x")]})
    out = GitHub("o/r", "t", fake, 0).with_comments([issue(5), issue(6)], [5])
    assert out[0]["ubiq_comments"][0]["id"] == 1 and "ubiq_comments" not in out[1]
    assert [c[1] for c in fake.calls] == ["/5/comments?per_page=100&page=1"]


def test_sync_check_fails_for_a_question_with_no_issue(tmp_path, capsys, monkeypatch):
    repo(tmp_path, {"0001-alpha.md": text("alpha", question="99")})
    monkeypatch.setenv("GITHUB_TOKEN", "t")

    def transport(method, url, token, payload=None):
        return [] if "page=1" in url else {}

    args = SimpleNamespace(root=str(tmp_path), ref=None, repo=None, apply=False, check=True, dry_run=False)
    assert cmd_sync(args, transport, 0) == 1
    assert "listed number is not an issue" in capsys.readouterr().out


def test_closes_false_posts_the_comment_but_leaves_the_question_open():
    [item] = decision_desired([rec(closes=False)])
    assert item.state == "open"
    found = plan([item], [with_comments(5, [])])
    assert [a["action"] for a in found] == ["decision-comment"]
    [default] = decision_desired([rec()])
    assert default.state == "closed"


def test_closes_must_be_a_boolean(tmp_path, capsys):
    repo(tmp_path, {"0001-alpha.md": text("alpha", extra="closes: no way\n")})
    status, found = check(tmp_path, capsys)
    assert status == 1 and any(d["code"] == "E009" for d in found)


def test_decision_0004_does_not_close_its_tracking_issue():
    by_name = {d.ident["decision"]: d for d in desired_from_config(load_config(ROOT)) if d.kind == "decision"}
    assert by_name["feature-interactions"].state == "open" and by_name["rule-language"].state == "closed"
