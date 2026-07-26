## Decision record template

Based on [Documenting architecture decisions - Michael Nygard](http://thinkrelevance.com/blog/2011/11/15/documenting-architecture-decisions), and following the style actually used in practice by tools like [adr-tools](https://github.com/npryce/adr-tools/tree/master/doc/adr).

Real ADRs are short — a few lines per section, not essays. Bullet points are fine wherever they make a list easier to scan.

In each ADR file, write these sections:

# N. Title

`N` is the ADR's plain sequence number (no zero-padding, no "ADR" word — just `# 3. Single command with subcommands`).

Date: YYYY-MM-DD

## Status

"proposed" if not yet agreed, "accepted" once agreed. If a later ADR reverses this one, mark it "deprecated" or "superseded", with a reference to the replacement.

## Context

The forces at play — technological, political, social, project-local. These forces are often in tension; call that out. Write this section value-neutral: just the facts, not the response to them. A few short sentences or a bullet list of the options considered is enough.

## Decision

The response to those forces, stated plainly. Doesn't need to be forced into "We will …" boilerplate — a direct declarative statement is fine.

## Consequences

The resulting context after applying the decision. List all consequences, not just the positive ones — positive, negative, and neutral all belong here, since all of them affect the project going forward. Short bullets or short paragraphs, not a full write-up.
