"""Render the dependency and evidence diagrams for Ubiq's no-code pilot."""

import argparse
import re
from pathlib import Path

from ubiq.schemas import load_data

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- ubiq:dogfood-diagram -->"
END = "<!-- /ubiq:dogfood-diagram -->"
BLOCK = re.compile(rf"^{re.escape(BEGIN)}\n.*?^{re.escape(END)}$", re.MULTILINE | re.DOTALL)
ISSUES = "https://github.com/Ltilak13/ubiq/issues"


def label(value: str) -> str:
    return re.sub(r'[#"<>&\r\n]', lambda match: f"#{ord(match[0])};", value)


def issue_link(node: str, issue: int) -> str:
    return f'  click {node} "{ISSUES}/{issue}"'


def plan_lines(plan: dict) -> list[str]:
    steps = plan["steps"]
    nodes = {name: f"step_{index}" for index, name in enumerate(sorted(steps), 1)}
    external = sorted({r for spec in steps.values() for r in spec["requires"] if "/" in r})
    nodes.update({name: f"ext_{index}" for index, name in enumerate(external, 1)})
    lines = ["flowchart LR"]
    for name in external:
        lines.append(f'  {nodes[name]}["{label(name)}"]')
    for name, node in nodes.items():
        if name not in steps:
            continue
        issue = steps[name].get("issue")
        title = name if issue is None else f"{name} (#{issue})"
        lines.append(f'  {node}["{label(title)}"]')
        if issue is not None:
            lines.append(issue_link(node, issue))
    for name, node in nodes.items():
        for prerequisite in sorted(steps[name]["requires"]) if name in steps else []:
            if prerequisite not in nodes:
                raise ValueError(f"{name} requires undeclared step {prerequisite}")
            lines.append(f"  {nodes[prerequisite]} --> {node}")
    return lines


def goal_lines(goal: dict) -> list[str]:
    criterion = goal["criteria"]["AC6"]
    lines = ["flowchart TD", f'  goal["{label(goal["name"])}"]',
             f'  ac6["AC6 ({label(criterion["assessment"])})"]', "  goal -->|criterion| ac6"]
    for issue in sorted(set(criterion.get("issues", [])) | ({criterion["issue"]} if "issue" in criterion else set())):
        lines += [f'  issue_{issue}["Tracking issue #35;{issue}"]', f"  ac6 -->|tracked by| issue_{issue}",
                  issue_link(f"issue_{issue}", issue)]
    if not criterion["support"]:
        lines += ['  evidence["No evidence recorded"]', "  ac6 -.-> evidence"]
    for index, support in enumerate(criterion["support"], 1):
        check = support["check"]
        lines += [f'  feature_{index}["{label(support["feature"])}"]',
                  f'  check_{index}["{label(check["path"] + "#" + check["anchor"])}"]',
                  f"  ac6 -->|supported by| feature_{index}", f"  feature_{index} -->|cites| check_{index}"]
    return lines


def updated(path: Path, lines: list[str]) -> str:
    text = path.read_text(encoding="utf-8")
    replacement = "\n".join([BEGIN, "```mermaid", *lines, "```", END])
    result, count = BLOCK.subn(lambda _: replacement, text)
    if count != 1:
        raise ValueError(f"{path}: expected exactly one diagram block")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="refresh the two marked diagrams")
    args = parser.parse_args()
    plan = ROOT / "docs/plans/no-code-dogfood.md"
    goal = ROOT / "docs/goals/no-code-spec-goal.md"
    generated = {
        plan: updated(plan, plan_lines(load_data(plan, frontmatter=True))),
        goal: updated(goal, goal_lines(load_data(goal, frontmatter=True))),
    }
    stale = [path for path, text in generated.items() if path.read_text(encoding="utf-8") != text]
    for path in stale:
        if args.write:
            path.write_text(generated[path], encoding="utf-8")
        else:
            print(f"{path.relative_to(ROOT)}: stale diagram; run python scripts/dogfood_diagrams.py --write")
    return int(bool(stale) and not args.write)


if __name__ == "__main__":
    raise SystemExit(main())
