# Agent Instructions

## Working Principles

### Think before coding
- State assumptions; ask when uncertain rather than guessing.
- Surface multiple interpretations on ambiguous input — don't pick silently.
- Push back if `docs/SPEC.md` or `CONTEXT.md` points to a simpler path.
- Stop and name the confusion instead of plowing through.

### Simplicity first
- Minimum code that solves the stated problem. No speculative features, abstractions, or config knobs.
- No error handling for impossible cases. Trust internal invariants; validate only at boundaries.
- If 200 lines could be 50, rewrite before shipping.

### Surgical changes
- Touch only what the task requires. Don't reformat, rename, or "improve" adjacent code.
- Match existing style even when you'd write it differently.
- Remove imports/items your change orphaned. Flag pre-existing dead code; don't delete it unasked.

### Goal-driven execution
- Restate the task as a verifiable goal before coding (e.g., "test reproduces bug → make it pass", "tests green before and after refactor").

## Language

- **English**: prompts, code, comments, commit messages, PRs, issues, ADRs, module maps, PRDs, skill files, agent-facing docs (`CLAUDE.md`, `CONTRIBUTING.md`, `WORKFLOW.md`).
- **Spanish**: user-facing product content only (`README.md`, `docs/SPEC.md`, UI copy, end-user notifications).
- If a contributor prompts in Spanish, respond in English and continue in English.
