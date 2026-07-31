# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`
- **Read an issue**: `gh issue view <number> --comments`, including labels
- **List issues**: use `gh issue list` with appropriate state and label filters
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply or remove labels**: `gh issue edit <number> --add-label "..."` or `--remove-label "..."`
- **Close an issue**: `gh issue close <number> --comment "..."`

Infer the repository from `git remote -v`. When run inside this clone, `gh` resolves `chahoseong/hello-my-assistant` automatically.

## Pull requests as a triage surface

**PRs as a request surface: no.**

If this is changed to `yes` later, external pull requests should use the same triage states and labels as issues.

GitHub shares one number space across issues and pull requests. Resolve an ambiguous reference such as `#42` with `gh pr view 42`, falling back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The map is a single issue with child issues as tickets.

- **Map**: an issue labelled `wayfinder:map`, containing Notes, Decisions-so-far, and Fog
- **Child ticket**: a GitHub sub-issue where supported; otherwise use a task-list entry and `Part of #<map>`
- **Child labels**: `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, or `wayfinder:task`
- **Blocking**: use GitHub native issue dependencies where available; otherwise add `Blocked by: #<n>` to the child
- **Frontier query**: select the first open, unblocked, unassigned child in map order
- **Claim**: `gh issue edit <n> --add-assignee @me`
- **Resolve**: comment with the result, close the child, and append a context pointer to the map
