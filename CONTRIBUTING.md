# Contributing to BUSCASAM

How to take a feature or bug from idea to merged PR. The flow is built around AI skills that live in `.claude/skills/`; you drive them.

Read [WORKFLOW.md](docs/WORKFLOW.md) once for the *why*. This file is the *how*.

---

## Before you start

- [ ] Read [SPEC.md](docs/SPEC.md) — product scope and behavior.
- [ ] Read [CLAUDE.md](CLAUDE.md) — working principles agents must follow.
- [ ] Skim `.claude/docs/issue-tracker.md` and `.claude/docs/triage-labels.md` — how issues are created, labeled, and moved on the project board.

If `CONTEXT.md` or `docs/adr/` exist, read the ones relevant to your area. They define the project's vocabulary and locked-in decisions.

---

## Feature flow

```
idea → grill-with-docs → to-prd → module-map → to-issues → tdd → code-review → merge
```

Run each skill in its own session. Clear context between phases — fresh prompts beat compacted ones.

### 1. Grill the idea — `/grill-with-docs`
- Surface every design decision before any code is written.
- Stay on **specification** (what the system IS), not MVP scoping or rollout order.
- Output: shared mental model + updates to `CONTEXT.md` / new ADRs in `docs/adr/`.

### 2. Write the PRD — `/to-prd`
- Summarizes the grilling session into a GitHub issue with labels `ai` + `prd`.
- Don't review the PRD deeply — you already aligned during grilling. Skim for accuracy.
- Make sure the issue is linked to the project board.

### 3. Design the module map — `/module-map`
- Run *after* the PRD is approved, *before* any implementation.
- Output: `docs/module-maps/<feature-slug>.md` with module names from `CONTEXT.md`, interfaces, seams, dependency graph.
- Architectural anchor — implementing agents reference it during TDD.

### 4. Break into slices — `/to-issues`
- Cuts the PRD into **vertical tracer-bullet slices** (each crosses all layers end-to-end).
- Each slice issue must:
  - Reference the parent PRD as a real GitHub sub-issue.
  - Point to the module map under "Architecture anchor."
  - Carry exactly one priority label: `tracer` | `infra` | `polish` | `critical`.
  - Land on the project board.
- All slices except the first get the `blocked` label until their prerequisites merge.

### 5. Implement — `/tdd <issue#>`
- One slice = one branch = one PR.
- Pick up the issue: remove `needs-triage`, move project Status to **In progress**.
- Strict **red-green-refactor**, one test at a time. No horizontal slicing (don't write all tests first).
- Tests go through the public interface; mock only at process boundaries.
- Open the PR with `Closes #<n>` in the body. Status auto-moves to **In review**.

### 6. Review — `/code-review <PR#>`
- Posts structured `BLOCKING / WARN / NIT` comments with IDs (`R001`, `R002`, …).
- **You cannot merge while any BLOCKING is open.**
- Fix findings, reply `**Status**: resolved — <commit-sha>`, re-run `/code-review` until the merge gate clears.
- WARN waivers must come from you (the human), not the agent.

### 7. Merge
- Squash-merge when review is clean. Issue auto-closes; project Status auto-moves to **Done**.
- When a `blocked` issue's last blocker closes, remove its `blocked` label so the next contributor can pick it up.

---

## Bug-fix flow

Skip `grill-with-docs` / `to-prd` / `module-map` for surgical fixes.

1. File a bug issue (or pick one up). Apply `critical` if it blocks active work.
2. `/tdd <issue#>` — start with a failing test that reproduces the bug. Make it pass. No drive-by refactors.
3. `/code-review <PR#>` → resolve findings → merge.

If the bug reveals a deeper design problem, stop and escalate to a PRD instead.

---

## Architecture maintenance

When friction accumulates (shallow modules, hard-to-test seams), run `/improve-codebase-architecture`. Outputs deepening candidates — pick one, grill it, then implement via the normal slice → TDD → review flow.

---

## Conventions

**Branches:** `<type>/<short-slug>` — e.g. `feat/search-pagination`, `fix/duplicate-author-link`.

**Commits:** imperative, lowercase, no period, under 50 chars. Match existing project style — no Conventional Commits.

**PRs:**
- Title: short, descriptive.
- Body: `Closes #<n>` (mandatory — drives auto-close and Status flip).
- One PR per slice. No mixed-concern PRs.

**Labels:** never invent new ones. See `.claude/docs/triage-labels.md` for the full vocabulary (`needs-triage`, `ready`, `blocked`, priority labels, domain labels).

---

## Working principles (non-negotiable)

From [CLAUDE.md](CLAUDE.md):

- **Think before coding.** State assumptions; surface multiple interpretations; push back if SPEC points to a simpler path.
- **Simplicity first.** Minimum code that solves the stated problem. No speculative features.
- **Surgical changes.** Touch only what the task requires. No reformatting adjacent code.
- **Goal-driven execution.** Restate the task as a verifiable goal before coding.

Plus from [WORKFLOW.md](docs/WORKFLOW.md):

- **Vertical, not horizontal.** Every slice ships a thin path through all layers.
- **Deep modules.** Small interfaces, lots of hidden behavior. Apply the deletion test.
- **Clear context between phases.** Don't compact across skills.
- **QA is manual.** Run the change in a browser before claiming done.

---

## Where to ask

- Confused about scope? Re-read docs/SPEC.md and the relevant PRD before asking.
- Confused about a term? Check `CONTEXT.md`; if absent, raise it during the next grilling session.
- Confused about a past decision? Check `docs/adr/`.
- Still stuck? Open a `needs-info` issue with what you tried and what blocked you.
