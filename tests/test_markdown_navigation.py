"""Offline navigation evidence captured from GitHub's synthetic Markdown input."""

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ubiq.cli import build
from ubiq.scan import _interpret_markdown, _local_path, file_link_targets

FIXTURE = Path(__file__).parent / "fixtures" / "markdown-navigation"


class Navigation(HTMLParser):
    """Collect text-link destinations, excluding GitHub's clickable image wrappers."""

    def __init__(self):
        super().__init__()
        self.links = []
        self.href = None
        self.image = False

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.image = False
        elif tag == "img":
            self.image = True

    def handle_endtag(self, tag):
        if tag == "a":
            if self.href is not None and not self.image:
                self.links.append(self.href)
            self.href = None


def corpus(tmp_path):
    html = Navigation()
    html.feed((FIXTURE / "github.html").read_text())
    source = tmp_path / "README.md"
    source.write_text((FIXTURE / "source.md").read_text())
    targets = [source.parent / unquote(urlsplit(href).path)
               if urlsplit(href).path else None for href in html.links]
    # Source-only metadata references remain checked, but do not count as preview links.
    hidden = tmp_path / "glossary" / "hidden.md"
    for index, target in enumerate(dict.fromkeys([*targets, hidden])):
        if target is not None:
            target.parent.mkdir(exist_ok=True)
            name = target.stem if target.stem in ("plain", "hidden") else f"target-{index}"
            target.write_text(f"---\nterm: {name}\n---\n\n# Section\n")
    (tmp_path / "ubiq.yaml").write_text(
        'glossary: ["glossary/*.md"]\ndocs: [README.md]\ndelimiters: ["/"]\n')
    return source, html.links, targets, hidden


def test_supported_navigation_matches_captured_github_destinations(tmp_path):
    source, hrefs, expected, _ = corpus(tmp_path)
    document = _interpret_markdown(source.read_text())
    visible = [(start, end, spec) for start, end, spec in document.links
               if not any(a <= start < b for a, b in document.comments)]
    assert len(visible) == len(hrefs) == 27
    assert [_local_path(source, spec) for _, _, spec in visible] == expected
    assert [unquote(urlsplit(spec).fragment) for _, _, spec in visible] == [
        unquote(urlsplit(href).fragment) for href in hrefs]


def test_scan_and_traversal_preserve_visible_and_source_only_targets(tmp_path):
    source, _, expected, hidden = corpus(tmp_path)
    built = build(tmp_path)
    assert not built.diagnostics
    markdown = [ref for ref in built.refs if ref.kind == "markdown"]
    assert [ref.destination for ref in markdown] == [
        p for p in expected if p and p.parent == hidden.parent] + [hidden]
    assert set(file_link_targets(source, tmp_path)) == {
        p for p in expected if p and p.suffix == ".md"} | {hidden}
    assert all(ref.resolve(built.glossary) for ref in built.refs)
    # Both kinds intentionally scan source-only comments by default.
    assert any(ref.raw == "[[hidden]]" for ref in built.refs)
    assert any(ref.raw == "/hidden" for ref in built.refs)


def test_path_wiki_links_keep_literal_entity_names(tmp_path):
    source = tmp_path / "README.md"
    target = tmp_path / "a&amp;b.md"
    source.write_text("[[a&amp;b.md]]\n")
    target.write_text("A literal wiki filename.\n")
    assert file_link_targets(source, tmp_path) == [target]
