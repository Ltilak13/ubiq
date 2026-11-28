"""Verify incremental adoption using the installed release wheel in a fresh repository."""

import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from zipfile import ZipFile

RECORDS = Path(__file__).resolve().parents[1] / "src" / "ubiq" / "features"
GLOSSARY_ONLY = [
    "catalogs",
    "field-refs",
    "frontmatter-schemas",
    "id-references",
    "markdown-references",
    "overlays",
]
WITH_SCHEMAS = [
    "catalogs",
    "field-refs",
    "id-references",
    "markdown-references",
    "overlays",
    "record-graphs",
    "typed-coverage",
]


def check_feature_records(wheel: Path, records: Path) -> None:
    expected = {f"ubiq/features/{record.name}" for record in records.glob("*.md")}
    with ZipFile(wheel) as archive:
        missing = expected.difference(archive.namelist())
    if not expected:
        raise SystemExit(f"No feature records at {records}")
    if missing:
        raise SystemExit(f"{wheel.name} is missing bundled feature records: {', '.join(sorted(missing))}")


def check_adoption(cli: Path, repo: Path, used: list[str], expected: list[str]) -> None:
    subprocess.run([cli, "check"], cwd=repo, check=True)
    result = subprocess.run(
        [cli, "plan", "--next", "--json"], cwd=repo, text=True, stdout=subprocess.PIPE, check=False,
    )
    if result.returncode:
        raise SystemExit(f"ubiq plan --next failed ({result.returncode}): {result.stdout.strip()}")
    plan = json.loads(result.stdout)
    names = [feature["name"] for feature in plan["features"]]
    if plan["used"] != used or names != expected:
        raise SystemExit(
            f"Expected used={used} and next={expected}, got used={plan['used']} and next={names}"
        )
    print(f"With {', '.join(used)} adopted, next steps are {', '.join(names)}", flush=True)


def main(wheel: Path, records: Path = RECORDS) -> None:
    check_feature_records(wheel, records)
    # Keep an inherited source checkout off the installed CLI's import path.
    os.environ.pop("PYTHONPATH", None)
    os.environ.pop("PYTHONHOME", None)
    with tempfile.TemporaryDirectory(prefix="ubiq-release-", dir=os.environ.get("RUNNER_TEMP")) as tmp:
        outside_checkout = Path(tmp)
        environment = outside_checkout / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        binaries = environment / "bin"
        subprocess.run(
            [binaries / "python", "-I", "-m", "pip", "install", str(wheel)],
            cwd=outside_checkout, check=True,
        )
        repo = outside_checkout / "repo"
        subprocess.run(["git", "init", "--quiet", repo], cwd=outside_checkout, check=True)
        (repo / "glossary").mkdir()
        (repo / "glossary" / "widget.md").write_text(
            "---\nterm: widget\nns: example\n---\n\nA tracked item.\n", encoding="utf-8",
        )
        config = repo / "ubiq.yaml"
        glossary_config = "glossary: ['glossary/*.md']\n"
        config.write_text(glossary_config, encoding="utf-8")
        check_adoption(binaries / "ubiq", repo, ["glossary"], GLOSSARY_ONLY)

        (repo / "glossary.schema.json").write_text(
            '{"type":"object","required":["term"],"properties":{"term":{"type":"string"}}}\n',
            encoding="utf-8",
        )
        config.write_text(
            glossary_config + """schemas:
  - schema: glossary.schema.json
    files: ['glossary/*.md']
    format: frontmatter
""",
            encoding="utf-8",
        )
        check_adoption(binaries / "ubiq", repo, ["glossary", "frontmatter-schemas"], WITH_SCHEMAS)


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]) if len(sys.argv) > 2 else RECORDS)
