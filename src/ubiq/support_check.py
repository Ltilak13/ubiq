"""Support matrix as records: drift checks and the generated support table.

Records under `support.records` (one per runtime version) are the single source.
`requires-python`, the CI test matrix, and the support table are views, and
`ubiq check` reports every disagreement:

  E013 support-drift   a view disagrees with the records, or a record or feature
                       declaration is inconsistent
  W008 support-eol     a record says `supported` after its end-of-life date

`ubiq support` prints the table; `--write` refreshes the marked block.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .check import Diagnostic
from .config import Config, SupportSpec
from .schemas import load_data
from .support import parse_specifier, satisfies

BEGIN = "<!-- ubiq:support-table -->"
END = "<!-- /ubiq:support-table -->"
LIVE = ("supported", "deprecated")


@dataclass(frozen=True)
class Entry:
    path: Path
    name: str
    runtime: str
    version: str
    status: str
    eol: str
    reason: str

    @property
    def key(self) -> tuple[int, ...]:
        return tuple(int(n) for n in self.version.split("."))


def _diag(code: str, message: str, file: Path) -> Diagnostic:
    return Diagnostic(code, message, file)


def load_entries(cfg: Config, spec: SupportSpec) -> tuple[list[Entry], list[Diagnostic]]:
    """The support records that load and carry every field; schema validation reports the rest."""
    entries: list[Entry] = []
    diags: list[Diagnostic] = []
    for path in sorted(spec.records.walk(cfg.ignore)):
        if not path.is_file():
            continue
        try:
            data = load_data(path, frontmatter=True)
        except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
            diags.append(Diagnostic("E005", f"cannot read support record: {exc}", path))
            continue
        fields = ("name", "runtime", "version", "status", "eol", "reason")
        if not all(isinstance(data.get(f), str) for f in fields) \
                or not re.fullmatch(r"[0-9]+\.[0-9]+", data["version"]):
            continue  # the schema binding reports the malformed field
        entries.append(Entry(path, *(data[f] for f in fields)))
    if not entries and not diags:
        diags.append(_diag("E013", f"no support records match {spec.records.pattern}",
                           cfg.root / "ubiq.yaml"))
    return sorted(entries, key=lambda e: (e.runtime, e.key)), diags


def _section_lines(text: str, table: str) -> list[str]:
    lines: list[str] = []
    inside = False
    for line in text.splitlines():
        header = re.match(r"^\s*\[([^\[\]]+)\]\s*(#.*)?$", line)
        if header and not line.startswith((" ", "\t")):
            inside = header.group(1).strip() == table
            continue
        if inside:
            lines.append(line)
    return lines


def requires_python(text: str) -> str | None:
    """The `requires-python` value of a pyproject.toml's [project] table."""
    for line in _section_lines(text, "project"):
        match = re.match(r'^requires-python\s*=\s*"([^"]*)"', line)
        if match:
            return match.group(1)
    return None


def extras(text: str) -> set[str]:
    """Names declared in [project.optional-dependencies]."""
    names = set()
    for line in _section_lines(text, "project.optional-dependencies"):
        match = re.match(r'^([A-Za-z0-9_.-]+|"[^"]+")\s*=', line)
        if match:
            names.add(match.group(1).strip('"'))
    return names


def _read(path: Path, label: str, diags: list[Diagnostic], cfg: Config) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        diags.append(_diag("E013", f"cannot read {label}: {exc}", cfg.root / "ubiq.yaml"))
        return None


def _check_records(entries: list[Entry]) -> list[Diagnostic]:
    diags = []
    seen: dict[tuple[str, str], Entry] = {}
    for e in entries:
        if e.name != f"{e.runtime}-{e.version}":
            diags.append(_diag("E013", f"support record name '{e.name}' should be "
                               f"'{e.runtime}-{e.version}'", e.path))
        if (e.runtime, e.version) in seen:
            diags.append(_diag("E013", f"{e.runtime} {e.version} has two support records "
                               f"({seen[(e.runtime, e.version)].path.name}, {e.path.name})", e.path))
        seen.setdefault((e.runtime, e.version), e)
    return diags


