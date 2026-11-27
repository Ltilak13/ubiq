# No-code checks

A minimal repository whose specs are checked by four tools with no agent:
`ubiq check`, `cue vet`, `vale`, and `cucumber`. The recipe that explains the
setup is [no-code checks](../../docs/no-code-checks.md).

The one record is the [reservation](specs/reservation.md) spec. Each fact has one home:

| Fact | Home | Checked by |
| --- | --- | --- |
| Record shape and references | `specs/reservation.md` frontmatter | `ubiq check` |
| Limits and their cross-field rule | `limits/limits.yaml`, `limits/limits.cue` | `cue vet` |
| Writing rules for prose | `.vale/styles/Spec/` | `vale` |
| Behavior | `features/reservation.feature` | `cucumber` |

Run every check from this directory:

```sh
ubiq check
cue vet -d '#Limits' limits/limits.cue limits/limits.yaml
vale --config .vale.ini specs
npm ci && npm run cucumber
```
