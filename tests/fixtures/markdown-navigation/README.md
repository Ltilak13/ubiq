# GitHub navigation evidence

`source.md` is synthetic input. `github.html` is the unedited response from
`POST https://api.github.com/markdown`, with `mode: gfm` and no repository
context, captured on 2026-11-25 at approximately 19:10 UTC. GitHub does not
identify the renderer build in this response. No repository content was sent.

The offline tests compare 20 visible text links with the captured destinations,
including requested fragments. The sample covers inline links, angle brackets,
titles, reference links, normalized labels, first-definition precedence,
escaped parentheses, percent encoding, and character references. It includes
named, decimal, hexadecimal, unknown, unterminated, and escaped entity cases.
Reference definitions use the same destination interpretation as inline links.

The tests create the destination files, then check source reference resolution
and document traversal. One Markdown link inside an HTML comment remains a
source-only reference and traversal target. Wiki references and slash commands
also retain their documented source-checking behavior. These references do not
count toward the 20 visible links. Images, code, unused definitions, escaped
link syntax, and undefined references do not count either. GitHub wraps the
image in a clickable anchor, which the test excludes explicitly.

This capture measures destination agreement for this sample. It does not test
browser clicks, repository URL rewriting, heading ID generation, or every GFM
construct. Requested fragments are compared as decoded strings. General
fragment existence checks remain outside Ubiq's contract, except for W004's
installed-layout checks. Nested labels and multiline definitions remain outside
the documented subset. Indented code and raw HTML blocks need separate evidence
before the sample can cover them. Passing this test makes no claim about those
cases or future GitHub renderer changes.

Run the offline checks from the repository root:

```sh
python -m pytest tests/test_markdown_navigation.py -q
```

To refresh the capture, review the synthetic source first. Run this command from
the repository root, then inspect the HTML diff and update the capture date:

```sh
python - <<'PY' | gh api markdown --input - > tests/fixtures/markdown-navigation/github.html
import json
from pathlib import Path
source = Path('tests/fixtures/markdown-navigation/source.md').read_text()
print(json.dumps({'mode': 'gfm', 'text': source}))
PY
```

The refresh requires GitHub access. Ordinary test runs use only the committed
capture and Python's standard-library HTML parser.
