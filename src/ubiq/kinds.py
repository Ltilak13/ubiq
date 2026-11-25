"""Reference kinds: where each kind matches, how it resolves, and what it reports.

One policy table drives scanning, checks, `ubiq refs`, and the CLI. The
`references:` setting composes overrides onto it, and every guarantee below is
checked against the loaded configuration, so no configuration can switch one off.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from .config import Config
    from .records import Glossary, Term
    from .scan import Ref


class Context(enum.Flag):
    """Document regions a kind may match in, besides plain prose.

    Fences, frontmatter, and reference definitions have no member, so no policy,
    and therefore no configuration, can scan them.
    """
    NONE = 0
    INLINE_CODE = enum.auto()
    ADDRESS = enum.auto()  # link and image destinations, bare URLs, emails, HTML tags
    COMMENT = enum.auto()  # HTML comments

    @classmethod
    def parse(cls, names: Iterable[str]) -> Context:
        flags = cls.NONE
        for name in names:
            member = cls.__members__.get(name.upper())
            if not member:
                regions = ", ".join(cast(str, flag.name).lower() for flag in cls if flag)
                raise ValueError(f"unknown region {name}; expected {regions}")
            flags |= member
        return flags

    def names(self) -> list[str]:
        return [cast(str, flag.name).lower() for flag in type(self) if flag and flag in self]


class Severity(enum.Enum):
    ERROR = "error"
    WARN = "warn"
    OFF = "off"


Resolver = Callable[["Glossary", "Ref"], "list[Term]"]


def by_file(glossary: Glossary, ref: Ref) -> list[Term]:
    return list(glossary.by_file.get(ref.destination, [])) if ref.destination is not None else []


def by_id(glossary: Glossary, ref: Ref) -> list[Term]:
    return list(glossary.by_id.get(ref.target, []))


def by_name(glossary: Glossary, ref: Ref) -> list[Term]:
    if ref.ns is None and "/" in ref.target and ":" in ref.target:
        return glossary.resolve(ref.target)
    return glossary.resolve(ref.name, ref.ns)


def unqualified(resolver: Resolver) -> Resolver:
    """Apply `resolver` only to refs without a namespace."""
    return lambda glossary, ref: [] if ref.ns else resolver(glossary, ref)


def first(*resolvers: Resolver) -> Resolver:
    """The first resolver that finds anything wins."""
    def resolve(glossary: Glossary, ref: Ref) -> list[Term]:
        for resolver in resolvers:
            if found := resolver(glossary, ref):
                return found
        return []
    return resolve


@dataclass(frozen=True)
class Policy:
    name: str        # `references:` key and `--kind` choice
    kind: str        # reported kind: wiki-links and delimiters are both "explicit"
    resolve: Resolver
    code: str        # what a failure reports: unresolved (E00x) or, for mentions, W002
    scannable: Context = Context.NONE  # regions this kind can match in at all
    scans: Context = Context.NONE      # regions it does match in, within `scannable`
    severity: Severity = Severity.ERROR
    links: bool = False  # a resolved ref links its term for W002

    def override(self, *, severity: Severity | None = None,
                 scans: Context | None = None) -> Policy:
        if scans is not None and scans & ~self.scannable:
            extra = ", ".join((scans & ~self.scannable).names())
            allowed = ", ".join(self.scannable.names()) or "nothing"
            raise ValueError(f"{self.name} cannot scan {extra}; it can scan {allowed}")
        return replace(self, severity=severity or self.severity,
                       scans=self.scans if scans is None else scans)


Policies = Mapping[str, Policy]

_EXPLICIT = first(by_name, unqualified(by_id))
_ANYWHERE = Context.INLINE_CODE | Context.ADDRESS | Context.COMMENT

POLICIES: Policies = {policy.name: policy for policy in (
    Policy("wiki", "explicit", _EXPLICIT, "E002", _ANYWHERE,
           Context.ADDRESS | Context.COMMENT, links=True),
    # Slash-commands are written in backticks; paths in URLs are not commands.
    Policy("delimiter", "explicit", _EXPLICIT, "E002", _ANYWHERE,
           Context.INLINE_CODE | Context.COMMENT, links=True),
    # A link inside a code span is not a link, so code is not scannable.
    Policy("markdown", "markdown", by_file, "E002", Context.COMMENT, Context.COMMENT,
           links=True),
    Policy("id", "id", by_id, "E004", _ANYWHERE, Context.COMMENT, links=True),
    Policy("field", "field", first(by_id, by_name), "E006"),
    Policy("catalog", "catalog", first(by_id, by_name), "E006"),
    # Severity here is the unlinked-mention warning (W002), off by default.
    Policy("mention", "mention", by_name, "W002", _ANYWHERE, severity=Severity.OFF),
    # Only links to missing files that no record owns become refs, so none resolves.
    Policy("link", "link", lambda glossary, ref: [], "W007", Context.COMMENT,
           severity=Severity.WARN),
)}

KINDS = tuple(sorted({policy.kind for policy in POLICIES.values()} | set(POLICIES)))


@dataclass(frozen=True)
class Guarantee:
    """A docs/spec.md sentence that no configuration may contradict.

    `spec` is quoted verbatim, so a test fails if the spec drops the sentence.
    `broken_by` names the setting that would contradict it, or returns None.
    Structural guarantees need no check: the schema cannot express a violation
    (Context has no member for fences), and a property test confirms it.
    """
    spec: str
    broken_by: Callable[[Config], str | None] = lambda config: None


def _relaxes_includes(config: Config) -> str | None:
    """An unresolved include link is a Markdown ref, so it reports E002 at the
    markdown severity. Only a glossary rule can mark a missing file as a part."""
    severity = config.policies["markdown"].severity
    return f"references.markdown.severity: {severity.value}" if (
        config.part_rules and severity is not Severity.ERROR) else None


GUARANTEES = (
    Guarantee("Fenced code blocks are never scanned"),
    Guarantee("Frontmatter is never scanned as prose"),
    Guarantee("Definition lines are metadata: they produce no references"),
    Guarantee("can never fail the build",
              lambda config: "references.mention.severity: error"
              if config.policies["mention"].severity is Severity.ERROR else None),
    Guarantee("An include link that resolves nowhere fails the build under any configuration",
              _relaxes_includes),
)


def broken_guarantees(config: Config) -> list[str]:
    return [f"{setting} contradicts the spec guarantee '{guarantee.spec}'"
            for guarantee in GUARANTEES if (setting := guarantee.broken_by(config))]
