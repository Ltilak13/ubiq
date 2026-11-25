# Read canonical goal metadata on GitHub

GitHub's repository file view is the acceptance environment for these goals.
Use its native Markdown preview and frontmatter display. If a value is absent
or unclear, select **Code** or **Raw** on the same file. Source access is a
supported way to read required metadata. A rendered table does not need to
repeat the metadata in the document body.

The [goal index](README.md) explains which fields own the current assessment.
Read those fields before interpreting historical evidence in a goal's body.

## Check the three goals

The sample is every goal linked from the index: domain schema, composable
skills, and human and agent readability. This sample covers nested support
records and empty support lists. Other Markdown documents, editor previews,
GitHub Pages, and human comprehension are outside this check.

1. Choose a published commit. Record its full SHA and the date of the check.
   Open each goal's GitHub file view at that SHA.
2. Begin in **Preview**. Answer each question below. If needed, select **Code**
   or **Raw**. Record the view used and whether the switch succeeds.
3. Compare each answer with the frontmatter in the same commit. Record a
   missing value or a conflicting value as a failure.
4. Record the three file URLs, reviewer or tool, questions checked, failures,
   and number of source switches. Separate preview visibility from source
   access. A source fetch alone does not verify the browser's controls.

| Question | Authoritative frontmatter location |
| --- | --- |
| What identifies this goal? | `name` |
| What is its current status? | `status` |
| Which criteria have assessments? | Keys of `criteria` |
| What is each criterion's assessment and remaining gap? | `criteria.<AC>.assessment` and `.gap` |
| Which features support each criterion, including none? | `criteria.<AC>.support` |
| Where is each feature implemented and checked? | Each support entry's `implementation` and `check`, including both `path` and `anchor` |

Require correct answers for all questions across all three files. Count each
criterion and support entry separately within its question. Required values
must be accessible, with zero missing or conflicting answers. Report direct
preview visibility separately, even when source access succeeds.

For a local source baseline, run this from the checkout of the recorded SHA:

```sh
python3 -m ubiq.cli check
python3 -m pytest tests/test_goals.py -q
python3 - <<'PY'
import json
from pathlib import Path
from ubiq.schemas import load_data

for path in sorted(Path('docs/goals').glob('*-goal.md')):
    print(path)
    print(json.dumps(load_data(path, frontmatter=True), indent=2, ensure_ascii=False))
PY
```

These commands validate shape, criterion labels, and evidence locations. The
JSON output reads canonical frontmatter directly. It is temporary comparison
output, not another source to maintain. The commands do not test GitHub or
establish whether a feature satisfies a goal.

When metadata changes, repeat the check at the new commit. Confirm that the
changed value appears through Preview or Code/Raw without a second metadata
edit. Record both revisions. Do not treat an earlier observation as evidence
for a later revision.

## Evidence and limits

GitHub documents [frontmatter table rendering](https://github.blog/news-insights/product-news/viewing-yaml-metadata-in-your-documents/)
and [Code, Preview, and Raw views](https://docs.github.com/en/repositories/working-with-files/using-files/viewing-and-understanding-files).

On 2026-11-25, a web text extraction of a
[GitHub Docs file](https://github.com/github/docs/blob/main/content/repositories/working-with-files/using-files/viewing-and-understanding-files.md)
exposed its frontmatter table and Preview, Code, and Raw controls. A GitHub
connector fetched the same file's YAML. The sample contained scalar, list, and
nested mapping values. This was one external example at a moving branch,
without a browser interaction or a pinned revision. It establishes a useful
starting point, not a passing result for these goals.

A recorded check of the three goals at a published commit is still required.
Local checks must not mark the broader readability goal as achieved.
