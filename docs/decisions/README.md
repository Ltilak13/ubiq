# Decisions

Each decision is a record in this folder, numbered in the order it was
accepted. Its frontmatter holds the facts: the question it answers, its status,
when and by whom it was decided, the options considered, and the outcome. The
body holds the rationale.

Record a decision here when it is made, in the pull request that acts on it or
in its own pull request. GitHub comments that announce a decision mirror the
record; once [#152](https://github.com/Ltilak13/ubiq/issues/152) lands, the sync
generates them. A later decision that replaces one sets `supersedes` and the
earlier record's `status` becomes `superseded`.

| Field | Meaning |
| --- | --- |
| `name` | Stable identifier, matching the file name without its number |
| `question` | The issue the decision answers |
| `status` | `proposed`, `accepted`, or `superseded` |
| `decided` | Date accepted |
| `by` | Who decided |
| `options` | The options considered |
| `outcome` | What was decided, as short statements |
| `supersedes` | The decision this one replaces, if any |
| `closes` | Whether accepting it closes the question issue (default `true`; `false` for tracking issues) |