def _check_requires(cfg: Config, spec: SupportSpec, python: list[Entry]) -> list[Diagnostic]:
    path = cfg.root / spec.pyproject
    diags: list[Diagnostic] = []
    text = _read(path, spec.pyproject, diags, cfg)
    if text is None:
        return diags
    declared = requires_python(text)
    live = [e for e in python if e.status in LIVE]
    if declared is None:
        return [*diags, _diag("E013", "pyproject.toml has no [project] requires-python", path)]
    try:
        clauses = parse_specifier(declared)
    except ValueError as exc:
        return [*diags, _diag("E013", f"requires-python: {exc}", path)]
    if not live:
        return [*diags, _diag("E013", "no supported or deprecated Python record", path)]
    floor = min(e.key for e in live)
    lower = [v for op, v in clauses if op == ">="]
    if not lower or tuple(lower[0][:2]) != floor:
        want = ".".join(map(str, floor))
        diags.append(_diag("E013", f'requires-python "{declared}" does not start at the lowest '
                           f'supported version; the support records say ">={want}"', path))
    for e in live:
        if not satisfies(e.key, declared):
            diags.append(_diag("E013", f'requires-python "{declared}" excludes {e.status} '
                               f"Python {e.version}", path))
    top = max(e.key for e in live)
    for e in python:
        if e.status == "unsupported" and floor < e.key < top:
            diags.append(_diag("E013", f"Python {e.version} is unsupported but sits between "
                               "supported versions; mark it supported or deprecated", e.path))
    return diags


def _matrix_versions(workflow: dict, spec: SupportSpec) -> tuple[set[str], str | None]:
    job = (workflow.get("jobs") or {}).get(spec.job)
    if not isinstance(job, dict):
        return set(), f"job '{spec.job}' not found"
    matrix = (job.get("strategy") or {}).get("matrix")
    if not isinstance(matrix, dict):
        return set(), f"job '{spec.job}' has no strategy.matrix"
    found: list = []
    values = matrix.get(spec.matrix, [])
    found.extend(values if isinstance(values, list) else [values])
    for item in matrix.get("include") or []:
        if isinstance(item, dict) and spec.matrix in item:
            found.append(item[spec.matrix])
    if not found:
        return set(), f"matrix has no '{spec.matrix}' values"
    return {str(v) for v in found}, None


def _check_workflow(cfg: Config, spec: SupportSpec, python: list[Entry]) -> list[Diagnostic]:
    path = cfg.root / spec.workflow
    diags: list[Diagnostic] = []
    text = _read(path, spec.workflow, diags, cfg)
    if text is None:
        return diags
    try:
        workflow = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return [*diags, _diag("E013", f"cannot parse {spec.workflow}: {exc}", path)]
    if not isinstance(workflow, dict):
        return [*diags, _diag("E013", f"{spec.workflow}: expected a mapping", path)]
    versions, problem = _matrix_versions(workflow, spec)
    if problem:
        return [*diags, _diag("E013", f"{spec.workflow}: {problem}", path)]
    by_version = {e.version: e for e in python}
    for e in python:
        if e.status in LIVE and e.version not in versions:
            diags.append(_diag("E013", f"{e.status} Python {e.version} is missing from the "
                               f"{spec.job} matrix in {spec.workflow}", path))
    for version in sorted(versions):
        entry = by_version.get(version)
        if entry is None:
            hint = " (quote versions such as \"3.10\" so YAML keeps them as text)" \
                if re.fullmatch(r"3\.[0-9]", version) else ""
            diags.append(_diag("E013", f"Python {version} in the {spec.job} matrix has no "
                               f"support record{hint}", path))
        elif entry.status == "unsupported":
            diags.append(_diag("E013", f"unsupported Python {version} is in the {spec.job} "
                               "matrix", path))
    for name, job in (workflow.get("jobs") or {}).items():
        for step in (job or {}).get("steps") or []:
            value = ((step or {}).get("with") or {}).get(spec.matrix)
            if isinstance(value, (str, float)) and "${{" not in str(value):
                version = str(value)
                entry = by_version.get(version)
                if entry is None or entry.status == "unsupported":
                    why = "is unsupported" if entry else "has no support record"
                    diags.append(_diag("E013", f"job '{name}' pins Python {version}, which {why}",
                                       path))
    return diags


