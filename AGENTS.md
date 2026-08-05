# Hello My Assistant

## Agent skills

### Issue tracker

Issues are tracked in this repository's GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the five default canonical triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

Use the single-context domain documentation layout. See `docs/agents/domain.md`.

## Testing

### Principles

- Identify the subject module and its interface before writing a test.
- Test observable behavior through the module's interface, not its implementation details.
- Give each behavior one primary owning test at the narrowest interface that can prove it.
- Use a broader test only for behavior that narrower tests cannot prove, such as wiring or interaction across modules.
- Do not repeat lower-level edge cases in broader tests unless the broader path introduces a distinct risk.
- Keep each test focused on one behavior and one reason to fail.
- Name tests as `test_<subject>_<expected_behavior>_when_<scenario>`. Omit the condition when no meaningful scenario distinction exists.
- Parametrize cases only when they exercise the same behavior with different inputs, and give each case a descriptive ID.
- Use terminology from `CONTEXT.md` consistently in test names.
