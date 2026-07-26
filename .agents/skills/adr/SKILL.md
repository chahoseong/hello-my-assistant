---
name: adr
description: Create a new Architecture Decision Record (ADR) in Michael Nygard format. Use when the user wants to document why a technical or architectural decision was made, record trade-offs between alternatives, or explicitly asks to write/create an ADR.
---

## When to write an ADR

Not every decision deserves one. Write an ADR only when:

- Real alternatives existed and were weighed
- The decision is hard or costly to reverse
- The reasoning wouldn't be obvious just from reading the code

If none of these apply, say so and skip creating the file.

## Procedure

1. Check `docs/architecture/decisions/` for existing ADRs. Find the highest `NNNN` number present (files are named `NNNN-slug.md`, 4-digit zero-padded, no `adr-` prefix); the new one is the next number. If the folder doesn't exist, create it and start at `0001`.
2. Read `references/TEMPLATE.md` for the exact section structure, title format, and what belongs in each section.
3. Using the decision discussed in the conversation, draft each section. If information needed for a section wasn't actually discussed (e.g. alternatives), ask the user rather than inventing it.
4. Derive a short kebab-case slug from the title (e.g. title "Group deployable services under apps/" → slug `group-deployable-services-under-apps`).
5. Save the result to `docs/architecture/decisions/NNNN-slug.md`.
