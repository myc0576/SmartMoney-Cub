# TypeSafe AI Skill Provenance

- **Upstream Repository**: https://github.com/typesafe-ai/skills
- **Pinned Commit**: `65a39f393687675ce170e6094757de20370365b9`
- **Upstream Plugin Version**: `0.5.7`
- **License**: MIT

## Vendored Files

- `.codex/skills/typesafe-ai/SKILL.md`: `71ea90d7906c6554c4f4c460ef7361b2d26f59116ccdae986dc6d997b9389f52`
- `.codex/skills/typesafe-ai/LICENSE`: `835f233f1d6ed84a9b9a351aba0689b47644a4137d6316911fc7957bde523b02`

## Verification

To verify the integrity of the vendored files:

```bash
shasum -a 256 .codex/skills/typesafe-ai/SKILL.md .codex/skills/typesafe-ai/LICENSE
```

## Security & Execution Boundary

This skill is a read-only prompt asset that must never be treated as an execution surface.
