# Domain Docs

How engineering skills should consume this repository's domain documentation.

## Before exploring, read these

- `CONTEXT.md` at the repository root
- `CONTEXT-MAP.md`, if it exists, and the context documents it references
- Relevant ADRs under `docs/adr/`
- In a multi-context repository, relevant context-specific ADRs

If these files do not exist, proceed silently. Do not suggest creating them upfront. The domain-modeling workflow creates them lazily when terminology or architectural decisions are resolved.

## File structure

This repository uses the single-context layout:

```text
/
├── CONTEXT.md
├── docs/
│   └── adr/
└── apps/
```

`CONTEXT.md` is a domain glossary only. Implementation and architectural decisions belong in `docs/adr/`.

## Use the glossary's vocabulary

Use terms exactly as defined in `CONTEXT.md` when naming domain concepts in issues, proposals, hypotheses, and tests. Avoid synonyms explicitly rejected by the glossary.

If a required concept is absent, reconsider whether it belongs to the domain language or note it for the domain-modeling workflow.

## Flag ADR conflicts

If proposed work contradicts an existing ADR, surface the conflict explicitly instead of silently overriding the decision.