def _check_features(cfg: Config, spec: SupportSpec) -> list[Diagnostic]:
    if not spec.features:
        return []
    diags: list[Diagnostic] = []
    text = _read(cfg.root / spec.pyproject, spec.pyproject, diags, cfg)
    known = extras(text) if text is not None else set()
    for glob in spec.features:
        for path in sorted(glob.walk(cfg.ignore)):
            if not path.is_file():
                continue
            try:
                data = load_data(path, frontmatter=True)
            except (OSError, ValueError, TypeError, yaml.YAMLError):
                continue  # parse errors belong to the record's own schema and E005
            runtime = data.get("runtime")
            if runtime is not None:
                python = runtime.get("python") if isinstance(runtime, dict) else None
                try:
                    if not isinstance(python, str):
                        raise TypeError("runtime must be a mapping with a python specifier")
                    parse_specifier(python)
                except (TypeError, ValueError) as exc:
                    diags.append(_diag("E013", f"runtime: {exc}", path))
            extra = data.get("extra")
            if extra is not None and extra not in known:
                diags.append(_diag("E013", f"extra '{extra}' is not declared in "
                                   f"[project.optional-dependencies] of {spec.pyproject}", path))
    return diags


def render_table(entries: list[Entry]) -> str:
    """The marked support table block, newest version first."""
    rows = ["| Runtime | Version | Status | End of life | Reason |",
            "| --- | --- | --- | --- | --- |"]
    for e in sorted(entries, key=lambda e: (e.runtime, e.key), reverse=True):
        rows.append(f"| {e.runtime.capitalize()} | {e.version} | {e.status} | {e.eol} | "
                    f"{e.reason.replace('|', chr(92) + '|')} |")
    return "\n".join([BEGIN, *rows, END])


def _block(text: str) -> re.Match | None:
    return re.search(re.escape(BEGIN) + r".*?" + re.escape(END), text, re.DOTALL)


def write_table(path: Path, entries: list[Entry]) -> bool:
    """Refresh (or fail to find) the marked block. True when the file changed."""
    text = path.read_text(encoding="utf-8")
    match = _block(text)
    if match is None:
        raise ValueError(f"{path} has no {BEGIN} ... {END} block")
    new = text[:match.start()] + render_table(entries) + text[match.end():]
    if new == text:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def _check_table(cfg: Config, spec: SupportSpec, entries: list[Entry]) -> list[Diagnostic]:
    if spec.table is None:
        return []
    path = cfg.root / spec.table
    diags: list[Diagnostic] = []
    text = _read(path, spec.table, diags, cfg)
    if text is None:
        return diags
    match = _block(text)
    if match is None:
        return [_diag("E013", f"{spec.table} has no support table block; add {BEGIN} and {END} "
                      "and run `ubiq support --write`", path)]
    if match.group(0) != render_table(entries):
        return [_diag("E013", "support table is out of date with the support records; "
                      "run `ubiq support --write`", path)]
    return []


def _eol(entries: list[Entry], today: datetime.date) -> list[Diagnostic]:
    diags = []
    for e in entries:
        try:
            ended = datetime.date.fromisoformat(e.eol) < today
        except ValueError:
            continue  # the schema reports a malformed date
        if e.status == "supported" and ended:
            diags.append(_diag("W008", f"Python {e.version} is marked supported but its end of "
                               f"life ({e.eol}) has passed; deprecate or drop it", e.path))
    return diags


def check_support(cfg: Config, today: datetime.date | None = None) -> list[Diagnostic]:
    """Drift between support records and the views derived from them."""
    spec = cfg.support
    if spec is None:
        return []
    entries, diags = load_entries(cfg, spec)
    diags += _check_records(entries)
    python = [e for e in entries if e.runtime == "python"]
    if python:
        diags += _check_requires(cfg, spec, python)
        diags += _check_workflow(cfg, spec, python)
    diags += _check_table(cfg, spec, entries)
    diags += _check_features(cfg, spec)
    diags += _eol(entries, today or datetime.date.today())
    return diags
