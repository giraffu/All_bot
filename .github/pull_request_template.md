## Summary

Describe the task and behavior change.

## Concurrent workspace handoff

- Slot: `A | B | C | D | E | F | G | H`
- Main base SHA:
- Head SHA:
- Affected modules:
- Migration: `none | revision and forward-compatibility notes`
- Risks:
- Focused tests:

## Validation

List exact commands and results. Normal A–H development uses an immutable handoff and
the main single-writer integration queue without a per-task PR. If an exceptional PR is
needed, target `main`; `codex/test-train` is retired compatibility history.
