"""Change review contracts: `ubiq impact` and `ubiq compare` against a git baseline.

Expected outputs live in tests/fixtures/review/. See "Change review" in docs/spec.md.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ubiq.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "review"
COMPARE = pytest.mark.xfail(strict=True, reason="M5: ubiq compare is not implemented")

SKILLS_CONFIG = """\
glossary:
  - glob: "skills/*/SKILL.md"
    term_field: name
    ns: skill
docs: ["skills/**/*.md"]
ref_fields: [uses]
"""


def skill(name: str, uses: str = "") -> str:
    """`uses:` sits on line 3, so every edge in the fixtures is declared there."""
    head = f"---\nname: {name}\n{'uses: [' + uses + ']' if uses else 'title: ' + name}\n---\n"
    # Enough shared body that git pairs a moved, renamed skill as a rename.
    return head + "\n## Steps\n\n1. Read the task.\n2. Plan the change.\n3. Make it.\n4. Check it.\n"


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
         "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
        cwd=root, check=True, capture_output=True, text=True).stdout


def commit_repo(root: Path, files: dict[str, str]) -> Path:
    """A repository whose `main` holds `files`, checked out on a feature branch."""
    for name, body in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(body)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    git(root, "checkout", "-qb", "feature")
    return root


def skills_repo(root: Path, config: str = SKILLS_CONFIG) -> Path:
    """a -> b -> c <- d, with e on its own. c owns a sibling reference file."""
    return commit_repo(root, {
        "ubiq.yaml": config,
        "skills/a/SKILL.md": skill("a", "b"),
        "skills/b/SKILL.md": skill("b", "c"),
        "skills/c/SKILL.md": skill("c"),
        "skills/c/reference.md": "Reference notes for c.\n",
        "skills/d/SKILL.md": skill("d", "c"),
        "skills/e/SKILL.md": skill("e"),
    })


def run_json(capsys, *argv: str) -> tuple[int, dict]:
    code = main([*argv, "--json"])
    return code, json.loads(capsys.readouterr().out)


def expected(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def impact(root: Path, capsys, *extra: str) -> tuple[int, dict]:
    code, out = run_json(capsys, "impact", "--since", "main", "--root", str(root), *extra)
    if "baseline" in out:
        assert out["baseline"]["commit"] == git(root, "rev-parse", "main").strip()
        out["baseline"]["commit"] = "<commit>"
    return code, out


def test_impact_edit_of_owned_file(tmp_path, capsys):
    root = skills_repo(tmp_path)
    (root / "skills/c/reference.md").write_text("Reference notes for c, revised.\n")
    assert impact(root, capsys) == (0, expected("impact-edit"))


def test_impact_untracked_addition(tmp_path, capsys):
    root = skills_repo(tmp_path)
    (root / "skills/f").mkdir()
    (root / "skills/f/SKILL.md").write_text(skill("f", "a"))
    assert impact(root, capsys) == (0, expected("impact-add"))


def test_impact_deletion_uses_baseline_callers(tmp_path, capsys):
    root = skills_repo(tmp_path)
    shutil.rmtree(root / "skills/c")
    assert impact(root, capsys) == (0, expected("impact-delete"))


def test_impact_rename_is_one_change(tmp_path, capsys):
    """Unstaged moves still pair as renames; the index is not touched."""
    root = skills_repo(tmp_path)
    shutil.move(root / "skills/c", root / "skills/c2")
    (root / "skills/c2/SKILL.md").write_text(skill("c2"))
    (root / "skills/b/SKILL.md").write_text(skill("b", "c2"))
    (root / "skills/d/SKILL.md").write_text(skill("d", "c2"))
    assert impact(root, capsys) == (0, expected("impact-rename"))
    assert git(root, "diff", "--cached", "--name-only") == ""


def test_impact_depth_limits_hops(tmp_path, capsys):
    root = skills_repo(tmp_path)
    (root / "skills/c/reference.md").write_text("Revised.\n")
    _, out = impact(root, capsys, "--depth", "1")
    assert [a["record"] for a in out["affected"]] == ["skill:b", "skill:d"]


def test_impact_unparsable_record_is_unknown_not_deleted(tmp_path, capsys):
    root = skills_repo(tmp_path)
    (root / "skills/c/SKILL.md").write_text("---\nname: [c\n---\n\nBroken.\n")
    code, out = impact(root, capsys)
    assert code == 0
    assert out["changed"] == [{"record": "skill:c", "change": "unknown",
                               "files": ["skills/c/SKILL.md"]}]
    assert out["complete"] is False
    assert [(i["side"], i["file"]) for i in out["incomplete"]] == [("head", "skills/c/SKILL.md")]


def test_impact_reports_missing_dependency_data(tmp_path, capsys):
    root = skills_repo(tmp_path / "repo", SKILLS_CONFIG + 'edges:\n  external: ["../absent"]\n')
    (root / "skills/c/reference.md").write_text("---\nuses: [b\n---\n\nBroken.\n")
    code, out = impact(root, capsys)
    assert code == 0 and out["complete"] is False
    absent = str((tmp_path / "absent").resolve())
    assert sorted((i["side"], i["file"]) for i in out["incomplete"]) == [
        ("baseline", absent), ("head", absent), ("head", "skills/c/reference.md")]
    assert all(i["reason"] for i in out["incomplete"])


@pytest.mark.parametrize("rev", ["nosuchref", "main~5"])
def test_impact_invalid_rev_exits_2(tmp_path, capsys, rev):
    root = skills_repo(tmp_path)
    code = main(["impact", "--since", rev, "--root", str(root), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 2 and rev in out["error"] and "changed" not in out


def test_impact_outside_git_exits_2(tmp_path, capsys):
    (tmp_path / "ubiq.yaml").write_text(SKILLS_CONFIG)
    assert main(["impact", "--since", "main", "--root", str(tmp_path)]) == 2
    assert "git" in capsys.readouterr().out


def test_impact_baseline_with_invalid_config_exits_2(tmp_path, capsys):
    root = skills_repo(tmp_path, SKILLS_CONFIG + "bogus: 1\n")
    (root / "ubiq.yaml").write_text(SKILLS_CONFIG)
    code, out = run_json(capsys, "impact", "--since", "main", "--root", str(root))
    assert code == 2 and "baseline" in out["error"]


def test_impact_readable_output_explains_paths(tmp_path, capsys):
    root = skills_repo(tmp_path)
    (root / "skills/c/reference.md").write_text("Revised.\n")
    assert main(["impact", "--since", "main", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "edited skill:c" in out
    assert "skill:a -invoke-> skill:b -invoke-> skill:c" in out


GHOSTS_CONFIG = 'glossary: ["glossary/**/*.md"]\ndocs: ["**/*.md"]\n'
TDD = "---\nterm: tdd\n---\n\nThe loop.\n"


def ghosts_repo(root: Path, doc: str, config: str = GHOSTS_CONFIG) -> Path:
    return commit_repo(root, {"ubiq.yaml": config, "glossary/tdd.md": TDD, "doc.md": doc})


def compare(root: Path, capsys) -> tuple[int, dict]:
    code, out = run_json(capsys, "compare", "--since", "main", "--root", str(root))
    if "baseline" in out:
        out["baseline"]["commit"] = "<commit>"
    return code, out


@COMPARE
def test_compare_classifies_by_identity_not_line(tmp_path, capsys):
    root = ghosts_repo(tmp_path, "[[ghost1]] there.\n\n[[ghost2]] here.\n")
    (root / "doc.md").write_text("Intro.\n\nMore.\n\n[[ghost2]] here.\n\n[[ghost3]] there.\n")
    assert compare(root, capsys) == (1, expected("compare-classify"))


@COMPARE
def test_compare_follows_renamed_files(tmp_path, capsys):
    root = ghosts_repo(tmp_path, "Intro.\n\n[[ghost2]] here.\n")
    shutil.move(root / "doc.md", root / "guide.md")
    assert compare(root, capsys) == (0, expected("compare-rename"))


@COMPARE
def test_compare_counts_duplicate_findings(tmp_path, capsys):
    root = ghosts_repo(tmp_path, "[[ghost]]\n[[ghost]]\n")
    (root / "doc.md").write_text("[[ghost]]\n[[ghost]]\n[[ghost]]\n")
    assert compare(root, capsys) == (1, expected("compare-duplicates"))


@COMPARE
def test_compare_new_warning_only_exits_0(tmp_path, capsys):
    root = ghosts_repo(tmp_path, "Uses [[tdd]].\n")
    (root / "doc.md").write_text("No links.\n")
    code, out = compare(root, capsys)
    assert code == 0 and [f["code"] for f in out["new"]] == ["W001"]


@COMPARE
def test_compare_unavailable_baseline_is_not_zero_findings(tmp_path, capsys):
    root = ghosts_repo(tmp_path, "[[ghost]]\n", GHOSTS_CONFIG + "bogus: 1\n")
    (root / "ubiq.yaml").write_text(GHOSTS_CONFIG)
    code, out = compare(root, capsys)
    assert code == 2 and out["status"] == "unavailable" and "baseline" in out["reason"]
    assert not {"new", "resolved", "unchanged", "counts"} & out.keys()


@COMPARE
def test_compare_unavailable_head_is_not_zero_findings(tmp_path, capsys):
    root = ghosts_repo(tmp_path, "[[ghost]]\n")
    (root / "ubiq.yaml").write_text(GHOSTS_CONFIG + "bogus: 1\n")
    code, out = compare(root, capsys)
    assert code == 2 and out["status"] == "unavailable" and "head" in out["reason"]


@COMPARE
def test_compare_invalid_rev_is_unavailable(tmp_path, capsys):
    root = ghosts_repo(tmp_path, "[[ghost]]\n")
    code, out = run_json(capsys, "compare", "--since", "nosuchref", "--root", str(root))
    assert code == 2 and out["status"] == "unavailable" and "nosuchref" in out["reason"]


@COMPARE
def test_compare_markdown_summary(tmp_path, capsys):
    root = ghosts_repo(tmp_path, "[[ghost1]] there.\n\n[[ghost2]] here.\n")
    (root / "doc.md").write_text("[[ghost2]] here.\n\n[[ghost3]] there.\n")
    assert main(["compare", "--since", "main", "--root", str(root), "--markdown"]) == 1
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "**ubiq:** 1 new, 1 resolved, 2 unchanged"
    assert "ghost3" in out and "ghost1" in out and "ghost2" not in out


def test_impact_baseline_symlinks_leaving_the_repository_resolve(tmp_path, capsys):
    """A committed relative link to a sibling checkout reads the same files on both sides."""
    upstream = tmp_path / "upstream" / "skills" / "u"
    upstream.mkdir(parents=True)
    (upstream / "SKILL.md").write_text(skill("u"))
    root = tmp_path / "repo"
    root.mkdir()
    (root / "skills").mkdir()
    (root / "skills" / "u").symlink_to("../../upstream/skills/u")
    skills_repo(root)
    (root / "skills/a/SKILL.md").write_text(skill("a", "u"))
    code, out = impact(root, capsys)
    assert code == 0 and out["complete"] is True
    assert out["changed"] == [{"record": "skill:a", "change": "edited",
                               "files": ["skills/a/SKILL.md"]}]
