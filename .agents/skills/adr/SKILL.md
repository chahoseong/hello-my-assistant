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

1. Check `docs/architecture/decisions/` for existing ADRs. Find the highest `adr-NNN.md` number present; the new one is the next number, zero-padded to 3 digits (e.g. `adr-001.md`, `adr-002.md`). If the folder doesn't exist, create it and start at `adr-001.md`.
2. Read `references/TEMPLATE.md` for the exact section structure and what belongs in each section.
3. Using the decision discussed in the conversation, draft each section. If information needed for a section wasn't actually discussed (e.g. alternatives), ask the user rather than inventing it.
4. Save the result to `docs/architecture/decisions/adr-NNN.md`.
